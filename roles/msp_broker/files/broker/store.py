import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    request_uid INTEGER NOT NULL,
    adapter TEXT NOT NULL,
    operation TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    parameters TEXT NOT NULL,
    risk TEXT NOT NULL,
    status TEXT NOT NULL,
    plan TEXT NOT NULL,
    execution_hash TEXT NOT NULL,
    confirmation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    approved_at TEXT,
    approver TEXT,
    execution_started_at TEXT,
    execution_finished_at TEXT,
    result_rc INTEGER,
    result_summary TEXT,
    pre_state TEXT,
    post_state TEXT,
    ai_declared TEXT
);
CREATE INDEX IF NOT EXISTS proposals_status ON proposals (status, created_at);

CREATE TABLE IF NOT EXISTS receipts (
    proposal_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    receipt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    adapter TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    external_id TEXT NOT NULL,
    attrs TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inventory_name ON inventory (name);
"""

JSON_FIELDS = ("parameters", "plan", "pre_state", "post_state", "ai_declared")
COLUMNS = {
    "proposal_id", "client_id", "site_id", "request_uid", "adapter", "operation", "target_id", "target_name",
    "parameters", "risk", "status", "plan", "execution_hash", "confirmation", "created_at",
    "expires_at", "approved_at", "approver", "execution_started_at", "execution_finished_at",
    "result_rc", "result_summary", "pre_state", "post_state", "ai_declared",
}


class StoreError(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = path

    def connect(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self):
        conn = self.connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _row(row):
        if row is None:
            return None
        out = dict(row)
        for field in JSON_FIELDS:
            if out.get(field) is not None:
                out[field] = json.loads(out[field])
        return out

    @staticmethod
    def _encode(fields):
        out = dict(fields)
        for field in JSON_FIELDS:
            if field in out and out[field] is not None:
                out[field] = json.dumps(out[field], sort_keys=True, separators=(",", ":"))
        return out

    def insert_proposal(self, fields):
        unknown = set(fields) - COLUMNS
        if unknown:
            raise StoreError("unknown proposal columns: %s" % ", ".join(sorted(unknown)))
        cols = sorted(fields)
        encoded = self._encode(fields)
        sql = "INSERT INTO proposals (%s) VALUES (%s)" % (", ".join(cols), ", ".join("?" for _ in cols))
        conn = self.connect()
        try:
            conn.execute(sql, [encoded[c] for c in cols])
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise StoreError(str(exc))
        finally:
            conn.close()

    def get(self, proposal_id):
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        finally:
            conn.close()
        return self._row(row)

    def update(self, proposal_id, **fields):
        unknown = set(fields) - COLUMNS
        if unknown:
            raise StoreError("unknown proposal columns: %s" % ", ".join(sorted(unknown)))
        if not fields:
            return
        encoded = self._encode(fields)
        cols = sorted(fields)
        sql = "UPDATE proposals SET %s WHERE proposal_id = ?" % ", ".join("%s = ?" % c for c in cols)
        conn = self.connect()
        try:
            conn.execute(sql, [encoded[c] for c in cols] + [proposal_id])
            conn.commit()
        finally:
            conn.close()

    def list_by_status(self, status, limit=50):
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        finally:
            conn.close()
        return [self._row(r) for r in rows]

    def list_recent(self, limit=50):
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
        return [self._row(r) for r in rows]

    def expire_stale(self, now):
        conn = self.connect()
        try:
            cur = conn.execute(
                "UPDATE proposals SET status = 'EXPIRED' WHERE status = 'PROPOSED' AND expires_at <= ?",
                (now,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def add_receipt(self, proposal_id, created_at, receipt):
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO receipts (proposal_id, created_at, receipt) VALUES (?, ?, ?)",
                (proposal_id, created_at, json.dumps(receipt, sort_keys=True, separators=(",", ":"))),
            )
            conn.commit()
        finally:
            conn.close()

    def get_receipt(self, proposal_id):
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT receipt FROM receipts WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        finally:
            conn.close()
        return json.loads(row["receipt"]) if row else None

    def inventory_upsert(self, entries):
        conn = self.connect()
        try:
            for entry in entries:
                conn.execute(
                    "INSERT OR REPLACE INTO inventory (id, client_id, site_id, adapter, kind, name, external_id, attrs)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry["id"],
                        entry["client_id"],
                        entry["site_id"],
                        entry["adapter"],
                        entry["kind"],
                        entry["name"],
                        entry["external_id"],
                        json.dumps(entry.get("attrs", {}), sort_keys=True, separators=(",", ":")),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def inventory_get(self, target_id):
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM inventory WHERE id = ?", (target_id,)).fetchone()
        finally:
            conn.close()
        return self._inv(row)

    def inventory_by_name(self, name):
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM inventory WHERE name = ?", (name,)).fetchall()
        finally:
            conn.close()
        return [self._inv(r) for r in rows]

    def inventory_list(self):
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM inventory ORDER BY id").fetchall()
        finally:
            conn.close()
        return [self._inv(r) for r in rows]

    @staticmethod
    def _inv(row):
        if row is None:
            return None
        out = dict(row)
        out["attrs"] = json.loads(out["attrs"])
        return out
