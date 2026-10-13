"""Permission filter.

filter_for_user(user, items) is THE enforcement point where ACL
pre-filtering plugs in: in production, every chunk and every structured
record carries ACL metadata, and the asking user's identity (from OIDC
group resolution) is compiled into the store query itself — never as a
post-filter.

Demo posture: single-tenant demo, all documents fictional and visible.
The filter logs the check and returns items unchanged; the signature is
the contract the real implementation would honor.
"""
from __future__ import annotations

import logging

log = logging.getLogger("deal_copilot.permissions")

DEMO_USER = {"id": "demo", "email": "demo@example.com", "groups": []}


def filter_for_user(user: dict, items: list) -> list:
    """Return only the items `user` is allowed to see.

    user:  {"id", "email", "groups"}.
    items: chunks or structured records, each optionally carrying
           {"acl": {"public": bool, "allow_users": [...],
                    "allow_groups": [...], "deny_users": [...],
                    "deny_groups": [...]}}. Deny wins.

    Demo: no ACLs are attached, so everything is visible; the check is
    still logged so the enforcement point is auditable.
    """
    visible = []
    for it in items:
        acl = (it.get("acl") if isinstance(it, dict) else None) or {}
        if acl.get("public", True):
            visible.append(it)
            continue
        uid, email = user.get("id"), user.get("email")
        groups = set(user.get("groups", []))
        denied = (uid in acl.get("deny_users", []) or
                  email in acl.get("deny_users", []) or
                  bool(groups & set(acl.get("deny_groups", []))))
        if denied:
            continue
        allowed = (uid in acl.get("allow_users", []) or
                   email in acl.get("allow_users", []) or
                   bool(groups & set(acl.get("allow_groups", []))))
        if allowed:
            visible.append(it)
    log.info("permission check: user=%s items_in=%d items_out=%d",
             user.get("id"), len(items), len(visible))
    return visible
