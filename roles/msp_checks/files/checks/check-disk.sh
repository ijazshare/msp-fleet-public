#!/bin/sh
# Filesystem usage. Baseline: disk.warn=80 disk.crit=90 disk.ignore="/boot/efi /mnt/x".
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
warn=$(bl_get disk.warn 80); crit=$(bl_get disk.crit 90); ignore=$(bl_get disk.ignore "")
tmp=$(mktemp) || exit 3; trap 'rm -f "$tmp" "$tmp.b"' EXIT
src df -P -l -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs > "$tmp" || finish "$UNKNOWN" "df did not run"
sed 1d "$tmp" > "$tmp.b"
c=""; w=""; n=0
while read -r _ _ _ _ pct mnt; do
  [ -z "$mnt" ] && continue
  in_list "$mnt" "$ignore" && continue
  pct=${pct%\%}; n=$((n+1))
  if [ "$pct" -ge "$crit" ]; then c="$c $mnt=$pct%"; elif [ "$pct" -ge "$warn" ]; then w="$w $mnt=$pct%"; fi
done < "$tmp.b"
[ -n "$c" ] && finish "$CRIT" "over ${crit}%:$c${w:+ (warn:$w)}"
[ -n "$w" ] && finish "$WARN" "over ${warn}%:$w"
finish "$OK" "$n filesystems under ${warn}%"
