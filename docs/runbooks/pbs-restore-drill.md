# PBS restore drill (item 3)

Purpose: prove a backup restores, using only what a stranger would have. Quarterly, and once before v1 exit.
Read-only against production data; the restored guest never touches the live network.

Preconditions
- A PBS datastore with at least one backup of the guest you will restore. Pick a small guest that is NOT a
  domain controller (restoring a DC from an image is a USN rollback; see the never list).
- The PBS storage entry on the PVE host is encrypted or not; if encrypted, you need the escrowed key
  (see pbs-key-escrow.md). Do the drill WITH the escrowed copy, not the live one.
- An unused VMID (9999) and a bridge with no uplink, or the guest's network device set to disconnected.

Steps (web UI unless noted; write the start time)
1. Datacenter > Storage > the PBS storage > Backups. Select the newest backup of the guest. Restore.
2. Dialog: Storage = the ZFS pool, VM ID = 9999, tick Unique, untick Start after restore. Restore.
3. When the task finishes, open its log and record the duration. Pass: task ends OK. Fail: any error; stop, keep the log.
4. VM 9999 > Hardware > Network Device > Edit > tick Disconnect. Do this BEFORE starting it.
5. Start VM 9999. Console. Log in with a local account (domain login will not work offline).
   Pass: the operating system boots and the service on it runs (`systemctl status <svc>` or the app opens).
   Fail: no boot, no login, service missing.
6. Stop VM 9999. More > Remove, tick Purge.
7. Write the attestation in the client repo, `sessions/<date>-restore-drill.md`, with the fields below.

Attestation fields
- date (UTC), operator, guest restored, backup date, PBS datastore, key used (escrowed copy: yes/no)
- restore duration, boot ok (yes/no), service ok (yes/no), surprises (anything you had to figure out)
- client-summary: one sentence with no hostnames. outcome: informational. visibility: client.

Fail conditions that end the drill and become a session note with outcome=planned
- restore task error; guest does not boot; escrowed key does not decrypt; the guest was started with network attached.
