#!/bin/sh
# Behavioural tests for item 1 against the sandbox. Prints a PASS/FAIL table.
#   sandbox/up.sh && ansible-playbook -i sandbox/inventory.yml playbooks/site.yml && sandbox/test.sh
cd "$(dirname "$0")/.." || exit 1
x() { docker exec msp-sandbox "$@"; }
fail=0
t() { if [ "$1" = 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=$((fail+1)); fi; }

# 1 fixtures on the node
x sh /usr/local/lib/msp/tests/run.sh >/tmp/fx.out 2>&1; r=$?
t $r "fixtures on node: $(tail -n1 /tmp/fx.out)"

# 2 three timers scheduled
n=$(x systemctl list-timers --all --no-legend --plain 'msp-check@*' | grep -vc '^-' )
[ "$n" = 3 ]; t $? "3 timers scheduled (got $n)"

# 3 a check run writes state and a heartbeat
x systemctl start msp-check@disk.service
x grep -q '^rc=' /var/lib/msp/state/disk.state; t $? "state file written: $(x sed -n 's/^msg=//p' /var/lib/msp/state/disk.state)"
x grep -q 'disk hc-disk sent' /var/log/msp/heartbeat.log; t $? "heartbeat logged as sent"
x grep -q '^POST /hc-disk ' /var/log/msp/hc-fake.log; t $? "heartbeat reached endpoint (plain ping = success)"
x systemctl is-failed --quiet msp-check@disk.service; [ $? != 0 ]; t $? "finding exit codes do not fail the unit"

# 4 a broken check fires OnFailure -> msp-alert -> _checker/fail
x sh -c 'printf "#!/bin/sh\nexit 3\n" > /usr/local/lib/msp/checks/check-crash.sh; chmod +x /usr/local/lib/msp/checks/check-crash.sh'
x systemctl start msp-check@crash.service 2>/dev/null
sleep 1
x grep -q '^POST /hc-checker/fail checker broke: msp-check@crash.service' /var/log/msp/hc-fake.log; t $? "checker-broke path pages _checker"
x rm -f /usr/local/lib/msp/checks/check-crash.sh; x systemctl reset-failed msp-check@crash.service

# 5 baseline flip with a deliberately failed unit; consecutive gating; expected-failed clears it
x sh -c 'printf "[Service]\nType=oneshot\nExecStart=/bin/false\n" > /etc/systemd/system/msp-testfail.service; systemctl daemon-reload; systemctl start msp-testfail.service' 2>/dev/null
x systemctl start msp-check@systemd.service
x grep -q '^rc=2' /var/lib/msp/state/systemd.state; t $? "unexpected failed unit -> CRIT: $(x sed -n 's/^msg=//p' /var/lib/msp/state/systemd.state)"
x grep -q '^POST /hc-systemd/log ' /var/log/msp/hc-fake.log; t $? "first crit run -> /log only (consecutive=2)"
x systemctl start msp-check@systemd.service
x grep -q '^POST /hc-systemd/fail ' /var/log/msp/hc-fake.log; t $? "second crit run -> /fail pages"
x sh -c 'echo "systemd.expected_failed = msp-testfail.service" >> /etc/msp/baseline.conf'
x systemctl start msp-check@systemd.service
x grep -q '^rc=0' /var/lib/msp/state/systemd.state; t $? "same unit in baseline -> OK: $(x sed -n 's/^msg=//p' /var/lib/msp/state/systemd.state)"
c=$(x grep -c ' systemd rc=' /var/log/msp/changes.log); [ "$c" = 2 ]; t $? "changes.log has exactly the 2 transitions (got $c)"

# 6 lock: a second concurrent run is refused with exit 3
x sh -c 'exec 9>/run/lock/msp-disk.lock; flock 9; /usr/local/bin/msp-run-check disk; echo rc=$?' | grep -q 'rc=3'; t $? "concurrent run refused by lock"

# 7 idempotence is checked by the caller (second playbook run: changed=0)
echo "---- $( [ $fail = 0 ] && echo ALL PASS || echo "$fail FAILED" )"
[ $fail = 0 ]
