# Broker build — handover (2026-09-25)

Resume from here. Read this, then `docs/BROKER-SPEC.md` (the full plan, authoritative for Phase 4 onward),
`docs/SPEC.md` §11 (the design record) and `git log --oneline -8`. `AGENTS.md` (with `CLAUDE.md`, `GEMINI.md`,
`OPENCODE.md` symlinked to it) is the operating contract for any harness.

## Status

- Phases 1–3 are implemented, tested and committed; the working tree is clean at `3fea366`.
  - `dcbcc79` broker core: socket, SO_PEERCRED identity, registry, policy, freeze/hash, expiry,
    single-use approval, receipts, mock adapter, Ansible role, 53 unit tests.
  - `4c4ee21` Proxmox adapter over the restricted host path (`exec`/`run-script`, preconditions, drift refusal).
  - `70769ff` script/plan mode, approval cards, AGENTS contract, offboard, README + SPEC §11.
  - `3fea366` per-site broker key pinning and deny-by-default host operation allowlist.
- Phase 4 (UniFi) was **not started**; no edits were made for it.
- **Constraint: do not touch the `unifi/` directory.** It is a separate project, not part of msp-fleet.
  Any UniFi adapter for this repo lives only under `roles/msp_broker/` plus sandbox/tests.

## Decisions taken (do not relitigate without the user)

- Broker policy stays JSON; `client.conf` stays `key = value` until it grows past a handful of fields.
- Broker key: per-site, generated on that site's box, registered only on that site's hosts, `from=` pinned
  when the inventory address is an IP, and narrower than the interactive key (`msp-dispatch` allowlist).
- Host-side operation opt-in is deny-by-default: `/etc/msp/exec.allowlist` from `msp_broker_operations`.
- Development orchestration config is committed (`.opencode/agents/`, `opencode.json`); the orchestrator agent
  has not been exercised yet. Restart opencode, resume, press Tab to switch to `orchestrator`.

## Verify everything

    sh roles/msp_broker/files/tests/run.sh     # 53 unit tests, temp roots only
    sh roles/msp_checks/files/tests/run.sh     # 32 check fixture tests
    bin/lint                                   # shellcheck + ansible-lint
    sh sandbox/prove.sh                        # fresh sandbox: PROOF OK, 153 + 11 tests, idempotent

`ansible-lint` is installed user-level (`~/.local/venvs/ansible-lint` with a wrapper on PATH); the root-owned
`.venv` was not modified. The only lint line left is the informational "Directory expansion discovered 165
files" warning.

## Next up

Phase 4: UniFi read/discovery first (controller status, sites, devices, clients, ports, counters), then
approval-gated `unifi.port.bounce`, `unifi.port.enable/disable`, `unifi.ap.restart`, `unifi.device.restart`.
Credentials root/broker-only in `/etc/msp/secrets/`; stable inventory IDs; SITE-hardware tests (spec §23,
§68) before a Phase 4 commit. Then phases 5–9 in order: printers (SNMP read-only), Windows reads, ConnectWise/
ScreenConnect/Axcient boundaries, M365/Google Workspace read-first, optional UID network isolation.

Each phase: implement → unit/lint/sandbox proof → adversarial review → commit → stop for the user's review.
