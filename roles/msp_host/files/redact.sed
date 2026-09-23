# Redaction rules for the agent-readable recording and read-verb output. Targeted, not generic:
# checksums and long paths must survive. Tested by fixtures/redact.in -> fixtures/redact.expected.
s/\x1b\[[0-9;?]*[A-Za-z]//g
s/\x1b\][^\x07]*\x07//g
s/\r//g
/-----BEGIN [A-Z ]*PRIVATE KEY-----/,/-----END [A-Z ]*PRIVATE KEY-----/c\<REDACTED PRIVATE KEY>
s/(PVEAPIToken=[^=[:space:]]+=)[0-9a-fA-F-]{36}/\1<REDACTED>/g
s/((^|[^A-Za-z0-9])(pass(word|wd|phrase)?|secret|token|api[_-]?key|private[_-]?key|encryption[_-]?key)[[:space:]]*[=:][[:space:]]*)[^[:space:]]+/\1<REDACTED>/Ig
s/^([[:space:]]*(password|passwd|secret|token|encryption-key|master-pubkey)[[:space:]]+)[^[:space:]]+[[:space:]]*$/\1<REDACTED>/I
s/(--(password|passwd|secret|token|key|apikey)[= ])[^[:space:]]+/\1<REDACTED>/g
s/(Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+)[^[:space:]]+/\1<REDACTED>/Ig
s/(PBSClientKey[[:space:]]*[=:][[:space:]]*)[^[:space:]]+/\1<REDACTED>/g
s/([A-Za-z0-9._%+-]+:\/\/[^:@\/[:space:]]+:)[^@[:space:]]+@/\1<REDACTED>@/g
