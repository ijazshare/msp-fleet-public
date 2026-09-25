#!/bin/sh
# Offboard proof, run after test.sh on a sandbox that already had site.yml applied: the boundary is removed,
# sshd stays valid, evidence survives, a second run changes nothing. Prints a PASS/FAIL table.
cd "$(dirname "$0")/.." || exit 1
x() { docker exec msp-sandbox "$@"; }
h() { docker exec msp-sandbox-host "$@"; }
fail=0
t() { if [ "$1" = 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=$((fail+1)); fi; }
PATH=.venv/bin:$PATH
ansible-playbook -i sandbox/inventory.yml playbooks/offboard.yml > /tmp/off-1.out 2>&1 || { grep -E 'fatal|ERROR' /tmp/off-1.out | head; echo "---- 1 FAILED"; exit 1; }
ansible-playbook -i sandbox/inventory.yml playbooks/offboard.yml > /tmp/off-2.out 2>&1
grep -E '^sandbox-' /tmp/off-2.out
grep -E '^sandbox-' /tmp/off-2.out | grep -qv 'changed=0 '; [ $? = 1 ]; t $? "second offboard run changes nothing"
h test ! -e /etc/ssh/sshd_config.d/60-msp.conf; t $? "sshd Match block gone"
h sh -c 'id msp-agent' 2>/dev/null; [ $? != 0 ]; t $? "msp-agent account gone"
h sh -c 'sshd -t'; t $? "sshd config still valid"
h test ! -e /usr/local/bin/msp-dispatch && h test ! -e /etc/sudoers.d/msp && h test ! -e /etc/ssh/msp_keys; t $? "dispatcher, sudoers line and agent keys gone"
n=$(h systemctl list-units --type=timer --all --no-legend --plain 'msp-check@*' | grep -c .); [ "$n" = 0 ]; t $? "no msp units left on the hypervisor (got $n)"
h test -d /var/log/msp/rec; t $? "recordings kept (msp_offboard_purge defaults off)"
x su -s /bin/sh -c 'ssh -o BatchMode=yes -o StrictHostKeyChecking=no -i /home/llm/.ssh/msp_interactive msp-agent@msp-sandbox-host status' llm 2>&1 | grep -qiE 'denied|refused|closed|unable'; t $? "agent key no longer opens anything"
n=$(x sh -c "systemctl list-units --type=timer --all --no-legend --plain 'msp-check@*' | awk '\$3==\"active\"' | wc -l"); [ "$n" = 0 ]; t $? "box timers stopped (got $n active)"
echo "---- $( [ $fail = 0 ] && echo ALL PASS || echo "$fail FAILED" )"
[ $fail = 0 ]