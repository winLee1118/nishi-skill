from __future__ import annotations

from nihaixia_core import retrieval
from nihaixia_core.schemas import SearchResult


def make_result(chunk_id: str, match_source: str = "fts") -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        source_id="source-1",
        title="test",
        domain="renji",
        course="renji",
        chapter="chapter",
        timestamp="",
        page="",
        source_url="",
        snippet="test snippet",
        score=1.0,
        topics=[],
        entities=[],
        rights_status="public",
        match_source=match_source,
    )


def test_auto_defaults_to_hybrid(monkeypatch) -> None:
    monkeypatch.delenv("RAG_MODE", raising=False)

    def fake_search_hybrid(question, db_path, domain="auto", top_k=5):
        return [make_result("hybrid-1", "hybrid")], {
            "retrieval_mode": "hybrid",
            "requested_mode": "hybrid",
            "fallback": False,
            "warnings": [],
            "bm25_candidates": 1,
            "vector_candidates": 1,
        }

    import nihaixia_core.hybrid_retrieval as hybrid_retrieval

    monkeypatch.setattr(hybrid_retrieval, "search_hybrid", fake_search_hybrid)

    results, info = retrieval.search_with_info("失眠怎么办", "unused.sqlite", domain="renji", mode="auto")

    assert info["retrieval_mode"] == "hybrid"
    assert info["fallback"] is False
    assert info["vector_candidates"] == 1
    assert results[0].match_source == "hybrid"


def test_auto_hybrid_fallback_uses_fts(monkeypatch) -> None:
    monkeypatch.delenv("RAG_MODE", raising=False)

    def fake_search_hybrid(question, db_path, domain="auto", top_k=5):
        return [], {
            "retrieval_mode": "fts",
            "requested_mode": "hybrid",
            "fallback": True,
            "warnings": ["failed"],
        }

    def fake_search_fts_only(question, db_path, domain="auto", top_k=5):
        return [make_result("fts-1", "fts")]

    import nihaixia_core.hybrid_retrieval as hybrid_retrieval

    monkeypatch.setattr(hybrid_retrieval, "search_hybrid", fake_search_hybrid)
    monkeypatch.setattr(retrieval, "search_fts_only", fake_search_fts_only)

    results, info = retrieval.search_with_info("失眠怎么办", "unused.sqlite", domain="renji", mode="auto")

    assert info["retrieval_mode"] == "fts"
    assert info["requested_mode"] == "hybrid"
    assert info["fallback"] is True
    assert results[0].match_source == "fts"


def test_rag_mode_can_force_fts(monkeypatch) -> None:
    monkeypatch.setenv("RAG_MODE", "fts")
    monkeypatch.setattr(retrieval, "search_fts_only", lambda *args, **kwargs: [make_result("fts-1", "fts")])

    results, info = retrieval.search_with_info("失眠怎么办", "unused.sqlite", domain="renji", mode="auto")

    assert info["retrieval_mode"] == "fts"
    assert info["requested_mode"] == "fts"
    assert info["fallback"] is False
    assert results[0].match_source == "fts"


def test_demo_results_are_not_user_visible() -> None:
    results = retrieval.filter_user_visible_results(
        [
            make_result("real-1", "hybrid"),
            SearchResult(
                chunk_id="demo-1",
                source_id="renji-shanghan-taiyang-guizhi-demo",
                title="demo",
                domain="renji",
                course="renji",
                chapter="chapter",
                timestamp="demo",
                page="",
                source_url="",
                snippet="用于测试工程结构的示例片段",
                score=1.0,
                topics=[],
                entities=[],
                rights_status="public",
                match_source="hybrid",
            ),
        ]
    )

    assert [item.chunk_id for item in results] == ["real-1"]
