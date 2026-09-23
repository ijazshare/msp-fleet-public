#!/bin/sh
# The whole proof loop from a FRESH sandbox. Stops loudly if the playbook fails or is not idempotent.
#   sandbox/prove.sh            -> ends with "PROOF OK" or "PROOF FAILED: <why>"
cd "$(dirname "$0")/.." || exit 1
./sandbox/up.sh >/dev/null || { echo "PROOF FAILED: sandbox did not start"; exit 1; }
ansible-playbook -i sandbox/inventory.yml playbooks/site.yml > /tmp/prove-1.out 2>&1 || { grep -E 'ERROR|fatal' /tmp/prove-1.out | head -5; echo "PROOF FAILED: first playbook run"; exit 1; }
grep -E '^sandbox-' /tmp/prove-1.out
ansible-playbook -i sandbox/inventory.yml playbooks/site.yml > /tmp/prove-2.out 2>&1 || { echo "PROOF FAILED: second playbook run"; exit 1; }
grep -E '^sandbox-' /tmp/prove-2.out
if grep -E '^sandbox-' /tmp/prove-2.out | grep -qv 'changed=0 '; then grep -B8 '^changed:' /tmp/prove-2.out | grep -E '^(TASK|changed)'; echo "PROOF FAILED: second run not idempotent"; exit 1; fi
./sandbox/test.sh > /tmp/sbx.out 2>&1
grep -E 'FAIL|----' /tmp/sbx.out; echo "pass=$(grep -c '^PASS' /tmp/sbx.out)"
grep -q 'ALL PASS' /tmp/sbx.out && echo "PROOF OK" || { echo "PROOF FAILED: tests"; exit 1; }
