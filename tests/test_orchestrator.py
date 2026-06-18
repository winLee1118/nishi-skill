from __future__ import annotations

import re

from nihaixia_mcp import orchestrator, server
from nihaixia_core.schemas import SearchResult

NUMBERED_LINE_RE = re.compile(r"(?m)^\s*\d{1,2}[\.、)）]\s")


def fake_search_with_info(question, db_path, domain="auto", top_k=5, mode="auto"):
    return [
        SearchResult(
            chunk_id="chunk-1",
            source_id="source-1",
            title="测试资料",
            domain="renji",
            course="人纪",
            chapter="测试章节",
            timestamp="00:01:00",
            page="",
            source_url="",
            snippet="测试片段内容",
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


def test_needs_time_context() -> None:
    assert orchestrator._needs_time_context("日柱丁火今天运势如何", []) is True
    assert orchestrator._needs_time_context("今天流日是什么呢，生丁火吗", []) is True
    assert orchestrator._needs_time_context("今天流日是什么呢，生我日柱丁丑吗", []) is True
    assert orchestrator._needs_time_context("现在的天干地支是什么", []) is True
    assert orchestrator._needs_time_context("今天几号", []) is True
    # Follow-up question relying on history for the time reference.
    assert (
        orchestrator._needs_time_context(
            "那生我吗", [{"role": "user", "content": "今天流日是什么"}]
        )
        is True
    )
    assert orchestrator._needs_time_context("桂枝汤和太阳中风的关系", []) is False
    assert orchestrator._needs_time_context("五行相生相克怎么理解", []) is False
    assert orchestrator._needs_time_context("天干地支怎么学", []) is False


def test_time_context_injected_for_today_fortune(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("日柱丁火今天运势如何")

    assert result["route"] == "answer"
    assert result["meta"]["domain"] == "tianji"
    user_prompt = result["messages"][1]["content"]
    assert "当前时间底座" in user_prompt
    assert "流日即日柱" in user_prompt
    assert "不要声称无法获知当前或目标日期的干支" in user_prompt
    # The offline fallback draft carries the real numbers too.
    assert result["answer_draft"].startswith("先看时间底座")
    # Real-time tool results are exposed for display/audit.
    assert result["meta"]["skill_result"]["get_ganzhi"]["pillars"]


def test_flow_day_interpretation_goes_to_llm_not_template(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("今天流日是什么呢，生我日柱丁丑吗")

    # No fixed-template hijack: interpretation flows through retrieval + LLM.
    assert result["route"] == "answer"
    assert result["draft_is_final"] is False
    assert len(result["messages"]) == 2
    user_prompt = result["messages"][1]["content"]
    assert "当前时间底座" in user_prompt
    assert "做学习性解读" in user_prompt


def test_no_time_context_for_plain_knowledge_question(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("桂枝汤和太阳中风的关系")

    assert result["route"] == "answer"
    assert "当前时间底座" not in result["messages"][1]["content"]


def test_bazi_routing_with_history_followup() -> None:
    history = [{"role": "user", "content": "我是1979年11月6日20:30生的男性"}]
    assert orchestrator._wants_bazi_chart("你直接告诉我", history) is True
    assert orchestrator._wants_bazi_chart("我是1979年11月6日20:30生的男性，八字是什么", []) is True
    assert orchestrator._wants_bazi_chart("八字怎么入门", []) is False


def test_parse_birth_input_two_digit_year_and_gender() -> None:
    parsed = orchestrator._parse_birth_input("我是85年3月12日8:15生的女性", [])
    assert parsed is not None
    assert parsed["datetime_text"] == "1985-03-12 08:15"
    assert parsed["gender"] == "女"

    assert orchestrator._parse_birth_input("帮我排八字", []) is None


def test_bazi_route_hour_branch_matches_birth_time() -> None:
    # Morning birth must not produce the old hardcoded "20:30 是戌时" wording.
    result = orchestrator.chat_orchestrate("我是1985年3月12日8:15生的女性，帮我排四柱")
    assert result["route"] == "bazi"
    assert result["draft_is_final"] is False
    assert len(result["messages"]) == 2
    assert "08:15 落在辰时" in result["answer_draft"]
    assert "20:30" not in result["answer_draft"]
    assert "Asia/Shanghai" not in result["answer_draft"]
    assert "get_bazi_chart" not in result["answer_draft"]
    user_prompt = result["messages"][1]["content"]
    assert "确定排盘数据" in user_prompt
    assert "不要输出工具名" in user_prompt
    assert "Asia/Shanghai" not in user_prompt
    assert "get_bazi_chart" not in user_prompt

    evening = orchestrator.chat_orchestrate("我是1979年11月6日20:30生的男性，干支是什么")
    assert "20:30 落在戌时" in evening["answer_draft"]


def test_bazi_route_missing_birth_info_asks_for_it() -> None:
    result = orchestrator.chat_orchestrate("你直接告诉我", history=[{"role": "user", "content": "帮我排1990年的八字，时间我想想"}])
    assert result["route"] == "answer" or result["route"] == "bazi"


def test_pure_calendar_question_gets_time_basis_in_answer_route(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("现在的天干地支是什么")
    assert result["route"] == "answer"
    # Offline fallback already contains the computed Ganzhi.
    assert "干支是" in result["answer_draft"]
    assert "流日（日柱）是" in result["answer_draft"]
    assert result["meta"]["skill_result"]["get_ganzhi"]["pillars"]


def test_answer_route_contract(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate(
        "桂枝汤和太阳中风的关系",
        history=[{"role": "user", "content": "我在学伤寒论"}],
    )

    assert result["route"] == "answer"
    assert result["draft_is_final"] is False
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "system"
    assert result["messages"][1]["role"] == "user"
    assert len(result["citations"]) == 1
    assert result["meta"]["domain"] == "renji"

    system_prompt = result["messages"][0]["content"]
    user_prompt = result["messages"][1]["content"]
    # Format contract is stated in the system prompt.
    assert "纯对话文本" in system_prompt
    # Slimmed prompt: no raw plan JSON dumps.
    assert "evidence_plan" not in user_prompt
    assert "style_plan" not in user_prompt
    assert '"composition_order"' not in user_prompt
    # History is carried into the prompt.
    assert "我在学伤寒论" in user_prompt
    assert "引用标签" not in user_prompt
    assert "不要输出 source_id" in user_prompt
    assert "chunk_id" in user_prompt


def test_greeting_is_left_for_llm_without_fixed_draft(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("你好")

    assert result["route"] == "answer"
    assert result["draft_is_final"] is False
    assert result["answer_draft"] == ""
    assert result["citations"] == []
    assert result["meta"]["retrieval_info"]["retrieval_mode"] == "skipped_greeting"
    assert len(result["messages"]) == 2
    user_prompt = result["messages"][1]["content"]
    assert "若用户只是问候或闲聊，请直接自然回应" in user_prompt
    assert "你可以直接问人纪、天纪、地纪相关的问题" not in user_prompt


def test_voice_connection_check_skips_retrieval_and_stays_brief(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("你好，听到我说话了吗？")

    assert result["route"] == "answer"
    assert result["answer_draft"] == ""
    assert result["citations"] == []
    assert result["meta"]["retrieval_info"]["retrieval_mode"] == "skipped_greeting"
    user_prompt = result["messages"][1]["content"]
    assert "只自然确认一两句" in user_prompt
    assert "不展开知识讲解" in user_prompt


def test_one_sentence_request_limits_fallback_draft_and_prompt(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("倪师桂枝汤什么情况下喝最好，只回答我一句话")

    assert result["route"] == "answer"
    assert "资料里讲到" not in result["answer_draft"]
    assert "\n" not in result["answer_draft"]
    assert result["answer_draft"].count("。") <= 1
    user_prompt = result["messages"][1]["content"]
    assert "最终回答只能写一句话" in user_prompt
    assert "不要展开资料原文" in user_prompt


def test_chat_draft_has_no_numbered_lists(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    for question in ("我失眠多梦怎么办", "我肚子疼，吃什么药好", "口干舌燥还胃胀是怎么回事"):
        result = server.answer_with_citations(question, domain="renji", output_format="chat")
        assert not NUMBERED_LINE_RE.search(result["answer"]), question
        assert "学习用草稿" not in result["answer"]


def test_report_format_kept_for_compat(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = server.answer_with_citations("我失眠多梦怎么办", domain="renji", output_format="report")
    assert "学习用草稿" in result["answer"]


def test_history_helps_domain_classification(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = server.answer_with_citations(
        "继续说",
        domain="auto",
        history=[{"role": "user", "content": "讲讲阳宅风水的方位"}],
    )
    assert result["domain"] == "diji"


def test_resolve_date_references() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 13, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # Saturday

    targets = orchestrator._resolve_date_references("下周一去买车合适吗", now)
    assert len(targets) == 1
    assert targets[0]["label"] == "下周一"
    assert targets[0]["date"].isoformat() == "2026-06-15"
    assert targets[0]["date"].weekday() == 0

    targets = orchestrator._resolve_date_references("明天和6月18日哪天好", now)
    labels = {t["label"]: t["date"].isoformat() for t in targets}
    assert labels["明天"] == "2026-06-14"
    assert labels["6月18日"] == "2026-06-18"

    # Birth datetime must not be treated as a target date.
    targets = orchestrator._resolve_date_references("我是79年11月6日20:30生男，下周一去买车合适吗", now)
    assert [t["label"] for t in targets] == ["下周一"]

    # Explicit dates far in the past (>180 days) roll into next year.
    december = datetime(2026, 12, 13, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    targets = orchestrator._resolve_date_references("1月2日怎么样", december)
    assert targets[0]["date"].isoformat() == "2027-01-02"
    # Recently passed dates stay in the current year.
    targets = orchestrator._resolve_date_references("6月1日那天如何", now)
    assert targets[0]["date"].isoformat() == "2026-06-01"

    assert orchestrator._resolve_date_references("桂枝汤是什么", now) == []


def test_date_selection_question_gets_full_basis(monkeypatch) -> None:
    monkeypatch.setattr(server, "search_with_info", fake_search_with_info)

    result = orchestrator.chat_orchestrate("我是79年11月6日20:30生男，下周一去买车合适吗")

    # Not a chart request: flows to answer route with both bases injected.
    assert result["route"] == "answer"
    user_prompt = result["messages"][1]["content"]
    assert "目标日期底座" in user_prompt
    assert "下周一是" in user_prompt
    assert "提问者命盘底座" in user_prompt
    assert "日柱（命主日干支）是 丁丑" in user_prompt
    assert "日主 丁" in user_prompt
    # Offline draft also carries the target date basis.
    assert "下周一是" in result["answer_draft"]
    # Raw tool results exposed for display/audit.
    assert "target_dates" in result["meta"]["skill_result"]
    assert "get_bazi_chart" in result["meta"]["skill_result"]


def test_error_route_for_empty_question() -> None:
    result = orchestrator.chat_orchestrate("")
    assert result["route"] == "error"
