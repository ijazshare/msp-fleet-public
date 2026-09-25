import re
import subprocess
import time

from .adapters import Adapter, AdapterError, ExecResult, clamp, sanitize

EXT = {
    "vm_start": ("qm", "start"),
    "vm_shutdown": ("qm", "shutdown"),
    "vm_reboot": ("qm", "reboot"),
    "vm_stop": ("qm", "stop"),
    "ct_start": ("pct", "start"),
    "ct_shutdown": ("pct", "shutdown"),
    "ct_reboot": ("pct", "reboot"),
    "ct_stop": ("pct", "stop"),
}


def _observed():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fields(line):
    return [part for part in re.split(r"\s{2,}", line.strip()) if part]


def parse_qm_list(text):
    guests = []
    pattern = re.compile(r"^\s*(\d+)\s+(.+?)\s{2,}(\S+)\s+(\d+)\s+([\d.]+)\s+(\S+)\s*$")
    for line in text.splitlines()[1:]:
        match = pattern.match(line)
        if match:
            guests.append({"vmid": match.group(1), "name": match.group(2), "status": match.group(3)})
    return guests


def parse_pct_list(text):
    guests = []
    for line in text.splitlines()[1:]:
        parts = _fields(line)
        if len(parts) >= 3 and parts[0].isdigit():
            guests.append({"vmid": parts[0], "name": parts[-1], "status": parts[1]})
    return guests


def parse_status(text):
    match = re.search(r"^status:\s*(\S+)", text, re.M)
    return match.group(1) if match else "unknown"


class ProxmoxAdapter(Adapter):
    name = "proxmox"
    reads = ("vms", "vm", "node", "zpool")

    def __init__(self, paths, policy, runner=None, store=None):
        cfg = policy["adapters"].get("proxmox", {})
        self.host = cfg.get("host", "")
        self.user = cfg.get("user", "msp-agent")
        self.key = cfg.get("key", "")
        self.known_hosts = cfg.get("known_hosts", "")
        self.runner = runner or self._ssh
        self.store = store

    def _ssh(self, argv, stdin=None, timeout=30):
        command = [
            "ssh", "-i", self.key,
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + self.known_hosts,
            "%s@%s" % (self.user, self.host),
        ] + list(argv)
        try:
            proc = subprocess.run(command, input=stdin, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AdapterError("host did not answer in %ss" % timeout)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode == 255:
            raise AdapterError("cannot reach host: %s" % (sanitize(stderr.strip()) or "ssh failed"))
        return proc.returncode, stdout, stderr

    def _run(self, argv, stdin=None, timeout=30, allowed_rc=(0,)):
        rc, out, err = self.runner(argv, stdin=stdin, timeout=timeout)
        if rc not in allowed_rc:
            message = sanitize((err or out).strip()) or "command failed with rc=%d" % rc
            raise AdapterError(message)
        return rc, out, err

    def sync_inventory(self, client, store):
        _, qm_out, _ = self._run(["qm-list"])
        _, pct_out, _ = self._run(["pct-list"])
        _, status_out, _ = self._run(["status"])
        hostname = (status_out.splitlines() or ["unknown"])[0].strip() or "unknown"
        entries = [{
            "id": "node_" + re.sub(r"[^a-z0-9_]", "_", hostname.lower()),
            "client_id": client["client_id"],
            "site_id": client["site_id"],
            "adapter": "proxmox",
            "kind": "node",
            "name": hostname,
            "external_id": hostname,
            "attrs": {},
        }]
        for guest in parse_qm_list(qm_out):
            entries.append({
                "id": "vm_" + guest["vmid"],
                "client_id": client["client_id"],
                "site_id": client["site_id"],
                "adapter": "proxmox",
                "kind": "vm",
                "name": guest["name"],
                "external_id": guest["vmid"],
                "attrs": {"status": guest["status"]},
            })
        for guest in parse_pct_list(pct_out):
            entries.append({
                "id": "ct_" + guest["vmid"],
                "client_id": client["client_id"],
                "site_id": client["site_id"],
                "adapter": "proxmox",
                "kind": "ct",
                "name": guest["name"],
                "external_id": guest["vmid"],
                "attrs": {"status": guest["status"]},
            })
        store.inventory_upsert(entries)

    def read(self, client, verb, args):
        if verb == "vms":
            _, qm_out, _ = self._run(["qm-list"])
            _, pct_out, _ = self._run(["pct-list"])
            return {
                "source": "proxmox_host",
                "observed_at": _observed(),
                "vms": parse_qm_list(qm_out),
                "containers": parse_pct_list(pct_out),
            }
        if verb == "vm":
            vmid, kind = self._target_vmid(args[0] if args else "")
            if kind == "ct":
                _, config, _ = self._run(["pct-config", vmid])
                _, status, _ = self._run(["pct-status", vmid])
            else:
                _, config, _ = self._run(["qm-config", vmid])
                _, status, _ = self._run(["qm-status", vmid])
            return {
                "source": "proxmox_host",
                "observed_at": _observed(),
                "vmid": vmid,
                "kind": kind,
                "status": parse_status(status),
                "config": clamp(config, 8192),
            }
        if verb == "node":
            _, status, _ = self._run(["status"])
            _, version, _ = self._run(["pveversion"])
            return {"source": "proxmox_host", "observed_at": _observed(),
                    "status": clamp(status, 4096), "version": clamp(version, 4096)}
        if verb == "zpool":
            _, out, _ = self._run(["zpool-status"])
            return {"source": "proxmox_host", "observed_at": _observed(), "zpool_status": clamp(out, 8192)}
        raise AdapterError("unknown read verb: %s" % verb)

    def _target_vmid(self, reference):
        if reference.startswith("ct_"):
            return reference[3:], "ct"
        if reference.startswith("vm_"):
            return reference[3:], "vm"
        if reference.isdigit():
            if self.store is not None:
                row = self.store.inventory_get(reference)
                if row and row["adapter"] == "proxmox":
                    return row["external_id"], row["kind"]
            return reference, "vm"
        raise AdapterError("not a guest reference: %s" % reference)

    def precheck(self, operation, target, parameters):
        if operation.startswith("vm."):
            _, out, _ = self._run(["qm-status", target["external_id"]])
            return {"vmid": target["external_id"], "status": parse_status(out)}
        if operation.startswith("ct."):
            _, out, _ = self._run(["pct-status", target["external_id"]])
            return {"vmid": target["external_id"], "status": parse_status(out)}
        if operation == "zpool.scrub":
            pool = parameters["pool"]
            _, out, _ = self._run(["zpool-status"])
            exists = bool(re.search(r"^\s*pool:\s+%s\s*$" % re.escape(pool), out, re.M))
            return {"pool": pool, "exists": exists, "scrub": "scrub in progress" in out}
        if operation == "service.restart":
            unit = parameters["unit"]
            _, out, _ = self._run(["service-status", unit], allowed_rc=(0, 3))
            return {"unit": unit, "active": out.strip() == "active"}
        if operation == "script.run":
            _, out, _ = self._run(["status"])
            return {"node": (out.splitlines() or ["unknown"])[0].strip()}
        return {}

    def preconditions_hold(self, stored, fresh):
        if not stored:
            return True
        for key in ("status", "active", "node"):
            if key in stored:
                return stored.get(key) == fresh.get(key)
        if "exists" in stored:
            return fresh.get("exists") is True
        return True

    def execute(self, operation, target, parameters, plan, script_path=None):
        timeout = plan.get("timeout_seconds", 600) + 30
        if plan["executor"] in EXT:
            tool, action = EXT[plan["executor"]]
            rc, out, err = self._run(["exec", tool, action, target["external_id"]], timeout=timeout)
        elif plan["executor"] == "zpool_scrub":
            rc, out, err = self._run(["exec", "zpool", "scrub", parameters["pool"]], timeout=timeout)
        elif plan["executor"] == "service_restart":
            rc, out, err = self._run(["exec", "systemctl", "restart", parameters["unit"]], timeout=timeout)
        else:
            raise AdapterError("operation is not implemented: %s" % operation)
        return ExecResult(rc=rc, stdout=clamp(out), stderr=clamp(err))

    def run_script(self, interpreter, script_path, timeout_seconds):
        with open(script_path, "rb") as fh:
            data = fh.read()
        rc, out, err = self._run(
            ["run-script", interpreter, str(timeout_seconds)],
            stdin=data,
            timeout=timeout_seconds + 30,
        )
        return ExecResult(
            rc=rc,
            stdout=clamp(out),
            stderr=clamp(err),
            transcript=sanitize(out + err),
        )
