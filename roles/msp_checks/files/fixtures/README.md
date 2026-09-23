# Fixtures

Every check has at least one fixture pair here: `<case>.out` is saved command output, `<case>.expect` is the
exit code on line 1 and text the message must contain on line 2, `<case>.baseline` (optional) overrides
`baseline.default` for that case. `tests/run.sh` runs them all and prints a table.

`real-*` cases are verbatim captures from a live host via `bin/capture-fixtures.sh`; the others are hand-written
shapes for states we have not seen live yet (degraded pools, failed units). Replace hand-written shapes with real
captures whenever one becomes available. After any major version upgrade, re-capture and re-run before trusting
green.

| Capture | Host | Date | Notes |
| --- | --- | --- | --- |
| real-taxoffice-* | tax office PVE 9.2.11, ZFS 2.4.4, LVM root on NVMe | 2026-09-23 | timers output in EDT; no msp timers installed yet |
| real-SITE-* | N5 Air "SITE" PVE 9.2.3, ZFS root mirror on 2 NVMe, pool `fast` DEGRADED (member REMOVED, disk reports 959 MB and SMART unreadable), pool `tank` 2x20TB | 2026-09-23 | no PBS, no sanoid, no vzdump jobs on this host |
| _captured/<host>-<date>/ | raw shapes kept for checks not written yet (ZFS degraded, SMART unknown, boot-tool with two ESPs, pve tasks JSON) | 2026-09-23 | not run by tests/run.sh |
