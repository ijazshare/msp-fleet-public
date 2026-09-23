#!/bin/sh
# Config drift: run msp-dump; a change is a WARN finding (recorded, not paged), so you see what moved.
# ponytail: no fixture for this one, it is proven behaviourally in sandbox/test.sh (edit a file -> exactly one WARN).
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
out=$(/usr/local/bin/msp-dump 2>&1); rc=$?
[ "$rc" != 0 ] && finish "$UNKNOWN" "msp-dump failed: $out"
case $out in
  unchanged)      finish "$OK" "config unchanged";;
  initialized*)   finish "$OK" "config dump $out";;
  changed:*)      finish "$WARN" "config $out";;
  *)              finish "$UNKNOWN" "msp-dump said: $out";;
esac
