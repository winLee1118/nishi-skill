from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .db import connect
from .schemas import SearchResult
from .text import classify_domain, compact_snippet, json_loads_list, make_fts_query, query_terms


def search(
    question: str,
    db_path: str | Path,
    domain: str = "auto",
    top_k: int = 5,
    mode: str = "auto",
) -> list[SearchResult]:
    results, _info = search_with_info(question, db_path, domain=domain, top_k=top_k, mode=mode)
    return results


def search_with_info(
    question: str,
    db_path: str | Path,
    domain: str = "auto",
    top_k: int = 5,
    mode: str = "auto",
) -> tuple[list[SearchResult], dict]:
    selected_mode = resolve_mode(mode)
    if selected_mode == "hybrid":
        from .hybrid_retrieval import search_hybrid

        hybrid_results, info = search_hybrid(question, db_path, domain=domain, top_k=top_k)
        if not info.get("fallback"):
            return hybrid_results, info
        fts_results = search_fts_only(question, db_path, domain=domain, top_k=top_k)
        return fts_results, info

    return search_fts_only(question, db_path, domain=domain, top_k=top_k), {
        "retrieval_mode": "fts",
        "requested_mode": selected_mode,
        "fallback": False,
        "warnings": [],
    }


def resolve_mode(mode: str) -> str:
    if mode == "auto":
        mode = os.getenv("RAG_MODE", "hybrid")
    return mode if mode in {"fts", "hybrid"} else "fts"


def search_fts_only(
    question: str,
    db_path: str | Path,
    domain: str = "auto",
    top_k: int = 5,
) -> list[SearchResult]:
    selected_domain = classify_domain(question) if domain == "auto" else domain
    conn = connect(db_path)
    rows = search_fts(conn, question, selected_domain, max(top_k * 3, top_k))
    if not rows:
        rows = search_like(conn, question, selected_domain, max(top_k * 3, top_k))
    results = filter_user_visible_results([row_to_result(row, question) for row in rows])
    reranked = sorted(results, key=lambda item: item.score, reverse=True)
    conn.close()
    return reranked[:top_k]


def search_fts(conn: sqlite3.Connection, question: str, domain: str, limit: int) -> list[sqlite3.Row]:
    query = make_fts_query(question)
    domain_filter = "" if domain in ("auto", "cross") else "AND c.domain = ?"
    params: list[object] = [query]
    if domain_filter:
        params.append(domain)
    params.append(limit)
    sql = f"""
        SELECT c.*, bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.chunk_id
        WHERE chunks_fts MATCH ?
        {domain_filter}
        ORDER BY rank
        LIMIT ?
    """
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def search_like(conn: sqlite3.Connection, question: str, domain: str, limit: int) -> list[sqlite3.Row]:
    terms = query_terms(question)[:8] or [question]
    clauses = ["c.contextual_text LIKE ?" for _ in terms]
    params: list[object] = [f"%{term}%" for term in terms]
    domain_filter = "" if domain in ("auto", "cross") else "AND c.domain = ?"
    if domain_filter:
        params.append(domain)
    params.append(limit)
    sql = f"""
        SELECT c.*, 0 AS rank
        FROM chunks c
        WHERE ({' OR '.join(clauses)})
        {domain_filter}
        LIMIT ?
    """
    return conn.execute(sql, params).fetchall()


def row_to_result(row: sqlite3.Row, question: str) -> SearchResult:
    topics = json_loads_list(row["topics_json"])
    entities = json_loads_list(row["entities_json"])
    aliases = json_loads_list(row["aliases_json"] if "aliases_json" in row.keys() else "[]")
    haystack = "\n".join([row["contextual_text"], " ".join(topics), " ".join(entities), " ".join(aliases)]).lower()
    terms = query_terms(question)[:16]
    hits = sum(1 for term in terms if term.lower() in haystack)
    rank = float(row["rank"] or 0) if "rank" in row.keys() else 0.0
    score = hits * 2.0 - rank
    if terms and terms[0].lower() in haystack:
        score += 3.0
    if row["rights_status"] in ("authorized", "public"):
        score += 1.0
    return SearchResult(
        chunk_id=row["id"],
        source_id=row["source_id"],
        title=row["title"],
        domain=row["domain"],
        course=row["course"],
        chapter=row["chapter"],
        timestamp=row["timestamp"],
        page=row["page"] if "page" in row.keys() else "",
        source_url=row["source_url"] if "source_url" in row.keys() else "",
        snippet=compact_snippet(row["contextual_text"], question),
        score=score,
        topics=topics,
        entities=entities,
        rights_status=row["rights_status"],
    )


def is_demo_result(item: SearchResult) -> bool:
    source_id = item.source_id.lower()
    timestamp = item.timestamp.lower()
    snippet = item.snippet.lower()
    return (
        source_id.endswith("-demo")
        or "-demo" in source_id
        or timestamp == "demo"
        or "用于测试工程结构" in item.snippet
        or "test fixture" in snippet
    )


def filter_user_visible_results(results: list[SearchResult]) -> list[SearchResult]:
    return [item for item in results if not is_demo_result(item)]
