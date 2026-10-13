"""Seed the fictional property registry.

All properties are fictional, created for this demo. Run via
scripts/build_index.py (which wipes and rebuilds the DB first).
"""
from __future__ import annotations

from entities.store import EntityStore


def seed(store: EntityStore | None = None) -> EntityStore:
    store = store or EntityStore()
    store.init()
    store.add_property(
        "Maple Grove Apartments",
        "1420 Elm Street, Dayton, OH 45402",
        "multifamily",
        aliases=["maple grove"],
    )
    store.add_property(
        "Harbor Point",
        "88 Harbor Drive, Tampa, FL 33602",
        "mixed-use",
        aliases=["harbor point", "bluefin", "copperline"],
        # tenant aliases -> the property
    )
    store.add_property(
        "Ironworks Industrial Park",
        "Gary, IN",
        "industrial",
        aliases=["ironworks", "ironworks industrial", "great lakes"],
    )
    return store


if __name__ == "__main__":
    s = seed()
    for p in s.list_properties():
        print(p["id"], p["canonical_name"], "-", p["address"],
              f"({p['property_type']})")
