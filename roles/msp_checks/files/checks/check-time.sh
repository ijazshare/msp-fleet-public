#!/bin/sh
# Clock sync. `timedatectl show` says whether systemd (chrony or systemd-timesyncd) considers the clock
# synced; when chrony is installed its tracking offset feeds the thresholds.
# Baseline: time.warn_ms=200 time.crit_ms=2000 time.allow_unsynced=false.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
warn=$(bl_get time.warn_ms 200); crit=$(bl_get time.crit_ms 2000); allow=$(bl_get time.allow_unsynced false)
if [ -n "${MSP_FIXTURE:-}" ]; then
  out=$(src cat)
elif ! command -v timedatectl >/dev/null 2>&1; then
  finish "$UNKNOWN" "timedatectl not installed"
else
  out=$(src sh -c 'timedatectl show 2>&1; command -v chronyc >/dev/null 2>&1 && chronyc tracking')
fi
sync=$(printf '%s\n' "$out" | sed -n 's/^NTPSynchronized=//p' | head -n 1)
off=$(printf '%s\n' "$out" | sed -n 's/^System time[[:space:]]*:[[:space:]]*\(-\{0,1\}[0-9][0-9.]*\).*/\1/p' | head -n 1)
ms=""
[ -n "$off" ] && ms=$(awk -v s="$off" 'BEGIN{v=s*1000; if(v<0)v=-v; printf "%d", v}')
if [ "$sync" = no ]; then
  case $allow in true|True|yes|1) finish "$OK" "clock not synchronised (allowed by baseline)";; esac
  finish "$CRIT" "clock not synchronised (NTPSynchronized=no)"
fi
[ -n "$sync" ] || finish "$UNKNOWN" "timedatectl gave no NTPSynchronized line"
if [ -n "$ms" ]; then
  [ "$ms" -ge "$crit" ] && finish "$CRIT" "system offset ${ms}ms (>= ${crit}ms)"
  [ "$ms" -ge "$warn" ] && finish "$WARN" "system offset ${ms}ms (>= ${warn}ms)"
  finish "$OK" "NTP synced, offset ${ms}ms"
fi
finish "$OK" "NTP synced"