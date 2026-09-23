# PBS encryption key escrow (item 3)

If a PVE storage entry for PBS has encryption on, the client-side key lives ONLY on the PVE host at
`/etc/pve/priv/storage/<storage-id>.enc`. Lose the host, lose every backup; verify jobs stay green until then.

Escrow, once per encrypted storage and again after any key change
1. On the PVE host, as root, print the key file: `cat /etc/pve/priv/storage/<storage-id>.enc` (it is a short JSON
   with the encrypted key material and a fingerprint). Also print `pvesm status` and note the storage id.
2. Copy the JSON into the client's vault entry "PBS key <site> <storage-id>" together with the key fingerprint
   line from the storage's config (`grep -A5 "^pbs: <storage-id>" /etc/pve/storage.cfg`).
3. Print it on paper. Put the paper in the client's safe with the offline escrow envelope. Write the date on it.
4. Record in the client repo `handover/pbs-keys.md`: storage id, fingerprint, escrow location, date. Never the key.

Prove the escrow (part of the restore drill)
- On a PVE host that does not have the key (the lab hypervisor, or after `mv` of the live key to a backup name),
  add the PBS storage with the escrowed key file, restore one small guest with the network disconnected, boot it.
  Pass: it boots. Fail: "unable to decrypt" or "fingerprint mismatch"; the escrow is wrong and the live key must be
  re-escrowed before anything else.

Fingerprint check (deterministic, on the PVE host)
- The PBS server fingerprint stored in `storage.cfg` must equal `proxmox-backup-manager cert info` on the PBS.
  A mismatch after a PBS reinstall or certificate change fails every job. This becomes `check-pbs` once PBS
  output has been captured.
