#!/bin/sh
# Disk SMART health. Input is one block per device:
#   ##DEV /dev/sda   smartctl -H output (prefixed ##H RC) and smartctl -A output (##A RC); NVMe: ##NV /dev/nvme0
# Baseline: smart.wear_warn=90 (NVMe percentage_used that is a WARN). A device whose SMART cannot be read is
# a WARN, never a silent pass. Needs smartmontools on PVE hosts; on a node without it the check is OK-off.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
wear=$(bl_get smart.wear_warn 90)
if [ -n "${MSP_FIXTURE:-}" ]; then
  out=$(src cat)
elif ! command -v smartctl >/dev/null 2>&1; then
  finish "$OK" "smartctl not installed"
else
  out=$(src sh -c '
    for d in $(smartctl --scan 2>/dev/null | awk "{print \$1}"); do
      printf "##DEV %s\n" "$d"
      h=$(smartctl -H "$d" 2>&1); printf "##H %s\n%s\n" "$?" "$h"
      a=$(smartctl -A "$d" 2>&1); printf "##A %s\n%s\n" "$?" "$a"
      unset h a
    done
    for n in /dev/nvme[0-9]*; do
      [ -e "$n" ] || continue
      printf "##NV %s\n" "$n"
      nvme smart-log "$n" 2>&1
    done' 2>&1)
fi
tmp=$(mktemp) || exit 3; trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$out" > "$tmp"
crit=""; warn=""; ok=0; dev=""; hrc=0; hfail=0; nvbad=0; nvwarn=""
emit() { # classify the device we were reading
  [ -n "$dev" ] || return 0
  if [ "$hfail" = 1 ] || [ $((hrc & 8)) -ne 0 ] || [ $((hrc & 16)) -ne 0 ]; then crit="$crit $dev"
  elif [ $((hrc & 32)) -ne 0 ]; then warn="$warn $dev(old-age)"
  elif [ $((hrc & 2)) -ne 0 ]; then warn="$warn $dev(unreadable)"
  elif [ "$nvbad" = 1 ]; then crit="$crit $dev(nvme warning)"
  elif [ -n "$nvwarn" ]; then warn="$warn $dev(wear ${nvwarn}%)"
  elif [ "$hfail" = 2 ]; then warn="$warn $dev(health UNKNOWN)"
  else ok=$((ok+1)); fi
  dev=""; hrc=0; hfail=0; nvbad=0; nvwarn=""
}
while IFS= read -r line; do
  case $line in
    '##DEV '*) emit; dev=${line#\#\#DEV } ;;
    '##H '*) hrc=${line#\#\#H }; case $hrc in *[!0-9]*) hrc=0;; esac ;;
    '##A '*) ;;
    '##NV '*) emit; dev=${line#\#\#NV } ;;
    *'self-assessment test result: FAILED'*) hfail=1 ;;
    *'self-assessment test result: UNKNOWN'*) hfail=2 ;;
    *'critical_warning'*) v=$(printf '%s' "$line" | sed -n 's/.*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'); [ -n "$v" ] && [ "$v" != 0 ] && nvbad=1 ;;
    *'percentage_used'*) p=$(printf '%s' "$line" | sed -n 's/.*:[[:space:]]*\([0-9][0-9]*\)%.*/\1/p')
      [ -n "$p" ] && [ "$p" -ge "$wear" ] && nvwarn=$p ;;
  esac
done < "$tmp"
emit
if [ -n "$crit" ]; then finish "$CRIT" "SMART:$crit${warn:+ (warn:$warn)}"; fi
if [ -n "$warn" ]; then finish "$WARN" "SMART:$warn"; fi
if [ "$ok" -gt 0 ]; then finish "$OK" "$ok SMART devices healthy"; fi
finish "$OK" "no SMART-capable devices"