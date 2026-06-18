from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .db import connect
from .embedding import EmbeddingConfig, embed_texts, is_configured, load_embedding_config, sanitize_config_for_report, supports_batch_embeddings


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vector_json(vector: list[float]) -> str:
    return json.dumps(vector, ensure_ascii=False, separators=(",", ":"))


def vector_loads(value: str) -> list[float]:
    data = json.loads(value)
    return [float(item) for item in data] if isinstance(data, list) else []


def embedding_text(row: sqlite3.Row) -> str:
    return "\n".join(
        [
            str(row["context_prefix"]),
            str(row["contextual_text"]),
            str(row["topics_json"]),
            str(row["entities_json"]),
            str(row["aliases_json"] if "aliases_json" in row.keys() else "[]"),
        ]
    )


def chunk_embedding_hash(row: sqlite3.Row, config: EmbeddingConfig) -> str:
    return stable_hash(
        "\n".join(
            [
                config.provider,
                config.model,
                str(row["source_id"]),
                str(row["id"]),
                embedding_text(row),
            ]
        )
    )


def chunks_for_embedding(conn: sqlite3.Connection, config: EmbeddingConfig, limit: int | None = None) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT c.*, e.embedding_hash AS existing_hash
        FROM chunks c
        LEFT JOIN chunk_embeddings e
          ON e.chunk_id = c.id AND e.provider = ? AND e.model = ?
        WHERE LENGTH(c.contextual_text) >= ?
        ORDER BY c.id
        """,
        (config.provider, config.model, MIN_CHUNK_TEXT_LEN),
    ).fetchall()
    pending = [row for row in rows if row["existing_hash"] != chunk_embedding_hash(row, config)]
    return pending[:limit] if limit else pending


def upsert_chunk_embedding(conn: sqlite3.Connection, chunk_id: str, config: EmbeddingConfig, embedding_hash: str, vector: list[float]) -> None:
    conn.execute(
        """
        INSERT INTO chunk_embeddings (chunk_id, provider, model, embedding_hash, dim, vector_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id, provider, model) DO UPDATE SET
          embedding_hash=excluded.embedding_hash,
          dim=excluded.dim,
          vector_json=excluded.vector_json,
          created_at=excluded.created_at
        """,
        (chunk_id, config.provider, config.model, embedding_hash, len(vector), vector_json(vector), now_iso()),
    )


def build_chunk_embeddings(db_path: str | Path, limit: int | None = None, batch_size: int = 16) -> dict:
    config = load_embedding_config()
    if not is_configured(config):
        return {
            "built": 0,
            "pending": 0,
            "warnings": ["Embedding API is not configured; set EMBEDDING_BASE_URL, EMBEDDING_MODEL, and EMBEDDING_API_KEY."],
            "embedding": sanitize_config_for_report(config),
        }

    conn = connect(db_path)
    pending = chunks_for_embedding(conn, config, limit)
    built = 0
    warnings: list[str] = []
    effective_batch_size = batch_size if supports_batch_embeddings(config) else 1
    for start in range(0, len(pending), effective_batch_size):
        batch = pending[start : start + effective_batch_size]
        try:
            vectors = embed_texts([embedding_text(row) for row in batch], config)
        except RuntimeError as exc:
            warnings.append(str(exc))
            break
        for row, vector in zip(batch, vectors, strict=True):
            upsert_chunk_embedding(conn, row["id"], config, chunk_embedding_hash(row, config), vector)
            built += 1
        conn.commit()
    conn.close()
    return {
        "built": built,
        "pending": len(pending),
        "batch_size": effective_batch_size,
        "warnings": warnings,
        "embedding": sanitize_config_for_report(config),
    }


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def get_or_create_query_embedding(conn: sqlite3.Connection, question: str, config: EmbeddingConfig) -> list[float]:
    query_hash = stable_hash("\n".join([config.provider, config.model, question]))
    row = conn.execute(
        """
        SELECT vector_json FROM query_embedding_cache
        WHERE query_hash = ? AND provider = ? AND model = ?
        """,
        (query_hash, config.provider, config.model),
    ).fetchone()
    if row:
        return vector_loads(row["vector_json"])

    vector = embed_texts([question], config)[0]
    conn.execute(
        """
        INSERT OR REPLACE INTO query_embedding_cache (query_hash, provider, model, dim, vector_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (query_hash, config.provider, config.model, len(vector), vector_json(vector), now_iso()),
    )
    conn.commit()
    return vector


MIN_CHUNK_TEXT_LEN = 100


def vector_candidates(conn: sqlite3.Connection, question_vector: list[float], config: EmbeddingConfig, domain: str, limit: int) -> list[tuple[sqlite3.Row, float]]:
    domain_filter = "" if domain in ("auto", "cross") else "AND c.domain = ?"
    params: list[object] = [config.provider, config.model, MIN_CHUNK_TEXT_LEN]
    if domain_filter:
        params.append(domain)
    rows = conn.execute(
        f"""
        SELECT c.*, e.vector_json
        FROM chunk_embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        WHERE e.provider = ? AND e.model = ?
          AND LENGTH(c.contextual_text) >= ?
        {domain_filter}
        """,
        params,
    ).fetchall()
    scored = [(row, cosine_similarity(question_vector, vector_loads(row["vector_json"]))) for row in rows]
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
