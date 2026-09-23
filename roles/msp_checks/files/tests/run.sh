#!/bin/sh
# Fixture tests for every check. Prints a PASS/FAIL table; exit 1 if any FAIL.
# A fixture is fixtures/<check>/<case>.out (saved real command output) + <case>.expect
# (line 1: expected exit code, line 2: text the message must contain) and optional <case>.baseline.
here=$(cd "$(dirname "$0")/.." && pwd)
export MSP_LIB="$here/msp-lib.sh"
fail=0; total=0
printf '%-8s %-9s %-24s %s\n' RESULT CHECK CASE GOT
for dir in "$here"/fixtures/*/; do
  check=$(basename "$dir")
  for out in "$dir"*.out; do
    [ -e "$out" ] || continue
    case=$(basename "$out" .out); total=$((total+1))
    exp="$dir$case.expect"; bl="$dir$case.baseline"
    [ -f "$bl" ] || bl="$here/fixtures/baseline.default"
    want_rc=$(sed -n 1p "$exp"); want_txt=$(sed -n 2p "$exp")
    got=$(MSP_FIXTURE="$out" MSP_BASELINE="$bl" sh "$here/checks/check-$check.sh" 2>&1); rc=$?
    if [ "$rc" = "$want_rc" ] && printf '%s' "$got" | grep -qF -- "$want_txt"; then r=PASS; else r=FAIL; fail=$((fail+1)); fi
    printf '%-8s %-9s %-24s rc=%s %s\n' "$r" "$check" "$case" "$rc" "$got"
  done
done
echo "$((total-fail))/$total passed"
[ "$fail" = 0 ]
