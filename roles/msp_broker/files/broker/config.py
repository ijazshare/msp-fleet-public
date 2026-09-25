import json
import os
import re

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_POLICY_KEYS = {
    "version",
    "client_id",
    "approver_groups",
    "approver_users",
    "reader_groups",
    "approval_ttl_seconds",
    "adapters",
    "script",
    "plans",
}
_SCRIPT_KEYS = {
    "enabled",
    "max_bytes",
    "default_timeout_seconds",
    "max_timeout_seconds",
    "interpreters",
    "forbidden_patterns",
}
_PLANS_KEYS = {"enabled", "max_steps"}
_ADAPTER_KEYS = {"enabled", "operations"}


class ConfigError(Exception):
    pass


class Paths:
    def __init__(self, root=None):
        if root is None:
            root = os.environ.get("MSP_BROKER_ROOT", "/")
        self.root = root.rstrip("/")
        self.etc = self.root + "/etc/msp"
        self.secrets = self.etc + "/secrets"
        self.policy = self.etc + "/policy.json"
        self.client_conf = self.etc + "/client.conf"
        self.inventory_seed = self.etc + "/inventory.json"
        self.state = self.root + "/var/lib/msp-broker"
        self.db = self.state + "/broker.db"
        self.proposals = self.state + "/proposals"
        self.receipts = self.state + "/receipts"
        self.lock = self.state + "/execute.lock"
        self.log = self.root + "/var/log/msp-broker"
        self.run = self.root + "/run/msp"
        self.socket = self.run + "/broker.sock"


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc))


def load_client(path):
    out = {}
    for lineno, line in enumerate(_read(path).splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError("%s line %d: expected key = value" % (path, lineno))
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in ("client_id", "client_name", "site_id"):
            raise ConfigError("%s line %d: unknown key %r" % (path, lineno, key))
        if not _KEY.match(value):
            raise ConfigError("%s line %d: bad value for %s" % (path, lineno, key))
        out[key] = value
    for key in ("client_id", "client_name", "site_id"):
        if key not in out:
            raise ConfigError("%s: missing %s" % (path, key))
    return out


def load_policy(path):
    try:
        policy = json.loads(_read(path))
    except ValueError as exc:
        raise ConfigError("%s: invalid JSON: %s" % (path, exc))
    if not isinstance(policy, dict):
        raise ConfigError("%s: policy must be an object" % path)
    unknown = set(policy) - _POLICY_KEYS
    if unknown:
        raise ConfigError("%s: unknown policy keys: %s" % (path, ", ".join(sorted(unknown))))
    if policy.get("version") != 1:
        raise ConfigError("%s: unsupported policy version" % path)
    if not _KEY.match(str(policy.get("client_id", ""))):
        raise ConfigError("%s: client_id missing or invalid" % path)
    ttl = policy.get("approval_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 30 <= ttl <= 3600:
        raise ConfigError("%s: approval_ttl_seconds must be an integer 30..3600" % path)
    for key in ("approver_groups", "approver_users", "reader_groups"):
        val = policy.get(key)
        if not isinstance(val, list) or not all(isinstance(v, str) and v for v in val):
            raise ConfigError("%s: %s must be a list of names" % (path, key))
    adapters = policy.get("adapters")
    if not isinstance(adapters, dict) or not adapters:
        raise ConfigError("%s: adapters must be a non-empty object" % path)
    for name, cfg in adapters.items():
        if not isinstance(cfg, dict) or set(cfg) - _ADAPTER_KEYS:
            raise ConfigError("%s: adapter %s has invalid keys" % (path, name))
        if not isinstance(cfg.get("enabled"), bool):
            raise ConfigError("%s: adapter %s needs enabled: true/false" % (path, name))
        ops = cfg.get("operations")
        if not isinstance(ops, list) or not all(isinstance(o, str) and o for o in ops):
            raise ConfigError("%s: adapter %s operations must be a list" % (path, name))
    script = policy.get("script", {"enabled": False})
    if not isinstance(script, dict) or set(script) - _SCRIPT_KEYS:
        raise ConfigError("%s: script has invalid keys" % path)
    if script.get("enabled") is True:
        for key, lo, hi in (
            ("max_bytes", 1, 1048576),
            ("default_timeout_seconds", 1, 86400),
            ("max_timeout_seconds", 1, 86400),
        ):
            val = script.get(key)
            if not isinstance(val, int) or isinstance(val, bool) or not lo <= val <= hi:
                raise ConfigError("%s: script.%s must be an integer %d..%d" % (path, key, lo, hi))
        if script["default_timeout_seconds"] > script["max_timeout_seconds"]:
            raise ConfigError("%s: script default timeout exceeds max" % path)
        interp = script.get("interpreters")
        if not isinstance(interp, list) or not interp or not all(
            isinstance(i, str) and re.match(r"^[A-Za-z0-9/_.-]{1,32}$", i) for i in interp
        ):
            raise ConfigError("%s: script.interpreters must be a non-empty list" % path)
        pats = script.get("forbidden_patterns", [])
        if not isinstance(pats, list) or not all(isinstance(p, str) and p for p in pats):
            raise ConfigError("%s: script.forbidden_patterns must be a list" % path)
    plans = policy.get("plans", {"enabled": False})
    if not isinstance(plans, dict) or set(plans) - _PLANS_KEYS:
        raise ConfigError("%s: plans has invalid keys" % path)
    if plans.get("enabled") is True:
        steps = plans.get("max_steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 32:
            raise ConfigError("%s: plans.max_steps must be an integer 1..32" % path)
    return policy
