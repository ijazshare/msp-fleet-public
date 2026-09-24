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
[ "$n" = 7 ]; t $? "7 timers active on the box (got $n)"
# from here on only explicit runs: the boot-time timer firings would interleave with the assertions
alltimers() { for c in heartbeat systemd disk configdump guarantee scratch timers; do x systemctl "$1" "msp-check@$c.timer"; done; }
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
x su -s /bin/sh -c 'XDG_RUNTIME_DIR=/tmp/xdg; export XDG_RUNTIME_DIR; mkdir -p $XDG_RUNTIME_DIR; msp-tmux </dev/null >/dev/null 2>&1; tmux list-windows -t msp -F "#W"' llm | tr '\n' ' ' | grep -q 'plan'; t $? "msp-tmux creates the plan window (scratch window closes itself here: userns blocked on this laptop)"
x su -s /bin/sh -c 'tmux send-keys -t msp:plan "echo PLAN=\$CLAUDE_CONFIG_DIR:\$MSP_SCRATCH > /tmp/plan.env" Enter' llm; sleep 1
x grep -q '^PLAN=:$' /tmp/plan.env; t $? "plan window: no scratch flag ($(x cat /tmp/plan.env))"
o=$(x su -s /bin/sh -c 'XDG_RUNTIME_DIR=/tmp/xdg msp-scratch --test; echo rc=$?' llm 2>&1); echo "$o" | grep -qE 'rc=(0|97)$'; t $? "scratch --test is isolated or refused, never leaking: $(echo "$o" | tail -n 2 | tr '\n' ' ')"
x su -s /bin/sh -c 'test ! -e ~/.msp-scratch-probe' llm; t $? "no probe file leaked into the real home"
x systemctl start msp-check@scratch.service; x grep -qE '^rc=(0|1)$' /var/lib/msp/state/scratch.state; t $? "scratch check reports OK or WARN, never CRIT here: $(x sed -n 's/^msg=//p' /var/lib/msp/state/scratch.state | cut -c1-70)"
x su -s /bin/sh -c 'tmux select-window -t msp:scratch; tmux display -p "#{status-style}"' llm | grep -q colour125; t $? "scratch window: magenta status bar"
x su -s /bin/sh -c 'tmux select-window -t msp:plan; tmux display -p "#{status-style}"' llm | grep -q colour25; t $? "plan window: blue status bar"
x su -s /bin/sh -c 'tmux show -gv set-clipboard' llm | grep -q '^on$'; t $? "clipboard forwarding on"
x su -s /bin/sh -c 'MSP_SCRATCH=1 bash -ic "echo \$PS1"' llm 2>/dev/null | grep -q SCRATCH; t $? "scratch prompt shows [SCRATCH]"
x su -s /bin/sh -c 'tmux kill-server' llm 2>/dev/null

# 12 item 5: the gate. h = the hypervisor container; box reaches it as msp-agent over ssh.
h() { docker exec msp-sandbox-host "$@"; }
docker cp sandbox/gate-approve.py msp-sandbox-host:/usr/local/bin/gate-approve.py >/dev/null
B='su -s /bin/sh -c'
m() { x su -s /bin/sh -c "msp host '$*'" llm 2>&1; }             # as the LLM would: msp HOST VERB
mc() { x su -s /bin/sh -c "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -i /home/llm/.ssh/msp_cron msp-agent@msp-sandbox-host $*" llm 2>&1; }
x su -s /bin/sh -c 'grep -q msp-sandbox-host /home/llm/.ssh/known_hosts' llm; t $? "box learned the hypervisor host key from Ansible (no trust-on-first-use)"
m "'.*/touch /tmp/PWNED/e #'" status >/dev/null 2>&1; x test ! -e /tmp/PWNED; t $? "msp wrapper: sed injection via host name is inert"
m status | grep -q 'sandbox-host'; t $? "read verb works from the box: $(m status | head -n1)"
m /bin/sh | grep -q 'refused: unknown verb'; t $? "shell refused: $(m /bin/sh)"
x su -s /bin/sh -c 'ssh -o BatchMode=yes -i /home/llm/.ssh/msp_interactive msp-agent@msp-sandbox-host' llm 2>&1 | grep -q 'refused: no verb'; t $? "bare login refused"
x su -s /bin/sh -c 'ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -i /home/llm/.ssh/msp_interactive -R 9999:localhost:22 -N msp-agent@msp-sandbox-host' llm 2>&1 | grep -qi 'refused\|prohibited\|closed\|failed'; t $? "port forwarding refused"
m 'status; id' | grep -q 'refused: characters'; t $? "shell metacharacters refused"
m 'journal ssh 5' | grep -qv refused; t $? "journal verb with unit and cap works"
m 'qm-config abc' | grep -q 'refused: vmid'; t $? "read helper validates arguments"
mc 'stage SAFE -- /bin/echo probe' | grep -q 'refused: cron key cannot stage'; t $? "cron key cannot stage"
m 'stage SAFE -- /bin/echo probe' | grep -q 'refused: no recorded shell'; t $? "no stage without a recorded shell"
h sh -c 'mkdir -p /run/msp; echo TEST > /run/msp/recording'          # pretend the Exec seat is open
m 'stage DESTRUCTIVE -- zpool destroy tank' | grep -q 'refused: never-list'; t $? "never-list refused even with DESTRUCTIVE label"
m 'stage SAFE -- rm -rf /tmp/x' | grep -q 'refused: deny-list'; t $? "deny-list refused without DESTRUCTIVE label"
m 'stage BOGUS -- /bin/echo x' | grep -q 'refused: label'; t $? "bad label refused"
o=$(m 'stage SAFE -- /bin/echo gate-ok'); [ "$o" = "staged: SAFE" ]; t $? "stage returns only 'staged: SAFE' (got: $o)"
m 'stage SAFE -- /bin/echo second' | grep -q 'refused: a command is already pending'; t $? "second stage while pending refused"
h test -f /var/spool/msp/staged; t $? "spool holds exactly one staged file"
o=$(h gate-approve.py wrong); echo "$o" | grep -q ABORTED; t $? "wrong code aborts"
h test ! -f /var/spool/msp/staged; t $? "aborted stage is consumed (spool empty)"
m 'stage SAFE -- /bin/echo gate-ok' >/dev/null
o=$(h gate-approve.py); echo "$o" | grep -q '>>>/bin/echo gate-ok<<<' && echo "$o" | grep -q '^gate-ok' && echo "$o" | grep -q 'RESULT rc=0'; t $? "correct code: byte-exact display, runs as argv, RESULT line"
h test ! -f /var/spool/msp/staged; t $? "spool empty after approval"
h journalctl -t msp-gate --no-pager | grep -q 'approved label=SAFE rc=0'; t $? "approval written to the host journal"
m 'read-receipts 1' | grep -q 'command: /bin/echo gate-ok'; t $? "receipt readable by the agent with the literal command"
m 'stage DESTRUCTIVE -- /bin/echo 100' >/dev/null
o=$(h gate-approve.py 999); echo "$o" | grep -q 'target mismatch'; t $? "DESTRUCTIVE: wrong target id aborts"
m 'stage DESTRUCTIVE -- /bin/echo 100' >/dev/null
o=$(h gate-approve.py 100); echo "$o" | grep -q 'RESULT rc=0'; t $? "DESTRUCTIVE: typed target id runs"
h sh -c 'printf "SAFE\n2000-01-01T00:00:00Z\n/bin/echo old\n" > /var/spool/msp/staged'
o=$(h gate-approve.py); echo "$o" | grep -q EXPIRED; t $? "expired stage discarded"
h sh -c 'echo "SAFE" > /var/spool/msp/staged; echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /var/spool/msp/staged; printf "/bin/echo \$(id)\n" >> /var/spool/msp/staged'
o=$(h gate-approve.py); echo "$o" | grep -q 'REFUSED: staged text'; t $? "tampered spool with shell characters refused at the gate"
h sh -c 'sshd -T 2>/dev/null | grep -qiE "^permitrootlogin (prohibit-password|without-password)"'; t $? "root password login off on the hypervisor (key only)"
# recorder + redaction
h sh -c 'rm -f /run/msp/recording; printf "publickey ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n" > /tmp/authinfo; (echo "echo password=hunter2"; sleep 1; echo exit) | SSH_USER_AUTH=/tmp/authinfo msp-shell >/dev/null 2>&1; sleep 1'
h sh -c 'grep -q "password=<REDACTED>" /var/log/msp/rec/*.clean && ! grep -q hunter2 /var/log/msp/rec/*.clean'; t $? "recording: clean copy redacted, secret absent"
h sh -c 'grep -q hunter2 /var/log/msp/rec/raw/*.raw'; t $? "recording: raw copy verbatim, root-only ($(h stat -c %a /var/log/msp/rec/raw))"
h test ! -f /run/msp/recording; t $? "recording ended cleanly"
h journalctl -t msp-shell --no-pager | grep -q 'started by ops@sandbox'; t $? "the Exec seat names the operator from the ssh key that opened it"
m read-all | grep -q 'password=<REDACTED>'; t $? "agent reads the redacted recording via read-all"
# guarantee self-test from the box
x systemctl start msp-check@guarantee.service
x grep -q '^rc=0' /var/lib/msp/state/guarantee.state; t $? "guarantee self-test: $(x sed -n 's/^msg=//p' /var/lib/msp/state/guarantee.state)"
h sh -c 'sed -i "s/^restrict //" /etc/ssh/msp_keys/msp-agent; systemctl reload ssh'   # weaken nothing that matters yet; the ForceCommand still holds
h sh -c 'rm /etc/ssh/sshd_config.d/60-msp.conf; systemctl reload ssh'              # now remove the boundary
x systemctl start msp-check@guarantee.service
x grep -q '^rc=2' /var/lib/msp/state/guarantee.state; t $? "guarantee self-test goes CRIT when the sshd block is removed: $(x sed -n 's/^msg=//p' /var/lib/msp/state/guarantee.state | cut -c1-60)"

# 10 idempotence is checked by the caller (second playbook run: changed=0)
echo "---- $( [ $fail = 0 ] && echo ALL PASS || echo "$fail FAILED" )"
[ $fail = 0 ]
