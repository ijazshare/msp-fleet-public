#!/usr/bin/env python3
"""Site data for bin/publish: the scrub list and the export gate pattern.

Reads the inventory directory only (never group_vars values beyond what the inventory exposes).
  publish-data.py scrub ROOT   -> git-filter-repo --replace-text lines: addresses, host names, site names
  publish-data.py gate ROOT    -> one extended-regex alternation for `git grep -E` over the exported history
"""
import json
import os
import re
import subprocess
import sys


def inventory(root):
    inv = os.path.join(root, "inventory")
    if not os.path.isdir(inv):
        inv = os.path.join(root, "inventory", "hosts.yml")
    ainv = os.path.join(root, ".venv", "bin", "ansible-inventory")
    if not os.path.exists(ainv):
        ainv = "ansible-inventory"
    p = subprocess.run([ainv, "-i", inv, "--list"], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("publish-data: ansible-inventory failed:\n" + p.stderr.strip())
    return json.loads(p.stdout)


def legacy(root):
    f = os.path.join(root, "publish-legacy-names.txt")
    if not os.path.exists(f):
        return set()
    with open(f) as fh:
        return {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}


def collect(root):
    # ansible-inventory --list is flat: top-level keys are groups, `all` is one of them with a
    # children LIST of names, and every host's vars sit under _meta.hostvars.
    data = inventory(root)
    hv = data.get("_meta", {}).get("hostvars", {})
    hosts = set()
    for name, group in data.items():
        if name == "_meta" or not isinstance(group, dict):
            continue
        for h in group.get("hosts") or []:
            hosts.add(h if isinstance(h, str) else h.get("name"))
    hosts.discard(None)
    sites = {hv[h].get("site") for h in hosts if hv.get(h, {}).get("site")}
    names = {hv[h].get("msp_client_name") for h in hosts if hv.get(h, {}).get("msp_client_name")}
    addrs = {h: hv.get(h, {}).get("ansible_host") for h in hosts}
    return hosts, sites | names | legacy(root), addrs


def e(name):
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", name)


def scrub(root):
    hosts, names, addrs = collect(root)
    lines = []
    for h in sorted(hosts, key=len, reverse=True):
        lines.append(f"{h}==>host.invalid")
    for n in sorted(names, key=len, reverse=True):
        lines.append(f"{n}==>SITE")
    for i, h in enumerate(sorted(hosts), 1):
        a = addrs.get(h)
        if not a:
            continue
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", str(a)):
            lines.append(f"regex:\\b{e(str(a))}\\b==>192.0.2.{i}")
        else:
            lines.append(f"{a}==>host{i}.invalid")
    # Any other private address anywhere in history (old notes named hosts that are not in the inventory
    # today). Documentation range 192.0.2.0/24, so the export gate never has to allow a real range.
    lines += [
        r"regex:\b10\.[0-9]+\.[0-9]+\.[0-9]+\b==>192.0.2.1",
        r"regex:\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+\b==>192.0.2.1",
        r"regex:\b192\.168\.[0-9]+\.[0-9]+\b==>192.0.2.1",
    ]
    return lines


def gate(root):
    hosts, names, addrs = collect(root)
    pats = [
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}",
        r"\b10\.[0-9]+\.[0-9]+\.[0-9]+\b",
        r"\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+\b",
        r"\b192\.168\.[0-9]+\.[0-9]+\b",
        r"hc-ping\.com/[0-9a-f]",
    ]
    for n in sorted(hosts | names, key=len, reverse=True):
        pats.append(r"\b" + e(n) + r"\b")
    for a in addrs.values():
        if a:
            pats.append(r"\b" + e(str(a)) + r"\b")
    return "|".join(pats)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("scrub", "gate"):
        sys.exit(__doc__)
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    if sys.argv[1] == "scrub":
        print("\n".join(scrub(root)))
    else:
        print(gate(root))


if __name__ == "__main__":
    main()