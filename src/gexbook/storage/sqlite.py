"""Append-only session snapshots, anchors, decisions and trades stored locally."""

import json
import sqlite3
from pathlib import Path
from gexbook.models import Anchor, Snapshot, jsonable, timestamp


class Store:
    def __init__(self, path="runtime/research.sqlite"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS anchors(session TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, available_at TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, category TEXT, payload TEXT);
        """)

    def lock_anchor(self, anchor: Anchor):
        payload = json.dumps(jsonable(anchor), sort_keys=True)
        existing = self.db.execute(
            "SELECT payload FROM anchors WHERE session=?", (anchor.session,)
        ).fetchone()
        if existing and existing[0] != payload:
            raise ValueError(
                "Session anchor is locked. Use a new session ID for an explicit re-anchor"
            )
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO anchors VALUES (?,?)", (anchor.session, payload))

    def save_snapshot(self, snapshot: Snapshot):
        self.lock_anchor(snapshot.anchor)
        with self.db:
            self.db.execute(
                "INSERT INTO snapshots VALUES (?,?,?)",
                (snapshot.id, snapshot.available_at.isoformat(), json.dumps(jsonable(snapshot))),
            )

    def snapshots(self):
        return [
            Snapshot.from_dict(json.loads(r[0]))
            for r in self.db.execute("SELECT payload FROM snapshots ORDER BY available_at,id")
        ]

    def audit(self, ts, category, payload):
        with self.db:
            self.db.execute(
                "INSERT INTO audit(ts,category,payload) VALUES (?,?,?)",
                (timestamp(ts).isoformat(), category, json.dumps(jsonable(payload))),
            )

    def logs(self, limit=100):
        return [
            {"ts": r[0], "category": r[1], "payload": json.loads(r[2])}
            for r in self.db.execute(
                "SELECT ts,category,payload FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            )
        ]

    def close(self):
        self.db.close()
