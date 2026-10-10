# AGENTS.md — how any AI harness works in this repository

This file is guidance, not a security boundary. The product's guarantees are enforced by root-owned code and
Unix file permissions on the site boxes (see `docs/SPEC.md`), never by this file. Assume a model can ignore,
misread, or be prompt-injected past any instruction here; the repository's tests exist to catch exactly that.

## Read first, in this order

1. `docs/HANDOVER.md` — current state, decisions already made, the next phase, how to verify.
2. `docs/BROKER-SPEC.md` — the full broker plan (authoritative for Phase 4 onward).
3. `docs/SPEC.md` — the deployed design record; its §11 summarises the broker.
4. `README.md` — layout and the decisions this repo enforces.

## What this repository is

Ansible control repo for the msp-fleet LLM-auditor deployment: one site box per client where an AI works as
the unprivileged `llm` user, gated Proxmox hypervisors, deterministic checks, and a root-owned broker that lets
the AI propose changes a human technician approves before anything executes.

## Hard rules

- Work only inside this repository. Never touch a real host; `sandbox/` is the only place to run things.
  `unifi/` is a separate project: do not read, modify, or depend on it.
- Site data stays out of commits: `inventory/`, `group_vars/<site>.yml`, `host_vars/`, and `captures/` are
  client data and are stripped from the public export by `bin/publish`. Never commit secrets.
- Run before every commit:
      sh roles/msp_checks/files/tests/run.sh
      sh roles/msp_broker/files/tests/run.sh
      bin/lint
      sh sandbox/prove.sh        # fresh containers; idempotence, 150+ behaviour tests, offboard
- One phase per commit (`docs/BROKER-SPEC.md` §77–78): implement, test, adversarially review, commit, then
  stop and report for the human's review. Do not push; the operator pushes.
- Never weaken or delete an existing test to make a change pass (§71).
- Security invariants are non-negotiable: fail closed (§55); known operations run as fixed argv with no shell
  (§63); the LLM never receives credentials (§4.2); no write without approval (§4.1).

## Where the work is

- Broker: `roles/msp_broker/files/broker/` — stdlib Python only; CLIs `msp-action`, `msp-read`, `msp-approve`,
  daemon `msp-brokerd`; policy is root-owned JSON on the box.
- Host boundary: `roles/msp_host/files/` — `msp-dispatch` (forced command), `msp-execverb`, `msp-readverb`,
  `msp-gate`, `msp-shell`.
- Deployment: `playbooks/`, `roles/`; tests: `sandbox/test.sh`, `sandbox/offboard.sh`, `sandbox/prove.sh`.
- Verification entry point: `sh sandbox/prove.sh` must end in `PROOF OK` before any commit.

## Provider neutrality

The broker runtime must never call an LLM or any vendor SDK, and nothing below the scratch environment may
know which harness sent a request (§1, §46, §67). Any terminal-based AI tool must work identically through
`msp-action` / `msp-read` / `msp-approve`; Claude Code, Gemini CLI, OpenCode and local models are all first
class. Steps 1–4 above are also the read order for one of them.
