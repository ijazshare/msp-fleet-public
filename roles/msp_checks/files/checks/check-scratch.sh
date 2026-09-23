#!/bin/sh
# Scratch isolation re-proved daily on the box: a file written inside Scratch must be absent outside.
# OK = isolated. WARN = Scratch unavailable (refused, so nothing leaks). CRIT = a write leaked through.
# ponytail: behavioural (msp-scratch --test as the llm user); no fixture.
. "${MSP_LIB:-/usr/local/lib/msp/msp-lib.sh}"
u=${MSP_LLM_USER:-llm}
out=$(su -s /bin/sh -c 'XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/tmp/msp-scratch-check}; export XDG_RUNTIME_DIR; /usr/local/bin/msp-scratch --test' "$u" 2>&1); rc=$?
case $rc in 0) finish "$OK" "$out";; 97) finish "$WARN" "$out";; *) finish "$CRIT" "$out";; esac
