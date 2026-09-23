# pve-fleet

Ansible control repo for the LLM-auditor deployment. Private: the inventory names client hosts.

Ansible lives in `~/.venvs/ansible`, exposed as `ansible*` in `~/.local/bin`.

## Decisions this repo enforces

1. Three boxes per site, identical everywhere: PVE host, agent CT, docs repo.
   Client-specific content lives only in `group_vars/<site>.yml`, the client
   section of that site's AGENTS.md, `qcap.conf` on the host, and the docs repo remotes.
2. The agent CT holds only: the restricted PVE key, a read-only cron key, the docs
   deploy key, and whatever sign-in state the LLM tool keeps in the llm user's home.
3. Root reaches the PVE from the laptop only. Never from the agent CT.
4. Reads are free (dispatcher verbs). Mutations go through the gate: one command per
   step, no shell metacharacters, run as an argv array, no `eval`.
5. Every session ends with a note quoted from the log, committed and pushed.
6. Notifications are outbound only, site to you.
7. Laptop side: `ops <site>` launcher, overlay network, an OSC 52 terminal.

## Layout

    inventory/hosts.yml     sites and hosts
    group_vars/all.yml      fleet defaults
    group_vars/<site>.yml   per-site overrides (create when needed)
    playbooks/ping.yml      reachability check
    roles/msp_checks        deterministic checks: msp-lib.sh, checks/, fixtures/, tests/run.sh,
                            msp-run-check runner, msp-check@ units, heartbeat + checker-broke alert
    roles/msp_box           (next) llm/ops/checks users, tmux Plan/Exec/Scratch, repo clone, AGENTS.md
    roles/msp_host          (next) recorder, gate, dispatcher, sshd Match block, sudoers, self-test
    playbooks/site.yml      build or repair a site
    sandbox/                throwaway Debian 12 + systemd container; up.sh, test.sh, fake Healthchecks

## Proving a change without touching a host

    sh roles/msp_checks/files/tests/run.sh                          # fixtures, runs anywhere
    sandbox/up.sh                                                   # fresh container
    ansible-playbook -i sandbox/inventory.yml playbooks/site.yml    # apply (run twice: second is changed=0)
    sandbox/test.sh                                                 # behavioural table, must end ALL PASS

Rule 0: no check ships without a fixture pair in roles/msp_checks/files/fixtures/<check>/.
You review by reading the tables, not the scripts.

## Run

    cd ~/pve-fleet
    ansible-inventory --graph
    ansible-playbook playbooks/ping.yml
    ansible-playbook playbooks/ping.yml -l SITE      # one site only

## Homelab topology (2026-09-23)

    host.invalid   N5 Air, production hypervisor (192.0.2.3). Monitored only.
    host.invalid   Lenovo Core 7, lab hypervisor. Every destructive test runs here. PBS VM lives here.
    host.invalid   N305, the site box (plain Debian 12).
    UNAS 2        192.0.2.1, NFS: vzdump target and PBS datastore export.

## Adding a site

Copy the `SITE` block in `inventory/hosts.yml`, rename, set the two addresses,
add `group_vars/<site>.yml` for anything that differs.

## Who runs what

- Playbooks and roles are written by whoever (or whatever) works in this repo.
- They are RUN only by the `ops` user, whose SSH key is the one authorized on hosts.
  LLM sessions run as the normal user and cannot use it. Set up once with
  `sudo ./bootstrap-laptop.sh` at the laptop.
- Every run appends to `runs/ansible.log`, which the writer reads back to fix the next iteration.
- Roles are tested first against a throwaway sandbox (a disposable CT or local VM) that has
  its own throwaway key. Real hosts only see a playbook the sandbox has already passed.
