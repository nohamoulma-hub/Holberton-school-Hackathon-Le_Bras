import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        Path(__file__).resolve().parent.parent / "data.db",
    )
)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            assignee TEXT,
            due_date TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT UNIQUE NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start TEXT NOT NULL,
            duration_min INTEGER NOT NULL,
            attendees_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            action_index INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            output_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    action_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(actions)").fetchall()
    }
    if "action_index" not in action_columns:
        conn.execute("ALTER TABLE actions ADD COLUMN action_index INTEGER")
    conn.execute("UPDATE actions SET action_index = id WHERE action_index IS NULL")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_actions_plan_status
        ON actions (plan_id, status)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_token
        ON sessions (token_hash, expires_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id TEXT,
            user_message TEXT NOT NULL,
            agent_response TEXT NOT NULL,
            metrics_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_created
        ON conversations (user_id, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_owners (
            action_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_owners_user
        ON action_owners (user_id, created_at DESC)
        """
    )
    conn.commit()
    conn.close()


def get_recent_audit_log(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, idempotency_key, tool_name, input_json, output_json, status, error, created_at
        FROM audit_log
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
