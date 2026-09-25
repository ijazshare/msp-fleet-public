#!/bin/sh
# ZFS pool health. `zpool status -x` prints only pools with a problem, or "all pools are healthy".
# Baseline: none; any pool not ONLINE is CRIT (degraded, faulted, unavailable, removed).
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
if [ -n "${MSP_FIXTURE:-}" ]; then
  out=$(src cat)
elif ! command -v zpool >/dev/null 2>&1; then
  finish "$OK" "zpool not installed"
else
  out=$(src zpool status -x 2>&1)
fi
case $out in
  *"all pools are healthy"*) finish "$OK" "all pools healthy";;
esac
[ -n "$out" ] || finish "$OK" "no pools"
bad=$(printf '%s\n' "$out" | awk '
  /pool: /{p=$0; sub(/.*pool: */,"",p)}
  /state: /{s=$0; sub(/.*state: */,"",s); if(p!="") printf " %s=%s",p,s; p=""}')
errs=; printf '%s\n' "$out" | grep -q 'errors: No known data errors' || errs=" (data errors)"
if [ -n "$bad" ]; then finish "$CRIT" "pools:$bad$errs"; fi
finish "$CRIT" "$errs${errs:+: }$(printf '%s' "$out" | head -n 1)"