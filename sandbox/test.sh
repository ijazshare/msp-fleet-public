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
n=$(x systemctl list-units --type=timer --all --no-legend --plain 'msp-check@*' | awk '$3=="active"' | wc -l)
[ "$n" = 5 ]; t $? "5 timers active (got $n)"
# from here on only explicit runs: the boot-time timer firings would interleave with the assertions
alltimers() { for c in heartbeat systemd disk configdump timers; do x systemctl "$1" "msp-check@$c.timer"; done; }
alltimers stop

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
ch0=$(x sh -c 'grep -c " systemd rc=" /var/log/msp/changes.log 2>/dev/null; true' | head -n1); ch0=${ch0:-0}
x systemctl start msp-check@systemd.service
x grep -q '^rc=2' /var/lib/msp/state/systemd.state; t $? "unexpected failed unit -> CRIT: $(x sed -n 's/^msg=//p' /var/lib/msp/state/systemd.state)"
x grep -q '^POST /hc-systemd CRIT failed units' /var/log/msp/hc-fake.log; t $? "first crit run -> plain ping carrying the finding (consecutive=2)"
x systemctl start msp-check@systemd.service
x grep -q '^POST /hc-systemd/fail ' /var/log/msp/hc-fake.log; t $? "second crit run -> /fail pages"
x sh -c 'cur=$(sed -n "s/^systemd.expected_failed = //p" /etc/msp/baseline.conf | tail -n1); echo "systemd.expected_failed = $cur msp-testfail.service" >> /etc/msp/baseline.conf'
x systemctl start msp-check@systemd.service
x grep -q '^rc=0' /var/lib/msp/state/systemd.state; t $? "same unit in baseline -> OK: $(x sed -n 's/^msg=//p' /var/lib/msp/state/systemd.state)"
c=$(x grep -c ' systemd rc=' /var/log/msp/changes.log); [ "$c" = "$((ch0+2))" ]; t $? "changes.log gained exactly the 2 transitions ($ch0 -> $c)"

# 6 lock: a second concurrent run is refused with exit 3
x sh -c 'exec 9>/run/lock/msp-disk.lock; flock 9; /usr/local/bin/msp-run-check disk; echo rc=$?' | grep -q 'rc=3'; t $? "concurrent run refused by lock"

# 7 item 2: a stopped timer is a CRIT finding of the timers check
alltimers start; x systemctl stop msp-check@disk.timer
x systemctl start msp-check@timers.service
x grep -q 'inactive: msp-check@disk.timer' /var/lib/msp/state/timers.state; t $? "stopped timer detected: $(x sed -n 's/^msg=//p' /var/lib/msp/state/timers.state)"
alltimers stop

# 8 item 2: heartbeat keeps the checker ID alive; then endpoint unreachable -> logged offline, state still written
x systemctl start msp-check@heartbeat.service
x grep -q '^POST /hc-checker checker alive' /var/log/msp/hc-fake.log; t $? "heartbeat run keeps the checker ID alive with a plain ping"
x systemctl stop hc-fake
x systemctl start msp-check@heartbeat.service
x grep -q 'heartbeat hc-heartbeat offline' /var/log/msp/heartbeat.log; t $? "endpoint down -> heartbeat logged offline"
x grep -q '^rc=0' /var/lib/msp/state/heartbeat.state; t $? "check still ran and wrote state while offline"
x systemctl start hc-fake

# 9 item 4: config dump settles to unchanged; one edit is exactly one WARN naming the file and one commit
x systemctl start msp-check@configdump.service; x systemctl start msp-check@configdump.service
x grep -q '^msg=OK config unchanged' /var/lib/msp/state/configdump.state; t $? "dump settles to unchanged: $(x sed -n 's/^msg=//p' /var/lib/msp/state/configdump.state)"
c0=$(x git -C /var/lib/msp/dump log --oneline | wc -l)
x sh -c 'echo "# drift test" >> /etc/hosts'
x systemctl start msp-check@configdump.service
x grep -q '^rc=1' /var/lib/msp/state/configdump.state && x grep -q 'etc/hosts' /var/lib/msp/state/configdump.state; t $? "edit -> WARN naming the file: $(x sed -n 's/^msg=//p' /var/lib/msp/state/configdump.state)"
x grep -q '^POST /hc-configdump WARN config changed' /var/log/msp/hc-fake.log; t $? "drift rides a plain ping with the message, did not page"
c1=$(x git -C /var/lib/msp/dump log --oneline | wc -l); [ "$c1" = "$((c0+1))" ]; t $? "edit produced exactly one dump commit ($c0 -> $c1)"
x sh -c 'test ! -e /var/lib/msp/dump/etc/pve/priv && test -z "$(find /var/lib/msp/dump -name "*.key")"'; t $? "no priv/ or *.key in the dump"
x stat -c %a /var/lib/msp/dump | grep -q '^700$'; t $? "dump dir is root-only (0700)"
d=$(x systemctl show msp-check@configdump.timer -p TimersMonotonic --value | grep -o 'OnUnitActiveUSec=[^ ;]*' | tr '\n' ' '); [ "$d" = "OnUnitActiveUSec=6h " ]; t $? "configdump interval override replaces default ($d)"

# 9b guests.exclude: excluded guest config never lands in the dump
x sh -c 'mkdir -p /etc/pve/nodes/sb/qemu-server /etc/pve/nodes/sb/lxc; echo "name: keep" > /etc/pve/nodes/sb/qemu-server/100.conf; echo "name: hide" > /etc/pve/nodes/sb/qemu-server/130.conf; echo "guests.exclude = 130" >> /etc/msp/baseline.conf'
x systemctl start msp-check@configdump.service
x sh -c 'test -e /var/lib/msp/dump/etc/pve/guests/100.conf && test ! -e /var/lib/msp/dump/etc/pve/guests/130.conf'; t $? "excluded guest 130 absent from dump, 100 present"
x rm -rf /etc/pve

# 11 msp_box: llm user, no sudo, launcher, repo, rules file, memory in repo, scratch tmpfs
x id -nG llm | grep -qvE 'sudo|adm'; t $? "llm user exists and is in no privileged group ($(x id -nG llm))"
x sh -c 'command -v sudo >/dev/null && sudo -l -U llm 2>/dev/null | grep -q "may run" && exit 1; exit 0'; t $? "llm has no sudo rules"
x test -L /home/llm/fake-origin/CLAUDE.md; t $? "CLAUDE.md is a symlink to AGENTS.md in the clone"
x grep -q 'zpool destroy' /home/llm/fake-origin/AGENTS.md; t $? "AGENTS.md carries the site never-stage list"
x git -C /home/llm/fake-origin log --oneline | grep -q 'msp: rules file'; t $? "layout and rules committed by the box"
x git -C /srv/fake-origin.git log --oneline | grep -q 'msp: rules file'; t $? "and pushed to the origin"
x sh -c 'readlink /home/llm/.claude/projects/-home-llm-fake-origin/memory | grep -q /home/llm/fake-origin/memory/claude'; t $? "Claude Code project memory symlinked into the repo"
x sh -c 'touch /home/llm/.claude/.credentials.json; cd /home/llm/fake-origin && git status --porcelain | grep -q credentials && exit 1; exit 0'; t $? "credentials file is outside the repo tree"
x su -s /bin/sh -c 'XDG_RUNTIME_DIR=/tmp/xdg; export XDG_RUNTIME_DIR; mkdir -p $XDG_RUNTIME_DIR; msp-tmux </dev/null >/dev/null 2>&1; tmux list-windows -t msp -F "#W"' llm | tr '\n' ' ' | grep -q 'plan scratch'; t $? "msp-tmux creates plan and scratch windows"
x su -s /bin/sh -c 'tmux send-keys -t msp:scratch "echo SCR=\$CLAUDE_CONFIG_DIR:\$MSP_SCRATCH > /tmp/scr.env" Enter; tmux send-keys -t msp:plan "echo PLAN=\$CLAUDE_CONFIG_DIR:\$MSP_SCRATCH > /tmp/plan.env" Enter' llm; sleep 1
x grep -q 'SCR=/tmp/xdg/claude-scratch:1' /tmp/scr.env; t $? "scratch window: own CLAUDE_CONFIG_DIR on tmpfs and MSP_SCRATCH=1 ($(x cat /tmp/scr.env))"
x grep -q '^PLAN=:$' /tmp/plan.env; t $? "plan window: default config dir, no scratch flag ($(x cat /tmp/plan.env))"
x su -s /bin/sh -c 'tmux kill-server' llm 2>/dev/null

# 10 idempotence is checked by the caller (second playbook run: changed=0)
echo "---- $( [ $fail = 0 ] && echo ALL PASS || echo "$fail FAILED" )"
[ $fail = 0 ]
