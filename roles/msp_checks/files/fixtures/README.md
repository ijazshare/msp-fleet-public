# Fixtures

Every check has at least one fixture pair here: `<case>.out` is saved command output, `<case>.expect` is the
exit code on line 1 and text the message must contain on line 2, `<case>.baseline` (optional) overrides
`baseline.default` for that case. `tests/run.sh` runs them all and prints a table.

Everything under this directory is copied to **every node at every site**. Keep only shapes that carry no site
data: hand-written cases and captures that have been scrubbed. Real captures from a client host go to the
repository's `captures/<host>-<date>/` instead (raw outputs at the top, ready-made cases under `fixtures/`),
where `tests/run.sh` runs them on the laptop only. A capture that proves a bug belongs in `captures/`; a shape
that proves a check belongs here.

`real-sandbox-*` cases are verbatim captures from the throwaway sandbox containers; the others are hand-written
shapes for states we have not seen live yet (degraded pools, failed disks, stale backups). Replace hand-written
shapes with sanitized captures whenever one becomes available. After any major version upgrade, re-capture
(`bin/capture-fixtures.sh`) and re-run before trusting green.

| Capture | Host | Date | Notes |
| --- | --- | --- | --- |
| real-sandbox-* (timers) | Debian 13 sandbox container, `systemctl list-units --type=timer` shapes with one timer stopped | 2026-09-23 | check-timers reads ACTIVE, not next-run |
| captures/SITE-20260923/ | N5 Air "SITE" PVE 9.2.3, ZFS root mirror on 2 NVMe, pool `fast` DEGRADED (member REMOVED, disk reports 959 MB and SMART unreadable), pool `tank` 2x20TB | 2026-09-23 | no PBS, no sanoid, no vzdump jobs on this host |
| captures/taxoffice-20260923/ | tax office PVE 9.2.11, ZFS 2.4.4, LVM root on NVMe | 2026-09-23 | timers output in EDT; no msp timers installed yet |