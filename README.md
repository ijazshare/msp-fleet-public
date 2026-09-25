# msp-fleet

Ansible control repo for the LLM-auditor deployment on Proxmox. The private repo (github.com/ijazshare/msp-fleet)
holds everything; github.com/ijazshare/msp-fleet-public is its automated export minus the site data (inventory,
`group_vars/<site>`, `host_vars`, `captures/`), rebuilt by `bin/publish` on every push. Start a site with
`bin/new-site`. Lives at `/srv/pve-fleet`, shared by the laptop users through the `fleet` group.
`sudo ./bootstrap-laptop.sh` sets it up once: the `ops` user and its key, Ansible in `.venv/` inside
the repo (not tracked; the script builds it), `bin/ap` (ansible-playbook from that venv, logged to
`runs/ansible.log`), and `ops <site> <target>`, which runs `bin/ops-launch` as ops.

## Decisions this repo enforces

1. Each site has a dedicated plain-Debian SITE BOX where the LLM runs as the unprivileged `llm` user
   (no sudo). The box's checks run as root from systemd timers (`msp-check@<name>.timer`).
2. Hypervisors get `msp_checks`, plus `msp_host` when `msp_gate` is true (the default): the `msp-agent`
   account behind an sshd `Match` block whose ForceCommand is `msp-dispatch`, sudoers for exactly one read
   helper (`msp-readverb`), `msp-stage`, the gate `msp-gate`, and the recorded root shell `msp-shell`.
3. Reads are free (dispatcher verbs). A change is staged one command at a time and a human approves it at the
   gate inside the recorded Exec shell: no shell metacharacters, run as an argv list, never/deny lists.
4. Root reaches a hypervisor from the laptop (`ops`) only, never from the box.
5. Every session ends with a note quoted from the log, committed and pushed (`msp-end` verifies it).
6. Checks are deterministic and local (heartbeat, systemd, disk, smart, zpool, time, backup, configdump,
   timers). Notifications go out through `msp-notify` (Healthchecks by default; webhook, SNMP trap or a
   command per site). With `msp_snmp: true` the box also serves every check over read-only SNMP for the
   client's own NMS. Notifications are outbound only, site to you; SNMP is polled on the site LAN.
7. Client-specific values live only in `group_vars/<site>.yml` and `host_vars/`, and in the client section of
   the AGENTS.md they generate. Captured host output lives in `captures/<site>-<date>/` and is never shipped
   to a node.

## Layout

    inventory/              the inventory DIRECTORY: one <site>.yml per site (bin/new-site writes it)
    group_vars/<site>.yml   per-site values (never list, guests.exclude, repo URL, operator keys, SNMP)
    host_vars/<host>.yml    per-node values (Healthchecks UUIDs)
    captures/               real host captures, per site, for building checks; never copied to nodes
    roles/msp_checks        checks on every node: msp-lib.sh, checks/, fixtures/, tests/run.sh, msp-run-check,
                            msp-notify, msp-alert, msp-dump, msp-check@ units, heartbeat, checker-broke alert
    roles/msp_snmp          optional snmpd agent: one `extend` per check, read-only, for the site's NMS
    roles/msp_box           llm user, msp wrapper, tmux Plan/Scratch, client repo clone, AGENTS.md, msp-end
    roles/msp_host          dispatcher, stage, gate, recorder + redaction, sudoers read verb, sshd Match
    roles/msp_tools         Claude Code, agy and OpenCode for the llm user
    playbooks/site.yml      build or repair a site (box, hypervisors, box known_hosts from real host keys)
    playbooks/tools.yml     msp_tools alone      playbooks/ping.yml   reachability check
    playbooks/offboard.yml  remove the boundary and accounts from a site, keeping the recordings
    bin/                    ap, ops-launch, publish, publish-data.py, new-site, lint, capture-fixtures.sh
    sandbox/                two Debian 13 + systemd containers (box, hypervisor); prove.sh, test.sh, offboard.sh
    docs/SPEC.md            the design          docs/EXIT-GATE.md   drills and exit criteria

## Proving a change without touching a host

    sh roles/msp_checks/files/tests/run.sh      # every check against its fixtures, runs anywhere
    bin/lint                                    # shellcheck + ansible-lint (profile in .ansible-lint)
    sh sandbox/prove.sh                         # fresh sandbox, site.yml twice (second changed=0), test.sh,
                                                # offboard.sh -> PROOF OK

Rule 0: no check ships without a fixture pair in roles/msp_checks/files/fixtures/<check>/. Fixtures are
captured with `bin/capture-fixtures.sh` (set `MSP_EXCLUDE` to the site's guests.exclude) and kept under
`captures/<site>-<date>/`; sanitized cases that belong to the check (no site data) go in the role.

## On-site monitoring

Every node runs the same checks and writes `/var/lib/msp/state/<check>.state` (rc, message, time). By default
only Healthchecks pings go out. Per site you can add, in `group_vars/<site>.yml`:

    msp_webhook_url: https://...                  # one JSON POST per event
    msp_snmptrap_target: 192.0.2.1                # SNMPv2c trap on a page or a state change
    msp_snmp: true                                # serve the checks over read-only SNMP (snmpd)
    msp_snmp_bind: udp:192.0.2.1:161
    msp_snmp_rocommunity: <community>
    msp_snmp_allowed: 192.0.2.1/24                 # who may use the community

The NMS reads `nsExtendOutputFull` (`1.3.6.1.4.1.8072.1.3.2.3.1.2.<name>`) for the message and
`nsExtendOutput1Exit` (`...3.1.4.<name>`) for the rc (0 OK, 1 WARN, 2 CRIT, 3 unknown), one per check.
Reads are free, changes are not: `msp HOST read-state` gives the agent the same states.

## Scratch

`msp-scratch` overlays the llm home with an in-memory layer inside a user namespace: every tool is signed in,
nothing written survives the window. `check-scratch` re-proves it daily. The laptop sandbox cannot run it
(AppArmor blocks unprivileged user namespaces), so its tests assert the refusal path.

## Run (as ops)

    ap playbooks/ping.yml -l SITE
    ap playbooks/site.yml -l SITE
    ops SITE pve        # Plan (llm on the box) left, Exec (root in msp-shell on that hypervisor) right
    ops SITE lab        # same, second window; TARGET = a gated host's short name, as `msp` uses it
    ops SITE end        # close every Exec window, msp-end on the box, close the session

## Adding a site

    bin/new-site taxoffice 192.0.2.1 192.0.2.1 [192.0.2.1]   # box, pve, optional lab
    $EDITOR group_vars/taxoffice.yml                          # repo URL, never list, operator keys
    ap playbooks/site.yml -l taxoffice

It writes `inventory/taxoffice.yml`, `group_vars/taxoffice.yml` and host_vars stubs; sites never share a file.
Playbooks are written by anyone working in this repo and RUN only by `ops`; a real host only sees a change the
sandbox has already passed.

## Offboarding a site

    ap playbooks/offboard.yml -l taxoffice

Removes the sshd Match block, the `msp-agent` account, dispatcher/gate/recorder and the sudoers line from the
hypervisors, and stops the checks on the box. Recordings, receipts and the config dump are kept under
`/var/log/msp/rec` and `/var/lib/msp/dump` unless `msp_offboard_purge: true`; re-image the box, remove its
deploy key from the client repo, and archive the repo.

## License

AGPL-3.0-or-later; see `LICENSE`. If you run a modified copy as a network service, you must offer its source
to the users of that service.
