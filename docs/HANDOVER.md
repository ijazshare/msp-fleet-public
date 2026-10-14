# Broker build — handover (2026-09-25)

Resume from here. Read this, then `docs/BROKER-SPEC.md` (the full plan, authoritative for Phase 4 onward),
`docs/SPEC.md` §11 (the design record) and `git log --oneline -8`. `AGENTS.md` (with `CLAUDE.md`, `GEMINI.md`,
`OPENCODE.md` symlinked to it) is the operating contract for any harness.

## Status

- Broker Phases 1–3 are implemented, tested and committed (`3fea366`). Go-live Phase 1 is below.
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

## Next up: go-live plan (agreed 2026-10-10; replaces the Phase 4+ order below BROKER-SPEC §60)

Most of go-live is already built: site box, gate, checks. The broker stays off (its default) until Phase 4 here.
BROKER-SPEC Phases 4–9 are not needed to go live.

Phase 0 (done 2026-10-10): venv rebuilt for Python 3.14, PROOF OK, both repos pushed at `bd7892c`.

Phase 1, harden before go-live (code, sandbox only, one commit). Done 2026-10-10, PROOF OK; sandbox proves the
nft drop (privileged containers run nftables), so the SITE check is only the deployed rules. Open: agy's telemetry
switch is only its interactive `/config`, so `msp_tools_enabled` defaults to `[claude, opencode]`; agy is opt-in per
site until its settings key is known. Existing boxes keep an agy already installed (the list never uninstalls).
The SITE --check then showed the broker role ran on every box: it is now `msp_broker` (default false), with
AGENTS.md's broker text and the hypervisors' broker key line only when it is on.
Deployed on the SITE 2026-10-12 (`54e8c22`): --check clean, run, rerun changed=0 on all three hosts. Verified on
the box: llm refused :8006 on both PVEs (root reaches it), llm reaches the internet, GitHub and `msp pve status`;
guarantee rc=0; root password SSH to host.invalid refused; rules loaded again after a reboot. The box has no sudo:
run checks as llm with `runuser -u llm -- CMD`.
In the Scratch window (a user namespace) `msp` failed: root's files show as nobody there and ssh refused
/etc/ssh/ssh_config.d. `msp` now runs `ssh -F none`, so it reads no ssh_config at all.
1. nftables for the `llm` UID, on by default: allow DNS, the public internet (LLM vendor, git remote) and SSH to
   this site's gated hypervisors (`msp`); drop every other private range. Today llm reaches the hypervisor's root
   password SSH and :8006. If the sandbox cannot run nftables, check the rendered rules with `nft -c -f` and prove
   the drop on the SITE.
2. `msp_root_key_only: true` by default (`roles/msp_host/defaults/main.yml`).
3. Drop `script.run` from `examples/group_vars-site.yml` (it is already off by default).
4. Cap `read-all` / `read-new` in `roles/msp_host/files/msp-readverb` to the last N lines with a truncation marker,
   keeping read-new's offset right (5 s of `top` is about 10K tokens sent to the vendor today).
5. Box harnesses: a per-site list of tools for `msp_tools`, telemetry off for each (Claude Code is done in
   `roles/msp_tools/files/bashrc-tools`; agy and OpenCode are not configured).
6. `bootstrap-laptop.sh`: rebuild the venv when `.venv/bin/python3 -c 'import ansible'` fails (a Python upgrade
   left a dead venv that bootstrap skipped because `ansible-playbook` still existed).

Phase 2, exit gate on the SITE (operator, calendar time): the six items in `docs/EXIT-GATE.md`. The 14-day
window started 2026-10-12, when Phase 1 was deployed there; earliest exit 2026-10-26.

Phase 3, first client: `bin/new-site`, group_vars, `ap playbooks/site.yml -l SITE --check --diff`, then the real
run. Commands for real hosts are handed to the operator to run as `ops`; an agent never runs them.

Phase 4, broker, only if one command at a time gets in the way. Fix all of these before enabling it at any client
(review 2026-10-10, each verified in code):
- `approve()` checks status outside the execution lock (service.py ~384 vs ~392): two approvals can both run, and
  a cancel can race an approve.
- AI-declared text reaches the approval card unescaped (msp-approve:54-57; `sanitize()` strips only CSI).
- The card never shows the script bytes, and labels the AI-chosen VM as TARGET although `run_script` runs on the
  hypervisor (proxmox.py).
- Non-HIGH approvals are one keystroke; HIGH uses a fixed phrase the broker returns to the AI. Use a random code
  per approval, as the gate does (D4).
- Plans skip drift checks and fail on Proxmox; a crash mid-run leaves EXECUTING with no receipt; an `accept()`
  OSError exits 0 so systemd never restarts it; a FIFO script path hangs a worker; approver keys are
  cross-multiplied (msp_broker tasks `product`); run-script output skips the host's redaction.
- run-script only with host-verified signatures (`ssh-keygen -Y verify` in msp-execverb; hardware key per D9).
- README decision 4 and SPEC §3/§8 promise no root path from the box; true only while `script.run` stays off.
- `msp_broker` role under `--check` on a box without it: the group task does not create the groups, so the next
  task fails ("Group msp-broker does not exist"). Make the role check-mode clean before enabling it anywhere.
- `msp_broker` with the proxmox adapter unset: "Read the hypervisor host key" fails on an empty `delegate_to`
  (resolved before the block's `when`). Seen on the SITE before the role was gated.

Later, on demand only: UniFi and printers read-only through site-local accounts. Keep ConnectWise, ScreenConnect,
Axcient, M365 and Google credentials off client boxes (MSP-wide or tenant-admin; conflicts with D1).

Each phase: implement → unit/lint/sandbox proof → adversarial review → commit → stop for the user's review.
