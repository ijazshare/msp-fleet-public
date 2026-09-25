import grp
import pwd
from dataclasses import dataclass

from .adapters import Refused


@dataclass(frozen=True)
class Actor:
    uid: int
    name: str
    can_read: bool
    can_approve: bool


def actor_for(uid, gid, policy, pw_lookup=pwd.getpwuid, group_list=grp.getgrall):
    try:
        name = pw_lookup(uid).pw_name
    except KeyError:
        raise Refused("unknown uid %d" % uid)
    groups = set()
    for group in group_list():
        if group.gr_gid == gid or name in group.gr_mem:
            groups.add(group.gr_name)
    approvers = set(policy.get("approver_groups", []))
    readers = set(policy.get("reader_groups", []))
    can_approve = uid == 0 or name in policy.get("approver_users", []) or bool(groups & approvers)
    can_read = can_approve or uid == 0 or bool(groups & readers)
    return Actor(uid=uid, name=name, can_read=can_read, can_approve=can_approve)
