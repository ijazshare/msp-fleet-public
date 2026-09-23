#!/usr/bin/env bash
# bootstrap-laptop.sh — run ONCE, at the laptop, with sudo:   sudo ./bootstrap-laptop.sh
#
# Creates the 'ops' identity that runs Ansible against real hosts. LLM sessions run as your
# normal user and cannot read ops's keys or use ops's SSH. The fleet repo moves to
# /srv/pve-fleet so both users can reach it (Ubuntu home dirs are 750).
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
ME=${SUDO_USER:?run with sudo from your normal user, not as root}
SRC="/home/$ME/pve-fleet"; DST="/srv/pve-fleet"

apt-get install -y tmux git python3-venv

getent group fleet >/dev/null || groupadd fleet
id ops >/dev/null 2>&1 || adduser --disabled-password --gecos "fleet ops" ops
usermod -aG fleet ops
usermod -aG fleet "$ME"

# Shared repo: group fleet, setgid dirs so new files inherit the group.
if [[ -d "$SRC" && ! -L "$SRC" ]]; then mv "$SRC" "$DST"; ln -s "$DST" "$SRC"; fi
mkdir -p "$DST/runs"
chgrp -R fleet "$DST"; chmod -R g+rwX "$DST"; find "$DST" -type d -exec chmod g+s {} +

# One Ansible for both users, inside the shared repo.
if [[ ! -x "$DST/.venv/bin/ansible-playbook" ]]; then
    python3 -m venv "$DST/.venv"
    "$DST/.venv/bin/pip" install -q --upgrade pip
    "$DST/.venv/bin/pip" install -q ansible
    chgrp -R fleet "$DST/.venv"; chmod -R g+rX "$DST/.venv"
fi

# ops's key. Passphrase is prompted; set one.
if [[ ! -f /home/ops/.ssh/id_ed25519 ]]; then
    sudo -u ops mkdir -p /home/ops/.ssh; chmod 700 /home/ops/.ssh
    sudo -u ops ssh-keygen -t ed25519 -f /home/ops/.ssh/id_ed25519 -C "ops@$(hostname)"
fi

cat <<MSG

Done. ops's public key (add it to GitHub, then on each PVE web shell run
  curl -s https://github.com/ijazshare.keys >> /root/.ssh/authorized_keys):

$(cat /home/ops/.ssh/id_ed25519.pub)

Run playbooks as ops:
  sudo -iu ops
  cd /srv/pve-fleet && bin/ap playbooks/ping.yml

Log out and back in once so your own user picks up the 'fleet' group.
MSG
