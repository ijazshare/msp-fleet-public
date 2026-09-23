#!/bin/sh
# Declared timers are loaded and active. Baseline: timers.expected = "msp-check@disk.timer ...".
# Reads unit ACTIVE state, not "next run": a timer whose service is running right now has no next run yet.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
expected=$(bl_get timers.expected "")
[ -z "$expected" ] && finish "$OK" "no timers declared in baseline"
tmp=$(mktemp) || exit 3; trap 'rm -f "$tmp"' EXIT
src systemctl list-units --type=timer --all --no-legend --plain > "$tmp" || finish "$UNKNOWN" "systemctl list-units did not run"
missing=""; inactive=""; n=0
for t in $expected; do
  state=$(awk -v u="$t" '$1==u {print $3; exit}' "$tmp")
  if [ -z "$state" ]; then missing="$missing $t"
  elif [ "$state" != "active" ]; then inactive="$inactive $t"
  else n=$((n+1)); fi
done
[ -n "$missing$inactive" ] && finish "$CRIT" "${missing:+missing:$missing}${inactive:+ inactive:$inactive}"
finish "$OK" "$n timers active"
