# msp-fleet

Ansible control repo for the LLM-auditor deployment on Proxmox. Private: the inventory names client hosts.
Lives at `/srv/pve-fleet` (github.com/ijazshare/msp-fleet), shared by the laptop users through the `fleet`
group. `sudo ./bootstrap-laptop.sh` sets it up once: the `ops` user and its key, Ansible in `.venv/` inside
the repo (not tracked; the script builds it), `bin/ap` (ansible-playbook from that venv, logged to
`runs/ansible.log`), and `ops <site>`, which runs `bin/ops-launch` as ops.

## Decisions this repo enforces

1. Each site has a dedicated plain-Debian SITE BOX where the LLM runs as the unprivileged `llm` user
   (no sudo). There is no agent CT; `agent_cts` in the inventory is not targeted by `site.yml`.
   The box's checks run as root from systemd timers (`msp-check@<name>.timer`).
2. Hypervisors get `msp_checks`, plus `msp_host` when `msp_gate` is true (the default): the `msp-agent`
   account behind an sshd `Match` block whose ForceCommand is `msp-dispatch`, sudoers for exactly one read
   helper (`msp-readverb`), `msp-stage`, the gate `msp-gate`, and the recorded root shell `msp-shell`.
3. Reads are free (dispatcher verbs). A change is staged one command at a time and a human approves it at the
   gate inside the recorded Exec shell: no shell metacharacters, run as an argv list, never/deny lists.
4. Root reaches a hypervisor from the laptop (`ops`) only, never from the box.
5. Every session ends with a note quoted from the log, committed and pushed (`msp-end` verifies it).
6. Notifications are outbound only (Healthchecks pings), site to you.
7. Client-specific values live only in `group_vars/<site>.yml` and `host_vars/`, and in the client section of
   the AGENTS.md they generate.

## Layout

    inventory/hosts.yml     sites and hosts
    group_vars/<site>.yml   per-site values (never list, guests.exclude, repo URL, operator keys)
    host_vars/<host>.yml    per-node values (Healthchecks UUIDs)
    roles/msp_checks        checks on every node: msp-lib.sh, checks/, fixtures/, tests/run.sh, msp-run-check,
                            msp-check@ units, heartbeat, checker-broke alert, msp-dump config drift
    roles/msp_box           llm user, msp wrapper, tmux Plan/Scratch, client repo clone, AGENTS.md, msp-end
    roles/msp_host          dispatcher, stage, gate, recorder + redaction, sudoers read verb, sshd Match
    roles/msp_tools         Claude Code, agy and OpenCode for the llm user
    playbooks/site.yml      build or repair a site (box, hypervisors, box known_hosts from real host keys)
    playbooks/tools.yml     msp_tools alone          playbooks/ping.yml   reachability check
    bin/                    ap, ops-launch, capture-fixtures.sh
    sandbox/                two Debian 13 + systemd containers (box, hypervisor); prove.sh, test.sh
    docs/SPEC.md            the design              docs/EXIT-GATE.md   drills and exit criteria

## Proving a change without touching a host

    sh roles/msp_checks/files/tests/run.sh      # fixtures, runs anywhere
    sh sandbox/prove.sh                         # fresh sandbox, site.yml twice (second changed=0), test.sh -> PROOF OK

Rule 0: no check ships without a fixture pair in roles/msp_checks/files/fixtures/<check>/.
Fixtures are captured with `bin/capture-fixtures.sh` (set `MSP_EXCLUDE` to the site's guests.exclude).

## Scratch

`msp-scratch` overlays the llm home with an in-memory layer inside a user namespace: every tool is signed in,
nothing written survives the window. `check-scratch` re-proves it daily. The laptop sandbox cannot run it
(AppArmor blocks unprivileged user namespaces), so its tests assert the refusal path.

## Run (as ops)

    ap playbooks/ping.yml -l SITE
    ap playbooks/site.yml -l SITE
    ops SITE            # Plan (llm on the box) left, Exec (root in msp-shell on the lab hypervisor) right
    ops SITE end        # close Exec, msp-end on the box, close the window

## Adding a site

Copy the `SITE` block in `inventory/hosts.yml`, rename, set the addresses, add `group_vars/<site>.yml`
and `host_vars/` for its values. Playbooks are written by anyone working in this repo and RUN only by `ops`;
a real host only sees a change the sandbox has already passed.
