import hashlib
import json
import re
from dataclasses import dataclass

RISK_ORDER = {"LOW": 0, "DISRUPTIVE": 1, "HIGH": 2, "FORBIDDEN": 3}

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_UNIT_RE = re.compile(r"^[A-Za-z0-9@._:-]{1,64}$")
_POOL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class PlanError(Exception):
    pass


def _v_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10**9


def _v_vmid(value):
    return _v_int(value) and 1 <= value <= 10**9


def _v_port(value):
    return _v_int(value) and 1 <= value <= 65535


def _v_seconds(value):
    return _v_int(value) and 1 <= value <= 3600


def _v_message(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and all(32 <= ord(c) < 127 for c in value)


def _v_unit(value):
    return isinstance(value, str) and bool(_UNIT_RE.match(value))


def _v_pool(value):
    return isinstance(value, str) and bool(_POOL_RE.match(value))


KINDS = {
    "int": _v_int,
    "vmid": _v_vmid,
    "port": _v_port,
    "seconds": _v_seconds,
    "message": _v_message,
    "unit": _v_unit,
    "pool": _v_pool,
}


@dataclass(frozen=True)
class Operation:
    name: str
    adapter: str
    risk: str
    target_kinds: tuple
    params: tuple
    executor: str
    confirm: str = ""
    description: str = ""


def _op(name, adapter, risk, kinds, params, executor, confirm="", description=""):
    return Operation(name, adapter, risk, kinds, params, executor, confirm, description)


REGISTRY = {
    "mock.echo": _op("mock.echo", "mock", "LOW", ("mock",), (("message", "message"),), "echo",
                     description="Record a message in the mock adapter state."),
    "mock.noop": _op("mock.noop", "mock", "LOW", ("mock",), (), "noop",
                     description="Do nothing; proves the approval path."),
    "mock.fail": _op("mock.fail", "mock", "LOW", ("mock",), (), "fail",
                     description="Fail deliberately; test-only."),
    "mock.sleep": _op("mock.sleep", "mock", "DISRUPTIVE", ("mock",), (("seconds", "seconds"),), "sleep",
                      description="Sleep for a bounded time; test-only."),
    "mock.halt": _op("mock.halt", "mock", "HIGH", ("mock",), (), "noop", "HALT {target_name}",
                     description="Test-only high-risk operation."),
    "vm.start": _op("vm.start", "proxmox", "LOW", ("vm",), (), "vm_start",
                    description="Start a virtual machine."),
    "vm.shutdown": _op("vm.shutdown", "proxmox", "DISRUPTIVE", ("vm",), (), "vm_shutdown",
                       description="Ask a virtual machine to shut down."),
    "vm.reboot": _op("vm.reboot", "proxmox", "DISRUPTIVE", ("vm",), (), "vm_reboot",
                     description="Reboot a virtual machine."),
    "vm.stop": _op("vm.stop", "proxmox", "HIGH", ("vm",), (), "vm_stop", "STOP {target_name}",
                   description="Hard-stop a virtual machine."),
    "ct.start": _op("ct.start", "proxmox", "LOW", ("ct",), (), "ct_start",
                    description="Start a container."),
    "ct.shutdown": _op("ct.shutdown", "proxmox", "DISRUPTIVE", ("ct",), (), "ct_shutdown",
                       description="Ask a container to shut down."),
    "ct.reboot": _op("ct.reboot", "proxmox", "DISRUPTIVE", ("ct",), (), "ct_reboot",
                     description="Reboot a container."),
    "ct.stop": _op("ct.stop", "proxmox", "HIGH", ("ct",), (), "ct_stop", "STOP {target_name}",
                   description="Hard-stop a container."),
    "zpool.scrub": _op("zpool.scrub", "proxmox", "DISRUPTIVE", ("node",), (("pool", "pool"),), "zpool_scrub",
                       description="Start a scrub on a ZFS pool."),
    "service.restart": _op("service.restart", "proxmox", "DISRUPTIVE", ("node",), (("unit", "unit"),),
                           "service_restart", description="Restart one allowlisted systemd unit."),
    "vm.destroy": _op("vm.destroy", "proxmox", "FORBIDDEN", ("vm",), (), "vm_destroy",
                      description="Destroy a virtual machine. Not available."),
    "ct.destroy": _op("ct.destroy", "proxmox", "FORBIDDEN", ("ct",), (), "ct_destroy",
                      description="Destroy a container. Not available."),
}


def get_operation(name):
    return REGISTRY.get(name)


def validate_params(op, params):
    if not isinstance(params, dict):
        raise PlanError("parameters must be an object")
    allowed = {name for name, _ in op.params}
    unknown = set(params) - allowed
    if unknown:
        raise PlanError("unknown parameter(s): %s" % ", ".join(sorted(unknown)))
    clean = {}
    for name, kind in op.params:
        if name not in params:
            raise PlanError("missing parameter: %s" % name)
        value = params[name]
        if not KINDS[kind](value):
            raise PlanError("parameter %s is not a valid %s" % (name, kind))
        clean[name] = value
    return clean


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_hash(plan):
    return hashlib.sha256(canonical(plan).encode("utf-8")).hexdigest()


def confirmation_phrase(op, target_name):
    template = op.confirm or "APPROVE {target_name}"
    return template.format(target_name=target_name)


def build_plan(client, adapter, operation, target, parameters, executor, timeout_seconds,
               preconditions, steps=None, script=None, ai_declared=None):
    plan = {
        "version": 1,
        "client_id": client["client_id"],
        "site_id": client["site_id"],
        "adapter": adapter,
        "operation": operation,
        "target_id": target["id"],
        "target_name": target["name"],
        "target_external_id": target["external_id"],
        "parameters": parameters,
        "executor": executor,
        "timeout_seconds": timeout_seconds,
        "preconditions": preconditions,
    }
    if steps is not None:
        plan["steps"] = steps
    if script is not None:
        plan["script"] = script
    if ai_declared is not None:
        plan["ai_declared"] = ai_declared
    return plan
