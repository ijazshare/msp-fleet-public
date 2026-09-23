# msp-lib.sh: shared by every check. POSIX sh, source it. No pipefail (not POSIX): capture to files.
MSP_BASELINE=${MSP_BASELINE:-/etc/msp/baseline.conf}
OK=0 WARN=1 CRIT=2 UNKNOWN=3

# bl_get KEY DEFAULT: value of KEY=VALUE from baseline.conf, last one wins, '#' lines ignored.
bl_get() {
  v=$(grep -v '^[[:space:]]*#' "$MSP_BASELINE" 2>/dev/null | sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" | tail -n 1)
  if [ -n "$v" ]; then printf '%s\n' "$v"; else printf '%s\n' "$2"; fi
}
# in_list WORD "a b c": true if WORD is one of them.
in_list() { for _w in $2; do [ "$_w" = "$1" ] && return 0; done; return 1; }
# src CMD...: the check's input. MSP_FIXTURE=file replaces the command with saved output (tests).
src() { if [ -n "${MSP_FIXTURE:-}" ]; then cat "$MSP_FIXTURE"; else "$@"; fi; }
# finish RC MESSAGE: print one line "STATUS message" and exit RC. Every check ends here.
finish() {
  case $1 in 0) s=OK;; 1) s=WARN;; 2) s=CRIT;; *) s=UNKNOWN;; esac
  printf '%s %s\n' "$s" "$2"; exit "$1"
}
