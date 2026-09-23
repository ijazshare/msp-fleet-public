#!/bin/sh
# Failed systemd units. Baseline: systemd.expected_failed = "a.service b.timer" (allowed to be failed).
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
expected=$(bl_get systemd.expected_failed "")
tmp=$(mktemp) || exit 3; trap 'rm -f "$tmp" "$tmp.raw"' EXIT
src systemctl --failed --no-legend --plain > "$tmp.raw" || finish "$UNKNOWN" "systemctl --failed did not run"
sed 's/^[^A-Za-z0-9_@.-]*//' "$tmp.raw" > "$tmp"     # drop the marker column if present
bad=""; exp=""
while read -r unit _; do
  [ -z "$unit" ] && continue
  if in_list "$unit" "$expected"; then exp="$exp $unit"; else bad="$bad $unit"; fi
done < "$tmp"
[ -n "$bad" ] && finish "$CRIT" "failed units:$bad"
[ -n "$exp" ] && finish "$OK" "no unexpected failures (expected-failed:$exp)"
finish "$OK" "no failed units"
