"""SQLite helpers. One file database, no server needed."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, description TEXT,
    required TEXT, nice TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, email TEXT, resume_text TEXT,
    job_id INTEGER, stage TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS memory (
    candidate_id INTEGER, agent TEXT, key TEXT, value TEXT, updated TEXT,
    PRIMARY KEY (candidate_id, agent, key)
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER, agent TEXT, role TEXT, summary TEXT,
    status TEXT DEFAULT 'pending', comment TEXT,
    created TEXT, decided TEXT, decided_by TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, candidate_id INTEGER, agent TEXT, event TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, ref TEXT, title TEXT, text TEXT, vec TEXT, embedder TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, agent TEXT, model TEXT, prompt_tokens INTEGER,
    completion_tokens INTEGER, est_cost REAL, latency_ms INTEGER
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def reset_db() -> None:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    init_db()


def q(sql: str, args: tuple = ()) -> list:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()):
    rows = q(sql, args)
    return rows[0] if rows else None


def run(sql: str, args: tuple = ()) -> int:
    with conn() as c:
        return c.execute(sql, args).lastrowid


# ---- agent memory: every agent keeps its own key/value notes per candidate ----
def memory_set(cid: int, agent: str, key: str, value) -> None:
    run(
        "INSERT OR REPLACE INTO memory VALUES (?,?,?,?,?)",
        (cid, agent, key, json.dumps(value, default=str), now()),
    )


def memory_get(cid: int, agent: str, key: str, default=None):
    row = q1(
        "SELECT value FROM memory WHERE candidate_id=? AND agent=? AND key=?",
        (cid, agent, key),
    )
    return json.loads(row["value"]) if row else default


def memory_all(cid: int) -> dict:
    out: dict = {}
    for r in q("SELECT agent,key,value FROM memory WHERE candidate_id=?", (cid,)):
        out.setdefault(r["agent"], {})[r["key"]] = json.loads(r["value"])
    return out
