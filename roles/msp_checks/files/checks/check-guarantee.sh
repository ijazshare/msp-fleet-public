#!/bin/sh
# The guarantee itself, re-tested nightly from the box: for every host, a shell must be refused, the cron key
# must not stage, and a never-list command must be refused. Any pass = CRIT (something removed the boundary).
# ponytail: behavioural (sandbox/test.sh), no fixture: the inputs are live SSH sessions.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
k=/home/llm/.ssh; hosts=/etc/msp/hosts.conf
[ -s "$hosts" ] || finish "$OK" "no hosts declared"
bad=""; n=0
try() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/var/lib/msp/known_hosts -i "$1" "msp-agent@$2" "$3" 2>&1; }
while IFS='=' read -r name addr; do
  case $name in ''|\#*) continue;; esac
  [ -n "$addr" ] || continue; n=$((n+1))
  o=$(try "$k/msp_interactive" "$addr" "/bin/sh");                       case $o in *"refused: unknown verb"*) ;; *) bad="$bad $name:shell";; esac
  o=$(try "$k/msp_cron" "$addr" "stage SAFE -- echo probe");              case $o in *"refused: cron key cannot stage"*) ;; *) bad="$bad $name:cronstage";; esac
  o=$(try "$k/msp_interactive" "$addr" "stage DESTRUCTIVE -- zpool destroy probe"); case $o in *"refused: never-list"*) ;; *) bad="$bad $name:neverlist";; esac
  o=$(try "$k/msp_interactive" "$addr" "status");                         case $o in *refused*|*"Permission denied"*|*"Connection"*) bad="$bad $name:read";; esac
done < "$hosts"
[ -n "$bad" ] && finish "$CRIT" "boundary failed:$bad"
finish "$OK" "$n hosts: shell refused, cron stage refused, never-list refused, reads work"
