from __future__ import annotations

from nihaixia_core.persona import load_style_fingerprint, persona_guidance
from nihaixia_core.safety import medical_intent, safety_notes
from nihaixia_mcp.server import build_answer_draft, is_casual_greeting


def test_persona_guidance_returns_data_driven_fingerprint() -> None:
    persona = persona_guidance("renji", "high")
    profile = persona["style_profile"]

    assert persona["identity"] == "基于已索引倪海厦体系资料与语言风格画像生成的数字分身。"
    assert "video_style_fingerprint" in profile
    assert "style_weights" in profile
    assert profile["style_weights"]["questioning"] > 0
    assert "怎么办呢" in persona["style_prompt"]
    assert "风格摘要" in persona["style_prompt"]
    assert "profile=" not in persona["style_prompt"]


def test_style_fingerprint_loads_v02_subtitle_distillation() -> None:
    fingerprint = load_style_fingerprint()

    assert fingerprint["version"] == "0.2"
    assert fingerprint["source"]["sample_count"] == 220
    assert "对不对" in fingerprint["phrase_patterns"]
    assert any(move["id"] == "question_loop" for move in fingerprint["teaching_moves"])


def test_style_fingerprint_falls_back_when_file_is_missing() -> None:
    fingerprint = load_style_fingerprint("__missing_style_fingerprint__.json")

    assert fingerprint["version"] == "fallback"
    assert fingerprint["teaching_moves"]
    assert "high" in fingerprint["intensity_weights"]


def test_medical_boundary_allows_formula_study_without_personal_prescription() -> None:
    question = "今天口干舌燥，胃胀，不舒服吃点什么药"

    assert medical_intent(question, "renji") == "prescription_request"
    notes = "\n".join(safety_notes(question, "renji"))

    assert "经方适应证" in notes
    assert "不能直接替你生成个人处方" in notes


def test_medical_boundary_recognizes_abdominal_pain_synonyms() -> None:
    assert medical_intent("你好，今天肚子疼", "renji") == "clinical_caution"


def test_tianji_answer_uses_symbol_first_style() -> None:
    answer = build_answer_draft("我抽了一个大泽卦，问最近感情如何", "tianji", [])

    assert "先看象" in answer
    assert "兑为泽" in answer
    assert "不作绝对断语" in answer


def test_greeting_answer_is_not_orchestration_report() -> None:
    answer = build_answer_draft("你好", "auto", [])

    assert answer == ""
    assert "原则" not in answer
    assert "结构解释" not in answer
    assert "当前回答说明" not in answer


def test_voice_connection_greeting_does_not_swallow_symptom_question() -> None:
    assert is_casual_greeting("你好，听到我说话了吗？") is True
    assert is_casual_greeting("你好，今天肚子疼") is False
