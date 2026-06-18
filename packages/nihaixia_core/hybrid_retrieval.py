from __future__ import annotations

from pathlib import Path

from .db import connect
from .embedding import is_configured, load_embedding_config, sanitize_config_for_report
from .retrieval import filter_user_visible_results, row_to_result, search_fts, search_like
from .schemas import SearchResult
from .text import classify_domain, lexical_terms
from .vector_store import get_or_create_query_embedding, vector_candidates


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return {key: 1.0 for key in scores}
    return {key: (value - minimum) / (maximum - minimum) for key, value in scores.items()}


def row_haystack(row) -> str:
    return " ".join(
        [
            str(row["contextual_text"]),
            str(row["topics_json"]),
            str(row["entities_json"]),
            str(row["aliases_json"] if "aliases_json" in row.keys() else "[]"),
        ]
    ).lower()


def lexical_coverage(row, terms: list[str]) -> float:
    useful_terms = [term.lower() for term in terms[:16] if len(term.strip()) >= 2]
    if not useful_terms:
        return 0.0
    haystack = row_haystack(row)
    hits = sum(1 for term in useful_terms if term in haystack)
    return hits / len(useful_terms)


def reranked_bm25_ids(bm25_rows, question: str) -> list[str]:
    results = [row_to_result(row, question) for row in bm25_rows]
    reranked = sorted(results, key=lambda item: item.score, reverse=True)
    return [item.chunk_id for item in reranked]


def protected_top_k(sorted_results: list[SearchResult], protected_ids: set[str], top_k: int) -> list[SearchResult]:
    if len(protected_ids) < top_k:
        return sorted_results[:top_k]

    protected = [item for item in sorted_results if item.chunk_id in protected_ids]
    selected = protected[:top_k]
    if len(selected) >= top_k:
        return selected

    selected_ids = {item.chunk_id for item in selected}
    for item in sorted_results:
        if item.chunk_id in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= top_k:
            break
    return selected


def ensure_vector_presence(
    selected: list[SearchResult],
    sorted_results: list[SearchResult],
    vector_ids: set[str],
    top_k: int,
) -> list[SearchResult]:
    if top_k < 2 or not vector_ids or any(item.chunk_id in vector_ids for item in selected):
        return selected

    selected_ids = {item.chunk_id for item in selected}
    for item in sorted_results:
        if item.chunk_id in vector_ids and item.chunk_id not in selected_ids:
            return [*selected[: top_k - 1], item]
    return selected


def search_hybrid(
    question: str,
    db_path: str | Path,
    domain: str = "auto",
    top_k: int = 5,
    candidate_k: int = 30,
) -> tuple[list[SearchResult], dict]:
    config = load_embedding_config()
    if not is_configured(config):
        return [], {
            "retrieval_mode": "fts",
            "requested_mode": "hybrid",
            "fallback": True,
            "warnings": ["Embedding API is not configured; falling back to fts."],
            "embedding": sanitize_config_for_report(config),
        }

    selected_domain = classify_domain(question) if domain == "auto" else domain
    conn = connect(db_path)
    warnings: list[str] = []
    try:
        bm25_rows = search_fts(conn, question, selected_domain, candidate_k)
        if not bm25_rows:
            bm25_rows = search_like(conn, question, selected_domain, candidate_k)
        question_vector = get_or_create_query_embedding(conn, question, config)
        vector_rows = vector_candidates(conn, question_vector, config, selected_domain, candidate_k)
    except Exception as exc:  # noqa: BLE001
        conn.close()
        return [], {
            "retrieval_mode": "fts",
            "requested_mode": "hybrid",
            "fallback": True,
            "warnings": [f"Hybrid retrieval failed ({type(exc).__name__}); falling back to fts."],
            "embedding": sanitize_config_for_report(config),
        }

    baseline_bm25_rows = bm25_rows[: max(top_k * 3, top_k)]
    bm25_order = reranked_bm25_ids(bm25_rows, question)
    protected_order = reranked_bm25_ids(baseline_bm25_rows, question)
    protected_ids = set(protected_order[:top_k])
    bm25_scores = {chunk_id: float(len(bm25_order) - index) for index, chunk_id in enumerate(bm25_order)}
    vector_scores = {row["id"]: score for row, score in vector_rows}
    bm25_norm = normalize_scores(bm25_scores)
    vector_norm = normalize_scores(vector_scores)

    rows_by_id = {row["id"]: row for row in bm25_rows}
    rows_by_id.update({row["id"]: row for row, _score in vector_rows})
    terms = lexical_terms(question)
    results: list[SearchResult] = []
    for chunk_id, row in rows_by_id.items():
        result = row_to_result(row, question)
        in_bm25 = chunk_id in bm25_scores
        in_vector = chunk_id in vector_scores
        if in_bm25 and in_vector:
            result.match_source = "hybrid"
        elif in_vector:
            result.match_source = "vector"
        else:
            result.match_source = "fts"
        coverage = lexical_coverage(row, terms)
        domain_match = 1.0 if selected_domain in ("auto", "cross", result.domain) else 0.0
        rights_weight = 1.0 if result.rights_status in ("authorized", "public") else 0.25
        vector_weight = vector_norm.get(chunk_id, 0.0) * (0.25 + 0.75 * coverage)
        bm25_protection = 0.10 if chunk_id in protected_ids else 0.0
        result.score = (
            0.62 * bm25_norm.get(chunk_id, 0.0)
            + 0.18 * vector_weight
            + 0.12 * coverage
            + 0.05 * domain_match
            + 0.03 * rights_weight
            + bm25_protection
        )
        results.append(result)

    conn.close()
    sorted_results = filter_user_visible_results(sorted(results, key=lambda item: item.score, reverse=True))
    protected_ids = {item.chunk_id for item in sorted_results if item.chunk_id in protected_ids}
    visible_vector_ids = {item.chunk_id for item in sorted_results if item.chunk_id in vector_scores}
    final_results = protected_top_k(sorted_results, protected_ids, top_k)
    final_results = ensure_vector_presence(final_results, sorted_results, visible_vector_ids, top_k)
    return final_results, {
        "retrieval_mode": "hybrid",
        "requested_mode": "hybrid",
        "fallback": False,
        "warnings": warnings,
        "embedding": sanitize_config_for_report(config),
        "bm25_candidates": len(bm25_rows),
        "vector_candidates": len(vector_rows),
        "bm25_protected": min(len(protected_ids), top_k),
    }
