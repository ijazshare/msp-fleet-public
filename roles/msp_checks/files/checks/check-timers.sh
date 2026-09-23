#!/bin/sh
# Declared timers exist and have a next run. Baseline: timers.expected = "msp-check@disk.timer ...".
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
expected=$(bl_get timers.expected "")
[ -z "$expected" ] && finish "$OK" "no timers declared in baseline"
tmp=$(mktemp) || exit 3; trap 'rm -f "$tmp"' EXIT
src systemctl list-timers --all --no-legend --plain > "$tmp" || finish "$UNKNOWN" "systemctl list-timers did not run"
missing=""; inactive=""; n=0
for t in $expected; do
  next=$(awk -v u="$t" '$(NF-1)==u {print $1; exit}' "$tmp")
  if [ -z "$next" ]; then missing="$missing $t"
  elif [ "$next" = "-" ] || [ "$next" = "n/a" ]; then inactive="$inactive $t"
  else n=$((n+1)); fi
done
[ -n "$missing$inactive" ] && finish "$CRIT" "${missing:+missing:$missing}${inactive:+ inactive:$inactive}"
finish "$OK" "$n timers scheduled"
