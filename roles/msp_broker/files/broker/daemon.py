import json

from .adapters import Refused
from .config import Paths, load_client, load_policy
from .mock import MockAdapter
from .service import BrokerService, utcnow
from .store import Store


def seed_inventory(paths, client, store):
    try:
        with open(paths.inventory_seed, "r", encoding="utf-8") as fh:
            entries = json.load(fh)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        raise Refused("inventory seed is unreadable: %s" % exc)
    if not isinstance(entries, list):
        raise Refused("inventory seed must be a list")
    clean = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise Refused("inventory entry must be an object")
        missing = {"id", "kind", "name", "adapter", "external_id"} - set(entry)
        if missing:
            raise Refused("inventory entry missing: %s" % ", ".join(sorted(missing)))
        if entry["adapter"] not in ("mock", "proxmox"):
            raise Refused("inventory entry has unknown adapter: %s" % entry["adapter"])
        clean.append({
            "id": entry["id"],
            "client_id": client["client_id"],
            "site_id": client["site_id"],
            "adapter": entry["adapter"],
            "kind": entry["kind"],
            "name": entry["name"],
            "external_id": str(entry["external_id"]),
            "attrs": entry.get("attrs", {}),
        })
    store.inventory_upsert(clean)


def build_service(paths=None, clock=utcnow):
    paths = paths or Paths()
    policy = load_policy(paths.policy)
    client = load_client(paths.client_conf)
    if client["client_id"] != policy["client_id"]:
        raise Refused("client.conf and policy.json disagree on client_id")
    store = Store(paths.db)
    store.init()
    seed_inventory(paths, client, store)
    adapters = {}
    if policy["adapters"].get("mock", {}).get("enabled"):
        adapters["mock"] = MockAdapter(paths)
    if policy["adapters"].get("proxmox", {}).get("enabled"):
        from .proxmox import ProxmoxAdapter
        adapters["proxmox"] = ProxmoxAdapter(paths, policy)
    return BrokerService(paths, policy, client, store, adapters, clock=clock)
