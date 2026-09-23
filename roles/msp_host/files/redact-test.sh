#!/bin/sh
# Redaction fixture test: sed rules applied to fixtures/redact.in must equal fixtures/redact.expected.
here=$(cd "$(dirname "$0")" && pwd)
out=$(sed -E -f "${MSP_RULES:-$here/redact.sed}" "$here/fixtures/redact.in")
if [ "$out" = "$(cat "$here/fixtures/redact.expected")" ]; then echo "PASS redact fixture"; exit 0; fi
echo "FAIL redact fixture"; printf '%s\n' "$out" | diff - "$here/fixtures/redact.expected"; exit 1
