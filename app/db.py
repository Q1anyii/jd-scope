"""SQLite 数据层：建库、迁移、常用读写。

只有一张库（用户数据目录下的 jdscope.db），不含任何个人隐私样本。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import db_path, ensure_dirs

SCHEMA_VERSION = 2

# v2 相对 v1 的增量：老库启动时按列补齐，不重建、不清数据
COLUMN_PATCHES = (
    ("bases", "kind", "kind TEXT DEFAULT 'html'"),
    ("requirements", "source", "source TEXT DEFAULT 'rule'"),
)

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    education TEXT DEFAULT '',
    major TEXT DEFAULT '',
    years REAL DEFAULT 0,
    cities TEXT DEFAULT '',
    certs TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    intent TEXT NOT NULL,
    label TEXT DEFAULT '',
    content TEXT DEFAULT '',
    keywords TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    kind TEXT DEFAULT 'html',
    coverage INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    city TEXT DEFAULT '',
    url TEXT DEFAULT '',
    source TEXT DEFAULT '',
    jd_raw TEXT NOT NULL,
    jd_hash TEXT DEFAULT '',
    status TEXT DEFAULT 'new',
    decision TEXT DEFAULT 'undecided',
    decision_note TEXT DEFAULT '',
    base_id INTEGER,
    score REAL DEFAULT 0,
    score_json TEXT DEFAULT '{}',
    constraint_state TEXT DEFAULT '',
    verdict TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    category TEXT DEFAULT 'must',
    weight REAL DEFAULT 1,
    terms TEXT DEFAULT '[]',
    hit INTEGER DEFAULT 0,
    evidence TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    ord INTEGER DEFAULT 0,
    source TEXT DEFAULT 'rule'
);

CREATE TABLE IF NOT EXISTS gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    req_id INTEGER,
    requirement TEXT DEFAULT '',
    resume_state TEXT DEFAULT '',
    gap TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    action TEXT DEFAULT '',
    answer TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    module TEXT DEFAULT '',
    original TEXT DEFAULT '',
    suggestion TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    adopted INTEGER DEFAULT 0,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT
);

-- 公司档案：一个公司 = 数据目录 resumes/ 下的一个文件夹
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    folder TEXT NOT NULL,
    job_id INTEGER,
    base_id INTEGER,
    status TEXT DEFAULT 'draft',
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_req_job ON requirements(job_id);
CREATE INDEX IF NOT EXISTS idx_gap_job ON gaps(job_id);
CREATE INDEX IF NOT EXISTS idx_sug_job ON suggestions(job_id);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    for table, column, ddl in COLUMN_PATCHES:
        if column not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    row = conn.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT OR IGNORE INTO profile(id, education, major, years, cities, certs, notes, updated_at)"
            " VALUES(1, '', '', 0, '', '', '', ?)",
            (now(),),
        )
        del cur
        for k, v in (
            ("llm_base_url", ""),
            ("llm_model", ""),
            ("llm_api_key", ""),
            ("weights", json.dumps({"must": 30, "duty": 30, "nice": 15, "constraint": 25})),
        ):
            conn.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?, ?)", (k, v))
    conn.execute(
        "INSERT INTO meta(k, v) VALUES('schema_version', ?)"
        " ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
    return row["v"] if row and row["v"] is not None else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(k, v) VALUES(?, ?)"
        " ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, value),
    )
    conn.commit()


def get_profile(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
    return dict(row) if row else {}


def save_profile(conn: sqlite3.Connection, data: dict) -> None:
    conn.execute(
        "UPDATE profile SET education=?, major=?, years=?, cities=?, certs=?, notes=?, updated_at=?"
        " WHERE id=1",
        (
            data.get("education", ""),
            data.get("major", ""),
            float(data.get("years", 0) or 0),
            data.get("cities", ""),
            data.get("certs", ""),
            data.get("notes", ""),
            now(),
        ),
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}
