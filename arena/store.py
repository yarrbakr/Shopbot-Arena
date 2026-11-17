"""Event store: every chat, tool call, guard verdict and reply, in SQLite.

The judge (Phase 2), the round loop and the dashboards all read from here.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id        TEXT PRIMARY KEY,
    created   TEXT NOT NULL,
    source    TEXT NOT NULL,          -- human | red | normal
    customer  TEXT,                   -- who the chatter claims to be (ownership defence)
    round     INTEGER,                -- arena round, NULL for manual chats
    defenses  TEXT NOT NULL           -- JSON snapshot of the switches at session start
);
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    session  TEXT NOT NULL REFERENCES sessions(id),
    actor    TEXT NOT NULL,           -- customer | target | tool | defense
    event    TEXT NOT NULL,           -- message | tool_call | tool_result | reply | verdict | blocked
    data     TEXT NOT NULL            -- JSON
);
CREATE INDEX IF NOT EXISTS events_by_session ON events(session, id);
CREATE TABLE IF NOT EXISTS rounds (
    round     INTEGER PRIMARY KEY,
    started   TEXT NOT NULL,
    finished  TEXT,
    defenses  TEXT NOT NULL,          -- JSON: switches on during this round
    summary   TEXT                    -- JSON: metrics + blue's decision for the next round
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI runs handlers on a thread pool, so one connection guarded by a lock
        # timeout: the round runner and the server write to the same file from two processes
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)

    def new_session(self, source, defenses, customer=None, round_=None):
        sid = uuid.uuid4().hex[:8]
        with self.lock, self.db:
            self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                            (sid, now(), source, customer, round_, json.dumps(defenses)))
        return sid

    def log(self, session, actor, event, data):
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO events (ts, session, actor, event, data) VALUES (?, ?, ?, ?, ?)",
                                  (now(), session, actor, event, json.dumps(data)))
        return cur.lastrowid

    def events(self, session=None, since=0, limit=500, event=None):
        q, args = "SELECT * FROM events WHERE id > ?", [since]
        if session:
            q += " AND session = ?"
            args.append(session)
        if event:
            q += " AND event = ?"
            args.append(event)
        q += " ORDER BY id LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def last_event_id(self):
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]

    def sessions(self, limit=50):
        with self.lock:
            rows = self.db.execute("SELECT * FROM sessions ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "defenses": json.loads(r["defenses"])} for r in rows]

    def start_round(self, defenses):
        with self.lock, self.db:
            last = self.db.execute("SELECT COALESCE(MAX(round), 0) FROM rounds").fetchone()[0]
            self.db.execute("INSERT INTO rounds (round, started, defenses) VALUES (?, ?, ?)",
                            (last + 1, now(), json.dumps(defenses)))
        return last + 1

    def finish_round(self, round_, summary):
        with self.lock, self.db:
            self.db.execute("UPDATE rounds SET finished = ?, summary = ? WHERE round = ?",
                            (now(), json.dumps(summary), round_))

    def update_round_summary(self, round_, summary):
        """Re-scored metrics for a finished round (keeps its finish time)."""
        with self.lock, self.db:
            self.db.execute("UPDATE rounds SET summary = ? WHERE round = ?", (json.dumps(summary), round_))

    def rounds(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM rounds ORDER BY round").fetchall()
        return [{**dict(r), "defenses": json.loads(r["defenses"]),
                 "summary": json.loads(r["summary"]) if r["summary"] else None} for r in rows]

    def session(self, sid):
        with self.lock:
            r = self.db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        return {**dict(r), "defenses": json.loads(r["defenses"])} if r else None
