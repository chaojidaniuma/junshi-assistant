# -*- coding: utf-8 -*-
"""SQLite 持久化：threads / turns / items / memory / approvals。

替代 state.json：支持查询、回溯、并发安全（事务）、多会话。
零外部依赖（sqlite3 标准库）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .item import Item

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    target_name TEXT NOT NULL,
    target_meta TEXT DEFAULT '{}',
    status TEXT DEFAULT 'active',
    style_profile_id TEXT,
    config_override TEXT DEFAULT '{}',
    created_at REAL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    thread_id TEXT REFERENCES threads(id),
    trigger_hash TEXT,
    trigger_text TEXT,
    status TEXT,
    error TEXT,
    created_at REAL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_turns_hash ON turns(thread_id, trigger_hash);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    turn_id TEXT,
    thread_id TEXT,
    type TEXT NOT NULL,
    data TEXT,
    seq INTEGER,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_items_turn ON items(turn_id, seq);
CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    category TEXT,
    key TEXT,
    value TEXT,
    source_turn_id TEXT,
    created_at REAL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    turn_id TEXT,
    rule_id TEXT,
    reply TEXT,
    variants TEXT,
    best INTEGER,
    decision TEXT DEFAULT 'pending',
    decided_by TEXT,
    decided_at REAL,
    created_at REAL
);
"""


class Store:
    """线程安全的 SQLite 封装。所有写操作走同一把锁。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        """短连接：事务提交/回滚 + 用完即关（Windows 文件锁兼容）。"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ---- threads ----
    def upsert_thread(self, t: dict) -> str:
        now = time.time()
        with self._lock, self._conn() as conn:
            if not t.get("id"):
                t["id"] = uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO threads(id,target_name,target_meta,status,style_profile_id,"
                "config_override,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET target_name=excluded.target_name,"
                "target_meta=excluded.target_meta,status=excluded.status,"
                "config_override=excluded.config_override,updated_at=excluded.updated_at",
                (t["id"], t["target_name"], json.dumps(t.get("target_meta") or {}, ensure_ascii=False),
                 t.get("status", "active"), t.get("style_profile_id"),
                 json.dumps(t.get("config_override") or {}, ensure_ascii=False),
                 t.get("created_at", now), now))
            return t["id"]

    def get_thread(self, thread_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        return self._thread_from_row(row) if row else None

    def find_thread_by_target(self, target_name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM threads WHERE target_name=? AND status!='archived' "
                "ORDER BY updated_at DESC LIMIT 1", (target_name,)).fetchone()
        return self._thread_from_row(row) if row else None

    def list_threads(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM threads ORDER BY updated_at DESC").fetchall()
        return [self._thread_from_row(r) for r in rows]

    @staticmethod
    def _thread_from_row(row) -> dict:
        return {"id": row["id"], "target_name": row["target_name"],
                "target_meta": json.loads(row["target_meta"] or "{}"),
                "status": row["status"], "style_profile_id": row["style_profile_id"],
                "config_override": json.loads(row["config_override"] or "{}"),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    # ---- turns ----
    def create_turn(self, thread_id: str, trigger_hash: str, trigger_text: str) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO turns(id,thread_id,trigger_hash,trigger_text,status,created_at) "
                "VALUES(?,?,?,?, 'running', ?)",
                (tid, thread_id, trigger_hash, trigger_text[:2000], time.time()))
        return tid

    def set_turn_status(self, turn_id: str, status: str, error: str | None = None) -> None:
        done = time.time() if status in ("completed", "failed", "aborted") else None
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE turns SET status=?, error=?, completed_at=COALESCE(?,completed_at) "
                "WHERE id=?", (status, error, done, turn_id))

    def get_turn(self, turn_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
        return dict(row) if row else None

    def find_turn_by_hash(self, thread_id: str, trigger_hash: str,
                          statuses: list[str] | None = None) -> dict | None:
        q = "SELECT * FROM turns WHERE thread_id=? AND trigger_hash=?"
        args: list = [thread_id, trigger_hash]
        if statuses:
            q += f" AND status IN ({','.join('?' * len(statuses))})"
            args.extend(statuses)
        with self._conn() as conn:
            row = conn.execute(q + " ORDER BY created_at DESC LIMIT 1", args).fetchone()
        return dict(row) if row else None

    def abort_stale_turns(self) -> int:
        """启动时把上次遗留的 running/waiting_approval turn 标记 aborted，
        让对应消息下轮可重试（崩溃恢复，不丢消息）。"""
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE turns SET status='aborted', error='restart', "
                "completed_at=? WHERE status IN ('running','waiting_approval')",
                (time.time(),))
            return cur.rowcount

    # ---- items ----
    def add_item(self, item: Item) -> Item:
        with self._lock, self._conn() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM items WHERE turn_id=?",
                (item.turn_id or "",)).fetchone()[0]
            item.seq = seq
            conn.execute(
                "INSERT INTO items(id,turn_id,thread_id,type,data,seq,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (item.id, item.turn_id, item.thread_id, item.type,
                 json.dumps(item.data, ensure_ascii=False), seq, item.ts))
        return item

    def turn_items(self, turn_id: str) -> list[Item]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM items WHERE turn_id=? ORDER BY seq", (turn_id,)).fetchall()
        return [Item.from_row(r) for r in rows]

    # ---- approvals ----
    def create_approval(self, turn_id: str, rule_id: str, reply: str,
                        variants: list[str], best: int) -> str:
        aid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO approvals(id,turn_id,rule_id,reply,variants,best,decision,created_at) "
                "VALUES(?,?,?,?,?,?, 'pending', ?)",
                (aid, turn_id, rule_id, reply, json.dumps(variants, ensure_ascii=False),
                 best, time.time()))
        return aid

    def pending_approvals(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT a.*, t.thread_id, t.trigger_text FROM approvals a "
                "JOIN turns t ON t.id=a.turn_id WHERE a.decision='pending' "
                "ORDER BY a.created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["variants"] = json.loads(d["variants"] or "[]")
            out.append(d)
        return out

    def decide_approval(self, approval_id: str, decision: str, by: str = "human") -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE approvals SET decision=?, decided_by=?, decided_at=? WHERE id=?",
                (decision, by, time.time(), approval_id))
        return dict(row)

    # ---- memory ----
    def set_memory(self, thread_id: str, category: str, key: str, value: str,
                   turn_id: str | None = None) -> None:
        now = time.time()
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM memory WHERE thread_id=? AND category=? AND key=?",
                (thread_id, category, key)).fetchone()
            if row:
                conn.execute("UPDATE memory SET value=?, updated_at=?, source_turn_id=? WHERE id=?",
                             (value, now, turn_id, row["id"]))
            else:
                conn.execute(
                    "INSERT INTO memory(id,thread_id,category,key,value,source_turn_id,"
                    "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], thread_id, category, key, value, turn_id, now, now))

    def get_memory(self, thread_id: str, category: str | None = None) -> list[dict]:
        q = "SELECT * FROM memory WHERE thread_id=?"
        args: list = [thread_id]
        if category:
            q += " AND category=?"
            args.append(category)
        with self._conn() as conn:
            rows = conn.execute(q + " ORDER BY updated_at DESC", args).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, memory_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM memory WHERE id=?", (memory_id,))
