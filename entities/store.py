"""Entity store: canonical property registry + structured doc records.

Demo-scale entity resolution: a SQLite registry of canonical properties
with an alias table. resolve(name) is deterministic — normalized exact
alias match first, then alias-substring fallback — and returns a
property_id or None. Production would add LLM-assisted resolution with
human confirmation; this deterministic core is the auditable foundation
of that.

Tables (see schema.sql):
  properties(id, canonical_name UNIQUE, address, property_type)
  aliases(alias UNIQUE, property_id FK)   -- alias stored normalized
  extractions(id, doc_type, property_id FK, fields_json, source_file,
              created_at)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("ENTITY_DB",
                         str(Path(__file__).resolve().parent.parent
                             / "data" / "entities.db"))

# Suffixes stripped before alias matching ("the maple grove apartments"
# -> "maple grove").
_SUFFIXES = ("apartments", "apartment", "the", "llc", "inc", "co")


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    sql = (Path(__file__).resolve().parent / "schema.sql").read_text()
    conn = _connect(db_path)
    conn.executescript(sql)
    conn.commit()
    conn.close()


def normalize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    tokens = [t for t in re.sub(r"\s+", " ", name).strip().split(" ")
              if t not in _SUFFIXES]
    return " ".join(tokens)


class EntityStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DB_PATH

    def init(self):
        init_db(self.db_path)

    def add_property(self, canonical_name: str, address: str = "",
                     property_type: str = "",
                     aliases: list[str] | None = None) -> int:
        conn = _connect(self.db_path)
        cur = conn.execute(
            "INSERT OR IGNORE INTO properties (canonical_name, address, property_type)"
            " VALUES (?, ?, ?)", (canonical_name, address, property_type))
        if cur.lastrowid:
            prop_id = cur.lastrowid
        else:
            prop_id = conn.execute(
                "SELECT id FROM properties WHERE canonical_name = ?",
                (canonical_name,)).fetchone()["id"]
        all_aliases = {normalize(canonical_name)}
        for a in aliases or []:
            all_aliases.add(normalize(a))
        for a in all_aliases:
            if a:
                conn.execute("INSERT OR IGNORE INTO aliases (alias, property_id)"
                             " VALUES (?, ?)", (a, prop_id))
        conn.commit()
        conn.close()
        return prop_id

    def resolve(self, name: str) -> int | None:
        """Deterministic normalized alias matching. Returns property_id or None."""
        norm = normalize(name)
        if not norm:
            return None
        conn = _connect(self.db_path)
        row = conn.execute(
            "SELECT property_id FROM aliases WHERE alias = ?",
            (norm,)).fetchone()
        if row is None:
            # substring fallback: a stored alias contained in the input
            # (e.g. "Bluefin Coffee Roasters LLC" contains alias "bluefin")
            for a in conn.execute(
                    "SELECT alias, property_id FROM aliases ORDER BY length(alias) DESC"):
                if a["alias"] and a["alias"] in norm:
                    row = a
                    break
        conn.close()
        return row["property_id"] if row else None

    def get_property(self, property_id: int) -> dict | None:
        conn = _connect(self.db_path)
        row = conn.execute(
            "SELECT id, canonical_name, address, property_type FROM properties"
            " WHERE id = ?", (property_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_properties(self) -> list[dict]:
        conn = _connect(self.db_path)
        rows = conn.execute(
            "SELECT id, canonical_name, address, property_type FROM properties"
            " ORDER BY canonical_name").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def save_extraction(self, doc_type: str, fields: dict,
                        property_id: int | None,
                        source_file: str = "") -> int:
        conn = _connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO extractions (doc_type, property_id, fields_json, source_file)"
            " VALUES (?, ?, ?, ?)",
            (doc_type, property_id, json.dumps(fields), source_file))
        doc_id = cur.lastrowid or 0
        conn.commit()
        conn.close()
        return doc_id

    def get_extractions(self, property_id: int | None = None,
                        doc_type: str | None = None) -> list[dict]:
        conn = _connect(self.db_path)
        q = "SELECT * FROM extractions WHERE 1=1"
        params: list = []
        if property_id is not None:
            q += " AND property_id = ?"
            params.append(property_id)
        if doc_type:
            q += " AND doc_type = ?"
            params.append(doc_type)
        rows = conn.execute(q + " ORDER BY id DESC", params).fetchall()
        conn.close()
        out = []
        for r in rows:
            d = dict(r)
            d["fields"] = json.loads(d["fields_json"])
            out.append(d)
        return out

    def find_aliases_in(self, text: str) -> list[int]:
        """Property ids whose alias appears in the text (longest alias wins
        per property). Used by the query router for entity detection."""
        norm = normalize(text)
        conn = _connect(self.db_path)
        hits: dict[int, str] = {}
        for a in conn.execute(
                "SELECT alias, property_id FROM aliases ORDER BY length(alias) DESC"):
            if a["alias"] and a["alias"] in norm:
                hits.setdefault(a["property_id"], a["alias"])
        conn.close()
        return list(hits)
