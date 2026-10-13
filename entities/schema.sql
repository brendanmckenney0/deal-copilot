-- deal-copilot entity store schema.
-- Rebuilt by scripts/build_index.py (the .db file itself is gitignored).

CREATE TABLE IF NOT EXISTS properties (
    id             INTEGER PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    address        TEXT,
    property_type  TEXT
);

CREATE TABLE IF NOT EXISTS aliases (
    alias       TEXT PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id)
);

CREATE TABLE IF NOT EXISTS extractions (
    id          INTEGER PRIMARY KEY,
    doc_type    TEXT NOT NULL,
    property_id INTEGER REFERENCES properties(id),
    fields_json TEXT NOT NULL,
    source_file TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
