#!/bin/sh
# Backup freshness: age of the newest file under the configured backup paths.
# Baseline: backup.paths="/mnt/backup/*" backup.warn_age=93600 backup.crit_age=180000 (seconds).
# Empty backup.paths switches the check off, so sites opt in explicitly.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
paths=$(bl_get backup.paths "")
[ -n "$paths" ] || finish "$OK" "no backup paths configured"
warn=$(bl_get backup.warn_age 93600); crit=$(bl_get backup.crit_age 180000)
if [ -n "${MSP_FIXTURE:-}" ]; then
  newest=$(src cat)
else
  newest=$(src sh -c '
    for g in $1; do
      for p in $g; do
        [ -e "$p" ] || continue
        if [ -d "$p" ]; then find "$p" -maxdepth 1 -type f -printf "%T@ %p\n" 2>/dev/null
        else stat -c "%Y %n" "$p" 2>/dev/null; fi
      done
    done' sh "$paths" | sort -n | tail -n 1)
fi
[ -n "$newest" ] || finish "$CRIT" "no backup file found under: $paths"
ep=${newest%% *}; ep=${ep%%.*}
case $ep in ''|*[!0-9]*) finish "$UNKNOWN" "unreadable newest-backup line: $newest";; esac
f=${newest#* }
age=$(( $(date +%s) - ep )); [ "$age" -lt 0 ] && age=0
if [ "$age" -ge "$crit" ]; then finish "$CRIT" "newest backup is $((age/3600))h old (>= $((crit/3600))h): $f"
elif [ "$age" -ge "$warn" ]; then finish "$WARN" "newest backup is $((age/3600))h old (>= $((warn/3600))h): $f"
else finish "$OK" "newest backup $((age/3600))h old: $f"
fi