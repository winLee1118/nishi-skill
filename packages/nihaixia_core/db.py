from __future__ import annotations

import os
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  course TEXT NOT NULL DEFAULT '',
  chapter TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT 'markdown',
  rights_status TEXT NOT NULL DEFAULT 'unknown',
  path TEXT NOT NULL DEFAULT '',
  page TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  source_page TEXT NOT NULL DEFAULT '',
  raw_file TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  course TEXT NOT NULL DEFAULT '',
  chapter TEXT NOT NULL DEFAULT '',
  timestamp TEXT NOT NULL DEFAULT '',
  page TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  original_text TEXT NOT NULL,
  context_prefix TEXT NOT NULL DEFAULT '',
  contextual_text TEXT NOT NULL,
  topics_json TEXT NOT NULL DEFAULT '[]',
  entities_json TEXT NOT NULL DEFAULT '[]',
  aliases_json TEXT NOT NULL DEFAULT '[]',
  rights_status TEXT NOT NULL DEFAULT 'unknown',
  FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  domain,
  course,
  chapter,
  topics,
  entities,
  aliases,
  contextual_text,
  tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  aliases_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS relations (
  id TEXT PRIMARY KEY,
  source_entity TEXT NOT NULL,
  relation TEXT NOT NULL,
  target_entity TEXT NOT NULL,
  evidence TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  embedding_hash TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (chunk_id, provider, model)
);

CREATE TABLE IF NOT EXISTS query_embedding_cache (
  query_hash TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (query_hash, provider, model)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    db_existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    journal_mode = os.getenv("NIHAIXIA_SQLITE_JOURNAL_MODE", "DELETE").upper()
    synchronous = os.getenv("NIHAIXIA_SQLITE_SYNCHRONOUS", "OFF" if journal_mode == "OFF" else "NORMAL").upper()
    conn = open_connection(path, journal_mode=journal_mode, synchronous=synchronous)
    try:
        conn.executescript(SCHEMA)
        migrate_schema(conn)
        return conn
    except sqlite3.OperationalError as exc:
        conn.close()
        if journal_mode != "DELETE" or "disk I/O error" not in str(exc):
            raise
        if not db_existed and path.exists():
            try:
                path.unlink()
            except OSError as cleanup_error:
                raise exc from cleanup_error

    conn = open_connection(path, journal_mode="OFF", synchronous="OFF")
    conn.executescript(SCHEMA)
    migrate_schema(conn)
    return conn


def open_connection(path: Path, journal_mode: str, synchronous: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    conn.execute(f"PRAGMA synchronous={synchronous}")
    return conn


def migrate_schema(conn: sqlite3.Connection) -> None:
    ensure_columns(
        conn,
        "sources",
        {
            "page": "TEXT NOT NULL DEFAULT ''",
            "source_url": "TEXT NOT NULL DEFAULT ''",
            "source_page": "TEXT NOT NULL DEFAULT ''",
            "raw_file": "TEXT NOT NULL DEFAULT ''",
            "notes": "TEXT NOT NULL DEFAULT ''",
        },
    )
    ensure_columns(
        conn,
        "chunks",
        {
            "page": "TEXT NOT NULL DEFAULT ''",
            "source_url": "TEXT NOT NULL DEFAULT ''",
            "aliases_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )
    ensure_fts_schema(conn)


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_fts_schema(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(chunks_fts)").fetchall()}
    if existing and "aliases" not in existing:
        conn.execute("DROP TABLE chunks_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
              chunk_id UNINDEXED,
              domain,
              course,
              chapter,
              topics,
              entities,
              aliases,
              contextual_text,
              tokenize = 'unicode61'
            )
            """
        )


def reset_index(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM sources")
    conn.commit()
