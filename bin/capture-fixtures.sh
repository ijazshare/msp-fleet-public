#!/bin/sh
# capture-fixtures.sh: save REAL read-only command output from a Proxmox VE or PBS host so checks can be
# built and tested against it (rule 0). Run as root on each host. Changes nothing. Writes one tarball.
#   sh capture-fixtures.sh            -> /tmp/msp-fixtures-<hostname>-<date>.tar.gz
# Then copy that file to the laptop into ~/pve-fleet/fixtures-in/ . Outputs contain hostnames, VM names,
# pool names, task logs; no passwords or keys. Read the directory before you copy it if in doubt.
set -u
h=$(hostname -s); d=$(date -u +%Y%m%d); out=/tmp/msp-fixtures-$h-$d; mkdir -p "$out"
cap() { # cap NAME CMD... : save stdout+stderr and exit code
  n=$1; shift; "$@" > "$out/$n.out" 2>&1; echo "$?" > "$out/$n.rc"; printf '%-28s rc=%s %s\n' "$n" "$(cat "$out/$n.rc")" "$*"
}
echo "capturing on $h into $out"
# common
cap uname uname -a
cap os cat /etc/os-release
cap systemd-failed systemctl --failed --no-legend --plain
cap list-timers systemctl list-timers --all --no-legend --plain
cap df df -P -l -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs
cap timedatectl timedatectl show
cap chronyc chronyc tracking
cap journal-disk journalctl --disk-usage
cap journald-conf sh -c 'cat /etc/systemd/journald.conf /etc/systemd/journald.conf.d/*.conf 2>/dev/null; ls -d /var/log/journal'
cap lsblk lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL,SERIAL
cap smartctl-scan smartctl --scan
for dev in $(smartctl --scan 2>/dev/null | awk '{print $1}'); do
  b=$(basename "$dev")
  cap "smartctl-H-$b" smartctl -H "$dev"
  cap "smartctl-A-$b" smartctl -A "$dev"
  cap "smartctl-selftest-$b" smartctl -l selftest "$dev"
done
for nv in /dev/nvme[0-9]; do [ -e "$nv" ] && cap "nvme-smart-$(basename "$nv")" nvme smart-log "$nv"; done
cap zpool-status zpool status
cap zpool-status-x zpool status -x
cap zpool-status-p zpool status -p
cap zpool-status-j zpool status -j
cap zpool-list zpool list -H -o name,size,alloc,free,frag,cap,health
cap zpool-get-all zpool get all
cap zfs-list zfs list -o name,used,avail,refer,mountpoint,mounted,canmount
cap zfs-list-space zfs list -o space
cap zfs-snapshots sh -c 'zfs list -t snapshot -o name,creation -s creation | tail -n 200'
cap zfs-arc-max cat /sys/module/zfs/parameters/zfs_arc_max
cap zfs-scrub-schedule sh -c 'cat /etc/cron.d/zfsutils-linux 2>/dev/null; systemctl list-timers "zfs-scrub*" --all --no-legend --plain 2>/dev/null'
cap sanoid-monitor sanoid --monitor-snapshots
cap sanoid-conf cat /etc/sanoid/sanoid.conf
# Proxmox VE
if command -v pveversion >/dev/null; then
  cap pveversion pveversion -v
  cap qm-list qm list
  cap pct-list pct list
  cap pvesm-status pvesm status
  cap storage-cfg cat /etc/pve/storage.cfg
  cap pve-locks sh -c 'grep -H "^lock:" /etc/pve/nodes/*/qemu-server/*.conf /etc/pve/nodes/*/lxc/*.conf'
  cap pve-tasks sh -c 'pvesh get /cluster/tasks --output-format json | head -c 20000'
  cap pve-mount mountpoint /etc/pve
  cap pmxcfs pgrep -a pmxcfs
  cap pveproxy-cert sh -c 'openssl x509 -enddate -subject -noout -in /etc/pve/local/pveproxy-ssl.pem 2>/dev/null || openssl x509 -enddate -subject -noout -in /etc/pve/local/pve-ssl.pem'
  cap boot-tool proxmox-boot-tool status
  cap vzdump-jobs cat /etc/pve/jobs.cfg
  for id in $(qm list 2>/dev/null | awk 'NR>1{print $1}'); do cap "qm-config-$id" qm config "$id"; cap "qm-pending-$id" qm pending "$id"; done
  for id in $(pct list 2>/dev/null | awk 'NR>1{print $1}'); do cap "pct-config-$id" pct config "$id"; done
fi
# Proxmox Backup Server
if command -v proxmox-backup-manager >/dev/null; then
  cap pbs-versions proxmox-backup-manager versions --verbose
  cap pbs-datastore-list proxmox-backup-manager datastore list
  cap pbs-verify-jobs proxmox-backup-manager verify-job list
  cap pbs-prune-jobs proxmox-backup-manager prune-job list
  cap pbs-sync-jobs proxmox-backup-manager sync-job list
  cap pbs-cert proxmox-backup-manager cert info
  cap pbs-tasks sh -c 'proxmox-backup-manager task list --all --output-format json | head -c 20000'
  cap pbs-task-logdir sh -c 'ls -lt /var/log/proxmox-backup/tasks | head -n 30'
  for ds in $(proxmox-backup-manager datastore list --output-format json 2>/dev/null | sed -n 's/.*"name" *: *"\([^"]*\)".*/\1/p'); do
    cap "pbs-gc-status-$ds" proxmox-backup-manager garbage-collection status "$ds"
    cap "pbs-snapshots-$ds" sh -c "proxmox-backup-manager snapshot list $ds 2>/dev/null | head -n 100 || proxmox-backup-client snapshot list --repository $ds | head -n 100"
    p=$(proxmox-backup-manager datastore show "$ds" --output-format json 2>/dev/null | sed -n 's/.*"path" *: *"\([^"]*\)".*/\1/p')
    [ -n "$p" ] && cap "pbs-df-$ds" df -P "$p"
  done
fi
# Samba AD DC (only if this host is one; usually a guest)
if command -v samba-tool >/dev/null && [ -d /var/lib/samba/private ]; then
  cap samba-showrepl samba-tool drs showrepl
  cap samba-fsmo samba-tool fsmo show
  cap samba-level samba-tool domain level show
fi
cap help-qm sh -c 'qm set --help 2>&1 | head -n 5; man -P cat qm 2>/dev/null | grep -A3 -- "--lock"'
cap help-pbm sh -c 'proxmox-backup-manager help 2>&1 | head -n 60'
tar -C /tmp -czf "$out.tar.gz" "$(basename "$out")" && echo "-> $out.tar.gz  ($(du -h "$out.tar.gz" | cut -f1)). Copy this file to the laptop: ~/pve-fleet/fixtures-in/"
