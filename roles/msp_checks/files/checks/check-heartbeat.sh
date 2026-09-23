#!/bin/sh
# Pure liveness: always OK. Its Healthchecks ping going quiet means this node or its timers are dead.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
finish "$OK" "alive $(src cat /proc/uptime | cut -d' ' -f1)s uptime"
