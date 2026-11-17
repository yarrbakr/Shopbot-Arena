"""TufShop's persistent, mutable world: accounts, orders, reviews, tickets, messages, refunds, coupons.

This is the shop's shared state in SQLite, so one session's writes are visible to the next session and
to other agents. It is deliberately separate from the event log (`arena/store.py`): the Store records
*what happened* and the judge reads that log, while the World holds *the current state of the shop*.

Phase A seeds and reads accounts, orders, reviews and coupons; the ticket/message/refund tables exist
now so the write-tools (Phase C) and the internal agent (Phase D) have somewhere to land.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from arena import config

SEED_PATH = Path(__file__).parent / "world_seed.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    name           TEXT PRIMARY KEY,
    role           TEXT NOT NULL DEFAULT 'customer',   -- customer | staff
    email          TEXT,
    loyalty_points INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orders (
    id               TEXT PRIMARY KEY,
    customer_name    TEXT NOT NULL,
    product          TEXT NOT NULL,
    price            REAL NOT NULL,
    quantity         INTEGER NOT NULL,
    color            TEXT,
    shipping_address TEXT,
    payment_method   TEXT,
    status           TEXT NOT NULL DEFAULT 'open'       -- open | cancelled | refunded
);
CREATE TABLE IF NOT EXISTS reviews (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT NOT NULL,
    author  TEXT,
    text    TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    account  TEXT,
    order_id TEXT,
    subject  TEXT,
    status   TEXT NOT NULL DEFAULT 'open',              -- open | resolved
    created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    author    TEXT,
    role      TEXT,                                      -- customer | staff
    text      TEXT NOT NULL,
    created   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refunds (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    amount   REAL NOT NULL,
    status   TEXT NOT NULL DEFAULT 'paid',              -- paid | pending
    created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coupons (
    code    TEXT PRIMARY KEY,
    percent INTEGER NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);
"""

ORDER_FIELDS = ("customer_name", "product", "price", "quantity", "color", "shipping_address",
                "payment_method", "status")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class World:
    """The shop's live state. Pass ``":memory:"`` for a throwaway world in tests."""

    def __init__(self, path, seed=True):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
        if seed:
            self.ensure_seed()

    def ensure_seed(self, data=None):
        """Idempotent and non-destructive: every row is inserted only if absent, so the canonical
        seed appears in a fresh world while any runtime change (a new review, a moved address, spent
        loyalty points) survives reopening. Reviews seed only when the table is empty."""
        data = data if data is not None else json.loads(SEED_PATH.read_text(encoding="utf-8"))
        with self.lock, self.db:
            for a in data.get("accounts", []):
                self.db.execute(
                    "INSERT OR IGNORE INTO accounts (name, role, email, loyalty_points) VALUES (?, ?, ?, ?)",
                    (a["name"], a.get("role", "customer"), a.get("email"), a.get("loyalty_points", 0)))
            for oid, o in data.get("orders", {}).items():
                self.db.execute(
                    "INSERT OR IGNORE INTO orders (id, customer_name, product, price, quantity, color, "
                    "shipping_address, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (oid, o["customer_name"], o["product"], o["price"], o["quantity"], o.get("color"),
                     o.get("shipping_address"), o.get("payment_method")))
            for c in data.get("coupons", []):
                self.db.execute("INSERT OR IGNORE INTO coupons (code, percent, active) VALUES (?, ?, ?)",
                                (c["code"], c["percent"], int(c.get("active", True))))
            if not self.db.execute("SELECT 1 FROM reviews LIMIT 1").fetchone():
                for r in data.get("reviews", []):
                    self.db.execute("INSERT INTO reviews (product, author, text, created) VALUES (?, ?, ?, ?)",
                                    (r["product"], r.get("author"), r["text"], now()))

    # ---- orders ----

    @staticmethod
    def _order(row):
        # Same shape the old static DATA order had (keyed by id elsewhere, no id field inside).
        return {k: row[k] for k in ORDER_FIELDS}

    def order(self, order_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM orders WHERE id = ?", (str(order_id),)).fetchone()
        return self._order(row) if row else None

    def orders(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM orders").fetchall()
        return {row["id"]: self._order(row) for row in rows}

    def customers(self):
        with self.lock:
            rows = self.db.execute("SELECT DISTINCT customer_name FROM orders ORDER BY customer_name").fetchall()
        return [r["customer_name"] for r in rows]

    def set_order_status(self, order_id, status):
        with self.lock, self.db:
            self.db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, str(order_id)))

    def set_shipping_address(self, order_id, address):
        with self.lock, self.db:
            self.db.execute("UPDATE orders SET shipping_address = ? WHERE id = ?", (address, str(order_id)))

    # ---- reviews ----

    def reviews_for(self, product):
        with self.lock:
            rows = self.db.execute("SELECT text FROM reviews WHERE product = ? ORDER BY id", (product,)).fetchall()
        return [r["text"] for r in rows]

    def add_review(self, product, text, author=None):
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO reviews (product, author, text, created) VALUES (?, ?, ?, ?)",
                                  (product, author, text, now()))
        return cur.lastrowid

    # ---- accounts ----

    def account(self, name):
        with self.lock:
            row = self.db.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def accounts(self, role=None):
        q = "SELECT * FROM accounts" + (" WHERE role = ?" if role else "") + " ORDER BY name"
        with self.lock:
            rows = self.db.execute(q, (role,) if role else ()).fetchall()
        return [dict(r) for r in rows]

    def loyalty(self, name):
        acct = self.account(name)
        return acct["loyalty_points"] if acct else None

    def adjust_loyalty(self, name, delta):
        """Add delta (may be negative) to an account's points, floored at 0. Returns the new total or None."""
        if self.account(name) is None:
            return None
        with self.lock, self.db:
            self.db.execute("UPDATE accounts SET loyalty_points = MAX(0, loyalty_points + ?) WHERE name = ?",
                            (delta, name))
        return self.loyalty(name)

    # ---- coupons ----

    def coupon(self, code):
        with self.lock:
            row = self.db.execute("SELECT * FROM coupons WHERE code = ? AND active = 1", (code,)).fetchone()
        return dict(row) if row else None

    # ---- tickets & messages (the channel the internal agent reads) ----

    def open_ticket(self, account, subject, order_id=None):
        with self.lock, self.db:
            cur = self.db.execute(
                "INSERT INTO tickets (account, order_id, subject, status, created) VALUES (?, ?, ?, 'open', ?)",
                (account, str(order_id) if order_id else None, subject, now()))
        return cur.lastrowid

    def add_message(self, ticket_id, author, role, text):
        with self.lock, self.db:
            cur = self.db.execute(
                "INSERT INTO messages (ticket_id, author, role, text, created) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, author, role, text, now()))
        return cur.lastrowid

    def ticket(self, ticket_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    def open_tickets(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM tickets WHERE status = 'open' ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def messages_for(self, ticket_id):
        with self.lock:
            rows = self.db.execute("SELECT * FROM messages WHERE ticket_id = ? ORDER BY id", (ticket_id,)).fetchall()
        return [dict(r) for r in rows]

    def resolve_ticket(self, ticket_id):
        with self.lock, self.db:
            self.db.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))

    # ---- refunds ----

    def record_refund(self, order_id, amount, status="paid"):
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO refunds (order_id, amount, status, created) VALUES (?, ?, ?, ?)",
                                  (str(order_id), amount, status, now()))
        return cur.lastrowid

    def refunds_for(self, order_id):
        with self.lock:
            rows = self.db.execute("SELECT * FROM refunds WHERE order_id = ? ORDER BY id", (str(order_id),)).fetchall()
        return [dict(r) for r in rows]


# Shared, file-backed world for the running app (the round runner and the server see the same shop).
# Tests construct their own World(":memory:"); this one is only touched when the real tools run.
WORLD = World(config.WORLD_DB)
