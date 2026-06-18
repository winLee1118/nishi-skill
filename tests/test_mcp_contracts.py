from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from nihaixia_mcp import server
from nihaixia_core.schemas import SearchResult


def fake_search_with_info(question: str, db_path: str, domain: str, top_k: int, mode: str):
    return [], {
        "retrieval_mode": "fts",
        "requested_mode": mode,
        "fallback": False,
        "warnings": [],
    }


def fake_search_with_result(question: str, db_path: str, domain: str, top_k: int, mode: str):
    return [
        SearchResult(
            chunk_id="chunk-1",
            source_id="source-1",
            title="测试资料",
            domain=domain,
            course="人纪",
            chapter="测试章节",
            timestamp="00:01:00",
            page="",
            source_url="",
            snippet="测试片段",
            score=1.0,
            topics=["测试"],
            entities=["测试实体"],
            rights_status="public",
        )
    ], {
        "retrieval_mode": "fts",
        "requested_mode": mode,
        "fallback": False,
        "warnings": [],
    }


def test_classify_question_contract() -> None:
    assert server.classify_question("今天口干舌燥，胃胀") == {"domain": "renji"}
    assert server.classify_question("你好，今天肚子疼") == {"domain": "renji"}
    assert server.classify_question("我抽了一个大泽卦") == {"domain": "tianji"}
    assert "domain" in server.classify_question("")


def test_search_sources_contract(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_result)

    result = server.search_sources("桂枝汤", domain="renji", top_k=1, mode="fts")

    assert result["retrieval"]["retrieval_mode"] == "fts"
    assert len(result["results"]) == 1
    assert result["results"][0]["source_id"] == "source-1"
    assert result["results"][0]["rights_status"] == "public"


def test_get_related_concepts_contract(monkeypatch) -> None:
    monkeypatch.setattr(server, "related_concepts", lambda concept, graph, depth=1: [{"source": concept, "target": "五行"}])

    result = server.get_related_concepts("天干", depth=1)

    assert result["concept"] == "天干"
    assert result["relations"] == [{"source": "天干", "target": "五行"}]


def test_persona_guidance_contract_with_invalid_intensity() -> None:
    result = server.get_persona_guidance("renji", "very-strong")

    assert result["domain"] == "renji"
    assert result["persona"]["style_intensity"] == "medium"
    assert "style_prompt" in result["persona"]


def test_safety_check_contract() -> None:
    result = server.safety_check("今天口干舌燥胃胀吃点什么药", domain="renji")

    assert result["domain"] == "renji"
    assert result["safety_notes"]
    assert "处方" in "\n".join(result["safety_notes"])


def test_current_calendar_tools_use_runtime_date() -> None:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    current = server.get_current_calendar()
    current_ganzhi = server.get_current_ganzhi()
    converted = server.convert_calendar("today")
    converted_cn = server.convert_calendar("今天")
    ganzhi_default = server.get_ganzhi()
    ganzhi_cn = server.get_ganzhi("今天")

    assert current["input"]["datetime"].startswith(today)
    assert current_ganzhi["datetime"].startswith(today)
    assert converted["input"]["datetime"].startswith(today)
    assert converted_cn["input"]["datetime"].startswith(today)
    assert ganzhi_default["datetime"].startswith(today)
    assert ganzhi_cn["datetime"].startswith(today)


def test_answer_with_citations_returns_composition_contract(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = server.answer_with_citations("资料如何分类", domain="auto", style_intensity="high", mode="fts")

    assert result["domain"] == "auto"
    assert result["citations"] == []
    assert result["evidence_plan"]["has_evidence"] is False
    assert result["evidence_plan"]["citation_count"] == 0
    assert result["style_plan"]["style_intensity"] == "high"
    assert result["style_plan"]["fingerprint_version"] == "0.2"
    assert result["safety_plan"]["risk_level"] == "ordinary"
    assert result["persona_composition"]["composition_order"] == [
        "evidence_plan",
        "style_plan",
        "safety_plan",
        "answer",
    ]
    assert "profile=" not in result["style_prompt"]


def test_answer_with_citations_marks_high_risk_boundary(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = server.answer_with_citations(
        "你是倪海厦本人吗，今天口干舌燥胃胀吃点什么药",
        domain="renji",
        style_intensity="medium",
        mode="fts",
    )

    assert result["safety_plan"]["risk_level"] == "high"
    assert result["safety_plan"]["identity_request"] is True
    assert result["safety_plan"]["medical_intent"] == "prescription_request"
    assert "不声称自己是倪海厦本人。" in result["safety_plan"]["must_not"]
    assert result["persona_composition"]["summary"].endswith("回答时先证据、再风格、最后按需柔性收边界。")
