"""SQLite storage for Vera contexts, conversations, and suppression state."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_local = threading.local()
_db_lock = threading.RLock()

def get_db(db_path: str = "vera.db") -> sqlite3.Connection:
    if not hasattr(_local, "connections"):
        _local.connections = {}
    if db_path not in _local.connections:
        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        _local.connections[db_path] = conn
    return _local.connections[db_path]

def init_db(db_path: str = "vera.db") -> None:
    with _db_lock:
        conn = get_db(db_path)
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS contexts (
                scope TEXT NOT NULL,
                context_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                payload TEXT NOT NULL,
                delivered_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (scope, context_id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                merchant_id TEXT,
                customer_id TEXT,
                trigger_id TEXT,
                state TEXT NOT NULL DEFAULT 'NEW',
                goal TEXT,
                auto_reply_count INTEGER DEFAULT 0,
                unanswered_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                from_role TEXT NOT NULL,
                message TEXT NOT NULL,
                action TEXT,
                rationale TEXT,
                cta TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );

            CREATE TABLE IF NOT EXISTS suppressions (
                key TEXT PRIMARY KEY,
                scope TEXT,
                entity_id TEXT,
                expires_at TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS merchant_state (
                merchant_id TEXT PRIMARY KEY,
                auto_reply_count INTEGER DEFAULT 0,
                is_suppressed INTEGER DEFAULT 0,
                suppression_expires_at TEXT,
                last_interaction TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_contexts_scope ON contexts(scope);
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
            """)

class Storage:
    def __init__(self, db_path: str = "vera.db"):
        self.db_path = db_path
        init_db(self.db_path)

    def save_context(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: Optional[str] = None
    ) -> Tuple[bool, int, str]:
        """
        Store context. Returns (accepted, current_version, ack_id_or_reason).
        Rejects stale or equal version with 409 semantics.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                row = conn.execute(
                    "SELECT version FROM contexts WHERE scope = ? AND context_id = ?",
                    (scope, context_id),
                ).fetchone()
                if row:
                    cur_ver = row["version"]
                    if cur_ver >= version:
                        return False, cur_ver, "stale_version"
                    conn.execute(
                        """
                        UPDATE contexts 
                        SET version = ?, payload = ?, delivered_at = ?, updated_at = ?
                        WHERE scope = ? AND context_id = ?
                        """,
                        (version, payload_json, delivered_at or now_iso, now_iso, scope, context_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO contexts (scope, context_id, version, payload, delivered_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (scope, context_id, version, payload_json, delivered_at or now_iso, now_iso),
                    )
            return True, version, f"ack_{context_id}_v{version}"

    def get_context(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db(self.db_path)
        row = conn.execute(
            "SELECT version, payload, delivered_at FROM contexts WHERE scope = ? AND context_id = ?",
            (scope, context_id),
        ).fetchone()
        if not row:
            return None
        return {
            "version": row["version"],
            "payload": json.loads(row["payload"]),
            "delivered_at": row["delivered_at"],
        }

    def get_all_contexts_by_scope(self, scope: str) -> Dict[str, Dict[str, Any]]:
        conn = get_db(self.db_path)
        rows = conn.execute(
            "SELECT context_id, version, payload, delivered_at FROM contexts WHERE scope = ?",
            (scope,),
        ).fetchall()
        result = {}
        for r in rows:
            result[r["context_id"]] = {
                "version": r["version"],
                "payload": json.loads(r["payload"]),
                "delivered_at": r["delivered_at"],
            }
        return result

    def count_contexts(self) -> Dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        conn = get_db(self.db_path)
        rows = conn.execute("SELECT scope, COUNT(*) as c FROM contexts GROUP BY scope").fetchall()
        for r in rows:
            if r["scope"] in counts:
                counts[r["scope"]] = r["c"]
        return counts

    def get_or_create_conversation(
        self, conversation_id: str, merchant_id: Optional[str] = None, customer_id: Optional[str] = None, trigger_id: Optional[str] = None
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
                ).fetchone()
                if row:
                    return dict(row)
                conn.execute(
                    """
                    INSERT INTO conversations (conversation_id, merchant_id, customer_id, trigger_id, state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'NEW', ?, ?)
                    """,
                    (conversation_id, merchant_id, customer_id, trigger_id, now_iso, now_iso),
                )
                return {
                    "conversation_id": conversation_id,
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "trigger_id": trigger_id,
                    "state": "NEW",
                    "goal": None,
                    "auto_reply_count": 0,
                    "unanswered_count": 0,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }

    def update_conversation(self, conversation_id: str, **kwargs) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        kwargs["updated_at"] = now_iso
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [conversation_id]
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute(f"UPDATE conversations SET {fields} WHERE conversation_id = ?", values)

    def record_message(
        self,
        conversation_id: str,
        from_role: str,
        message: str,
        action: Optional[str] = None,
        rationale: Optional[str] = None,
        cta: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT INTO messages (conversation_id, from_role, message, action, rationale, cta, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (conversation_id, from_role, message, action, rationale, cta, ts),
                )

    def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        conn = get_db(self.db_path)
        rows = conn.execute(
            "SELECT from_role, message, action, rationale, cta, timestamp FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_suppression(
        self, key: str, scope: str, entity_id: str, expires_at: Optional[str] = None, reason: str = ""
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO suppressions (key, scope, entity_id, expires_at, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, scope, entity_id, expires_at, reason, now_iso),
                )

    def is_suppressed(self, key: str, now_iso: Optional[str] = None) -> bool:
        if not key:
            return False
        conn = get_db(self.db_path)
        row = conn.execute("SELECT expires_at FROM suppressions WHERE key = ?", (key,)).fetchone()
        if not row:
            return False
        expires_at = row["expires_at"]
        if not expires_at:
            return True
        check_now = now_iso or datetime.now(timezone.utc).isoformat()
        return check_now < expires_at

    def suppress_merchant(self, merchant_id: str, duration_seconds: int = 2592000, reason: str = "opt_out") -> None:
        # Default 30 days
        expires_dt = datetime.now(timezone.utc).timestamp() + duration_seconds
        expires_iso = datetime.fromtimestamp(expires_dt, tz=timezone.utc).isoformat()
        now_iso = datetime.now(timezone.utc).isoformat()
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT INTO merchant_state (merchant_id, is_suppressed, suppression_expires_at, last_interaction)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(merchant_id) DO UPDATE SET
                    is_suppressed = 1, suppression_expires_at = excluded.suppression_expires_at, last_interaction = excluded.last_interaction
                    """,
                    (merchant_id, expires_iso, now_iso),
                )
                self.add_suppression(f"merchant_optout:{merchant_id}", "merchant", merchant_id, expires_iso, reason)

    def is_merchant_suppressed(self, merchant_id: str, now_iso: Optional[str] = None) -> bool:
        conn = get_db(self.db_path)
        row = conn.execute(
            "SELECT is_suppressed, suppression_expires_at FROM merchant_state WHERE merchant_id = ?",
            (merchant_id,),
        ).fetchone()
        if not row or not row["is_suppressed"]:
            return False
        expires_at = row["suppression_expires_at"]
        if not expires_at:
            return True
        check_now = now_iso or datetime.now(timezone.utc).isoformat()
        return check_now < expires_at

    def increment_merchant_auto_reply(self, merchant_id: str) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute(
                    """
                    INSERT INTO merchant_state (merchant_id, auto_reply_count, last_interaction)
                    VALUES (?, 1, ?)
                    ON CONFLICT(merchant_id) DO UPDATE SET
                    auto_reply_count = merchant_state.auto_reply_count + 1,
                    last_interaction = excluded.last_interaction
                    """,
                    (merchant_id, now_iso),
                )
                row = conn.execute(
                    "SELECT auto_reply_count FROM merchant_state WHERE merchant_id = ?",
                    (merchant_id,),
                ).fetchone()
                return row["auto_reply_count"] if row else 1

    def wipe_all(self) -> None:
        with _db_lock:
            conn = get_db(self.db_path)
            with conn:
                conn.execute("DELETE FROM messages;")
                conn.execute("DELETE FROM conversations;")
                conn.execute("DELETE FROM contexts;")
                conn.execute("DELETE FROM suppressions;")
                conn.execute("DELETE FROM merchant_state;")
