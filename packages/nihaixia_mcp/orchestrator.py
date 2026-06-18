"""Unified chat orchestration entry for the Ni Haixia skill.

This is the single standard entry that any caller (desktop app, MCP agent,
mini-program backend, CLI) should use for chat-style interaction. It owns:

- question routing (Bazi chart vs. knowledge answer)
- deterministic tool invocation (convert_calendar / get_ganzhi / get_bazi_chart)
- real-time calendar basis injection: "today"-dependent questions (今天干支/
  流日/运势) stay on the answer route, with the computed time basis folded into
  the draft and the LLM prompt as a parameter, so answers keep the persona
  style and can interpret the numbers instead of echoing a fixed template
- LLM prompt composition (system + user messages) for the answer route
- the chat output-format contract (plain conversational text, no markdown)

Callers should not re-implement routing or prompt assembly. Three ways to call:

1. Python import:    from nihaixia_mcp.orchestrator import chat_orchestrate
2. MCP tool:         chat_orchestrate (registered on the nihaixia-system server)
3. Subprocess JSON:  echo '{"question": "..."}' | python -m nihaixia_mcp.orchestrator
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nihaixia_core.chat_text import sanitize_chat_text
from nihaixia_core.persona import CHAT_FORMAT_RULES, persona_guidance

from .server import (
    answer_with_citations,
    convert_calendar,
    get_bazi_chart,
    get_ganzhi,
    mcp_tool,
    wants_concise_answer,
)

WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# ---------------------------------------------------------------------------
# Weighted intent scoring.
#
# Routing intents are decided by weighted term scores (same idea as
# classify_domain in nihaixia_core.text), not by binary regex AND-matches:
# every signal term carries a weight, terms found in recent user history count
# with a decay factor, and an intent fires only above its threshold. This keeps
# routing robust to phrasing like "生我日柱丁丑吗" that single-pattern regexes miss.

# "When is now" references.
TIME_REF_WEIGHTS = {
    "今天": 2.0,
    "今日": 2.0,
    "现在": 2.0,
    "当前": 1.5,
    "此刻": 1.5,
    "今晚": 1.5,
    "这会儿": 1.0,
    "明天": 1.5,
}
# Topics that need the current calendar/Ganzhi basis to be answered.
# There is deliberately NO separate fixed-template calendar route: time-related
# questions always flow through retrieval + persona + LLM with the computed
# time basis injected as a parameter, so the answer keeps the persona style and
# can interpret (生克/运势) instead of just echoing numbers.
TIME_TOPIC_WEIGHTS = {
    "几号": 3.0,
    "流日": 3.0,
    "日柱": 2.5,
    "运势": 2.5,
    "干支": 2.5,
    "农历": 2.5,
    "天干": 2.0,
    "地支": 2.0,
    "四柱": 2.0,
    "八字": 2.0,
    "时辰": 2.0,
    "日期": 2.0,
    "星期": 2.0,
    "阴历": 2.0,
    "节气": 2.0,
    "流月": 2.5,
    "流年": 2.0,
    "年柱": 2.0,
    "月柱": 2.0,
    "时柱": 2.0,
    "日主": 2.0,
    "宜忌": 2.0,
    "吉凶": 2.0,
    "纳音": 2.0,
    "十神": 2.0,
    "命理": 1.5,
    "五行": 1.5,
    "卦": 1.0,
}
# Asking for a birth chart (paired with a structurally parsed birth datetime).
BAZI_CHART_WEIGHTS = {
    "八字": 3.0,
    "排盘": 3.0,
    "命盘": 3.0,
    "四柱": 2.5,
    "乾造": 2.5,
    "坤造": 2.5,
    "男命": 2.5,
    "女命": 2.5,
    "干支": 2.0,
    "出生": 1.5,
    "生的": 1.0,
}
# Short follow-ups that mean "just compute it" once birth info exists upstream.
BAZI_FOLLOWUP_WEIGHTS = {
    "直接告诉": 1.5,
    "直接说": 1.5,
    "算出来": 1.5,
    "排出来": 1.5,
    "告诉我": 1.0,
}

HISTORY_DECAY = 0.5
TIME_REF_THRESHOLD = 1.0
TIME_TOPIC_THRESHOLD = 1.5
BAZI_CHART_THRESHOLD = 2.0
BAZI_FOLLOWUP_THRESHOLD = 1.0

BIRTH_YEAR_RE = re.compile(r"(\d{2,4})\s*年")
BIRTH_DATE_RE = re.compile(r"\d{2,4}\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)?")
BIRTH_TIME_RE = re.compile(r"(\d{1,2})\s*[:：点]\s*(\d{1,2})?")
MALE_RE = re.compile(r"男|男性|男命|乾造|男生")
FEMALE_RE = re.compile(r"女|女性|女命|坤造|女生")

# Relative/explicit date references ("下周一去买车合适吗") are resolved to real
# dates so the flow-day Ganzhi can be computed deterministically.
RELATIVE_DAY_OFFSETS = {"明天": 1, "明日": 1, "后天": 2, "大后天": 3}
WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
WEEK_REF_RE = re.compile(r"(下下|下|这个?|本)(?:周|星期|礼拜)([一二三四五六日天])")
EXPLICIT_DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")


@mcp_tool()
def chat_orchestrate(
    question: str,
    history: list | None = None,
    timezone: str = "Asia/Shanghai",
    domain: str = "auto",
    top_k: int = 5,
    mode: str = "auto",
    style_intensity: str = "medium",
) -> dict:
    """Single chat entry: route the question (calendar/bazi/answer), run skill
    tools, and return either a final tool answer or LLM-ready messages plus
    citations and metadata.

    Returns a dict with: route, answer_draft, draft_is_final, messages,
    citations, and meta (domain, persona, safety, retrieval, skill invocation
    and raw tool results).
    """
    question = str(question or "").strip()
    if not question:
        return _error_result("question is empty")

    normalized_history = _normalized_history(history)

    if _wants_bazi_chart(question, normalized_history):
        return _run_bazi_route(question, normalized_history, timezone)

    return _run_answer_route(
        question,
        normalized_history,
        timezone=timezone,
        domain=domain,
        top_k=top_k,
        mode=mode,
        style_intensity=style_intensity,
    )


# ---------------------------------------------------------------------------
# Routing predicates


def _user_history_text(history: list[dict[str, str]]) -> str:
    return "\n".join(item["content"] for item in history if item["role"] == "user")


def _intent_score(weights: dict[str, float], question: str, history_text: str = "") -> float:
    """Weighted term score: full weight in the current question, decayed weight
    for terms that only appear in recent user history."""
    score = sum(weight for term, weight in weights.items() if term in question)
    if history_text:
        score += HISTORY_DECAY * sum(
            weight for term, weight in weights.items() if term not in question and term in history_text
        )
    return score


def _needs_time_context(question: str, history: list[dict[str, str]]) -> bool:
    history_text = _user_history_text(history)
    time_ref = _intent_score(TIME_REF_WEIGHTS, question, history_text)
    topic = _intent_score(TIME_TOPIC_WEIGHTS, question, history_text)
    return time_ref >= TIME_REF_THRESHOLD and topic >= TIME_TOPIC_THRESHOLD


def _wants_bazi_chart(question: str, history: list[dict[str, str]]) -> bool:
    text = "\n".join([question, *(item["content"] for item in history)])
    has_birth_time = bool(BIRTH_DATE_RE.search(text)) and bool(BIRTH_TIME_RE.search(text))
    if not has_birth_time:
        return False
    history_text = _user_history_text(history)
    chart_score = _intent_score(BAZI_CHART_WEIGHTS, question, history_text)
    followup_score = _intent_score(BAZI_FOLLOWUP_WEIGHTS, question)
    return chart_score >= BAZI_CHART_THRESHOLD or followup_score >= BAZI_FOLLOWUP_THRESHOLD


def _normalized_history(history: list | None, limit: int = 24) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized[-limit:]


def _pillar_ganzhi(pillars: dict, key: str) -> str:
    pillar = pillars.get(key)
    if isinstance(pillar, dict):
        return str(pillar.get("ganzhi") or "")
    return ""


# ---------------------------------------------------------------------------
# Bazi route


def _parse_birth_input(question: str, history: list[dict[str, str]]) -> dict | None:
    texts = [question]
    for item in reversed(history):
        if item["role"] == "user":
            texts.append(item["content"])
    source = "\n".join(texts)

    year_match = BIRTH_YEAR_RE.search(source)
    date_match = BIRTH_DATE_RE.search(source)
    time_match = BIRTH_TIME_RE.search(source)
    if not (year_match and date_match and time_match):
        return None

    year = int(year_match.group(1))
    if year < 100:
        year = 1900 + year if year >= 30 else 2000 + year
    month = int(date_match.group(1))
    day = int(date_match.group(2))
    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    if MALE_RE.search(source):
        gender = "男"
    elif FEMALE_RE.search(source):
        gender = "女"
    else:
        gender = "unknown"

    return {
        "datetime_text": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
        "time_text": f"{hour:02d}:{minute:02d}",
        "gender": gender,
    }


def _run_bazi_route(question: str, history: list[dict[str, str]], timezone: str) -> dict:
    birth = _parse_birth_input(question, history)
    safety = ["四柱排盘用于传统命理学习和结构分析，不作绝对命运判断；贴近节气交接或跨时区出生时建议复核。"]

    if birth is None:
        answer = "你这句要排干支，但我还缺完整的公历出生年月日和时间。格式可以这样给：1979年11月6日20:30，男性。"
        return {
            "route": "bazi",
            "answer_draft": answer,
            "draft_is_final": True,
            "messages": [],
            "citations": [],
            "meta": {
                "domain": "tianji",
                "persona": {},
                "safety_notes": safety,
                "medical_intent": "none",
                "retrieval_info": {"tool": "get_bazi_chart", "routed": True, "matched": False},
                "skill_invocation": {},
                "skill_result": {},
            },
        }

    chart = get_bazi_chart(
        birth["datetime_text"],
        timezone=timezone,
        gender=birth["gender"],
        annual_years=0,
    )
    if "error" in chart:
        return _error_result(str(chart["error"]))

    answer = _build_bazi_answer(birth, timezone, chart)
    persona = persona_guidance("tianji", "medium")
    messages = compose_bazi_messages(question, history, answer, persona, safety)
    return {
        "route": "bazi",
        "answer_draft": answer,
        "draft_is_final": False,
        "messages": messages,
        "citations": [],
        "meta": {
            "domain": "tianji",
            "persona": {
                "style_intensity": persona.get("style_intensity"),
                "identity": persona.get("identity"),
                "style_prompt": persona.get("style_prompt"),
            },
            "safety_notes": safety,
            "medical_intent": "none",
            "retrieval_info": {
                "tool": "get_bazi_chart",
                "routed": True,
                "datetime_text": birth["datetime_text"],
                "timezone": timezone,
                "gender": birth["gender"],
            },
            "skill_invocation": {
                "package": "nihaixia_mcp.server",
                "tool": "get_bazi_chart",
                "args": {
                    "datetime_text": birth["datetime_text"],
                    "timezone": timezone,
                    "gender": birth["gender"],
                    "annual_years": 0,
                },
            },
            "skill_result": {"get_bazi_chart": chart},
        },
    }


def _build_bazi_answer(birth: dict, timezone: str, chart: dict) -> str:
    pillars = chart.get("pillars", {})
    year = _pillar_ganzhi(pillars, "year")
    month = _pillar_ganzhi(pillars, "month")
    day = _pillar_ganzhi(pillars, "day")
    hour = _pillar_ganzhi(pillars, "hour")
    lunar = chart.get("lunar") or {}
    nayin = chart.get("nayin") or {}
    ten_gods = chart.get("ten_gods") or {}
    lunar_text = (
        f"{lunar.get('year_ganzhi') or year}年{lunar.get('month_name') or ''}{lunar.get('day_name') or ''}"
        if lunar
        else ""
    )
    # Derive the hour-branch name from the actual hour pillar instead of any
    # hardcoded example time.
    hour_branch = hour[1] if len(hour) >= 2 else ""

    gender_text = f"{birth['gender']}命" if birth["gender"] != "unknown" else "未注明性别"
    lines = [
        f"按公历 {birth['datetime_text']}（{gender_text}）排，四柱是：",
        f"{year}年、{month}月、{day}日、{hour}时。",
        f"农历是{lunar_text}，生肖{lunar.get('zodiac') or ''}。" if lunar_text else "",
        (
            f"这里要分清楚：出生时间 {birth['time_text']} 落在{hour_branch}时，所以时柱是 {hour}。"
            f"月柱按节气，不按农历初一；这一天在“{chart.get('month_boundary_term') or '节气'}”节气月内。"
        ),
        (
            f"纳音：年柱{nayin.get('year')}、月柱{nayin.get('month')}、日柱{nayin.get('day')}、时柱{nayin.get('hour')}。"
            if nayin
            else ""
        ),
        (
            f"以日主 {chart.get('day_master') or ''} 来看，年干{ten_gods.get('year')}，月干{ten_gods.get('month')}，时干{ten_gods.get('hour')}。"
            if ten_gods
            else ""
        ),
        "如果出生地不在中国标准时间地区，或要校正真太阳时，需要再给出生地复核。",
    ]
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------------
# Knowledge answer route


def _resolve_date_references(text: str, now: datetime) -> list[dict]:
    """Resolve relative ("明天", "下周一") and explicit ("6月18日") date references
    to concrete dates, excluding spans that are part of a birth datetime."""
    targets: list[dict] = []
    seen: set = set()

    def add(label: str, date_value) -> None:
        if date_value not in seen:
            seen.add(date_value)
            targets.append({"label": label, "date": date_value})

    for term, offset in RELATIVE_DAY_OFFSETS.items():
        if term in text:
            add(term, (now + timedelta(days=offset)).date())

    for match in WEEK_REF_RE.finditer(text):
        prefix, day_char = match.groups()
        weekday = WEEKDAY_INDEX[day_char]
        if prefix in ("这", "这个", "本"):
            delta = weekday - now.weekday()
        else:
            delta = 7 - now.weekday() + weekday
            if prefix == "下下":
                delta += 7
        add(match.group(0), (now + timedelta(days=delta)).date())

    birth_spans = [match.span() for match in BIRTH_DATE_RE.finditer(text)]
    for match in EXPLICIT_DATE_RE.finditer(text):
        if any(start <= match.start() < end for start, end in birth_spans):
            continue
        month, day = int(match.group(1)), int(match.group(2))
        try:
            date_value = now.date().replace(month=month, day=day)
        except ValueError:
            continue
        if (date_value - now.date()).days < -180:
            try:
                date_value = date_value.replace(year=date_value.year + 1)
            except ValueError:
                continue
        add(match.group(0), date_value)

    return targets[:3]


def _target_date_lines(targets: list[dict], timezone: str) -> tuple[list[str], dict]:
    lines: list[str] = []
    results: dict = {}
    for target in targets:
        date_value = target["date"]
        # Noon avoids the 23:00 Zi-hour day-boundary shifting the day pillar.
        pillars = get_ganzhi(f"{date_value.isoformat()} 12:00", timezone=timezone)
        if "error" in pillars:
            continue
        day_ganzhi = _pillar_ganzhi(pillars.get("pillars", {}), "day")
        month_ganzhi = _pillar_ganzhi(pillars.get("pillars", {}), "month")
        year_ganzhi = _pillar_ganzhi(pillars.get("pillars", {}), "year")
        weekday = WEEKDAYS[date_value.weekday()]
        lines.append(
            f"{target['label']}是 {date_value.isoformat()}（{weekday}），"
            f"当日干支：{year_ganzhi}年、{month_ganzhi}月、{day_ganzhi}日，流日是 {day_ganzhi}。"
        )
        results[target["label"]] = {"date": date_value.isoformat(), "ganzhi": pillars}
    return lines, results


def _build_time_context(timezone: str, question: str, history: list[dict[str, str]]) -> dict | None:
    """Compute the current calendar/Ganzhi basis (and any referenced target
    dates such as 下周一) so time-dependent questions can be answered instead of
    claiming the date is unknown."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return None

    text_all = "\n".join([question, _user_history_text(history)])
    targets = _resolve_date_references(text_all, now)
    if not targets and not _needs_time_context(question, history):
        return None

    datetime_text = now.isoformat()
    converted = convert_calendar(datetime_text, timezone=timezone)
    ganzhi = get_ganzhi(datetime_text, timezone=timezone)
    if "error" in converted or "error" in ganzhi:
        return None

    lunar = converted.get("lunar", {})
    pillars = ganzhi.get("pillars", {})
    year = _pillar_ganzhi(pillars, "year")
    month = _pillar_ganzhi(pillars, "month")
    day = _pillar_ganzhi(pillars, "day")
    hour = _pillar_ganzhi(pillars, "hour")
    target_lines, target_results = _target_date_lines(targets, timezone)

    text = (
        f"公历 {now.strftime('%Y-%m-%d %H:%M')} {WEEKDAYS[now.weekday()]}（{timezone}）；"
        f"农历{lunar.get('year_ganzhi') or year}年{lunar.get('month_name') or ''}{lunar.get('day_name') or ''}，"
        f"生肖{lunar.get('zodiac') or ''}；"
        f"当前四柱干支：{year}年、{month}月、{day}日、{hour}时（流日即日柱 {day}）；"
        f"当前节气月以“{ganzhi.get('month_boundary_term') or '节气'}”为界。"
    )
    if target_lines:
        text += "目标日期底座：" + "".join(target_lines)

    # Conversational lead-in so the offline draft also carries the real numbers.
    draft_line = (
        f"先看时间底座：今天是 {now.strftime('%Y-%m-%d')}，{WEEKDAYS[now.weekday()]}，"
        f"农历{lunar.get('year_ganzhi') or year}年{lunar.get('month_name') or ''}{lunar.get('day_name') or ''}；"
        f"干支是{year}年、{month}月、{day}日、{hour}时，流日（日柱）是{day}。"
    )
    if target_lines:
        draft_line += "".join(target_lines)

    skill_result: dict = {"convert_calendar": converted, "get_ganzhi": ganzhi}
    if target_results:
        skill_result["target_dates"] = target_results

    return {
        "text": text,
        "draft_line": draft_line,
        "skill_invocation": {
            "package": "nihaixia_mcp.server",
            "tools": ["convert_calendar", "get_ganzhi"],
            "args": {"datetime_text": datetime_text, "timezone": timezone, "target_dates": [t["label"] for t in targets]},
        },
        "skill_result": skill_result,
    }


def _build_birth_context(question: str, history: list[dict[str, str]], timezone: str) -> dict | None:
    """When the user states a full birth datetime in an interpretation question
    (择日/运势), chart it deterministically and feed the pillars to the LLM."""
    birth = _parse_birth_input(question, history)
    if birth is None:
        return None
    chart = get_bazi_chart(birth["datetime_text"], timezone=timezone, gender=birth["gender"], annual_years=0)
    if "error" in chart:
        return None
    pillars = chart.get("pillars", {})
    year = _pillar_ganzhi(pillars, "year")
    month = _pillar_ganzhi(pillars, "month")
    day = _pillar_ganzhi(pillars, "day")
    hour = _pillar_ganzhi(pillars, "hour")
    lunar = chart.get("lunar") or {}
    text = (
        f"提问者出生 {birth['datetime_text']}（{timezone}，{birth['gender']}），"
        f"四柱：{year}年、{month}月、{day}日、{hour}时，日柱（命主日干支）是 {day}，日主 {chart.get('day_master') or ''}，"
        f"生肖{lunar.get('zodiac') or ''}。"
    )
    return {
        "text": text,
        "skill_result": {"get_bazi_chart": chart},
    }


def _run_answer_route(
    question: str,
    history: list[dict[str, str]],
    timezone: str,
    domain: str,
    top_k: int,
    mode: str,
    style_intensity: str,
) -> dict:
    result = answer_with_citations(
        question,
        domain=domain,
        top_k=top_k,
        style_intensity=style_intensity,
        mode=mode,
        output_format="chat",
        history=history,
    )
    time_context = _build_time_context(timezone, question, history)
    birth_context = _build_birth_context(question, history, timezone)
    draft = str(result.get("answer") or "")
    if time_context:
        # The offline fallback must also state the real date/Ganzhi, so the
        # computed basis leads the draft instead of living only in the prompt.
        draft = f"{time_context['draft_line']}\n\n{draft}" if draft else str(time_context["draft_line"])
    persona = result.get("persona", {})
    safety_plan = result.get("safety_plan", {})
    messages = compose_chat_messages(
        question,
        history,
        draft=draft,
        citations=list(result.get("citations") or []),
        retrieval_info=dict(result.get("retrieval") or {}),
        persona=persona,
        domain=str(result.get("domain") or domain),
        safety_notes=list(result.get("safety_notes") or []),
        evidence_plan=dict(result.get("evidence_plan") or {}),
        style_plan=dict(result.get("style_plan") or {}),
        safety_plan=safety_plan,
        time_context_text=str(time_context["text"]) if time_context else "",
        birth_context_text=str(birth_context["text"]) if birth_context else "",
    )

    return {
        "route": "answer",
        "answer_draft": draft,
        "draft_is_final": False,
        "messages": messages,
        "citations": result.get("citations", []),
        "retrieval_hits": result.get("retrieval_hits", []),
        "meta": {
            "domain": result.get("domain", domain),
            "persona": {
                "style_intensity": persona.get("style_intensity"),
                "identity": persona.get("identity"),
                "style_prompt": persona.get("style_prompt"),
            },
            "safety_notes": result.get("safety_notes", []),
            "medical_intent": safety_plan.get("medical_intent", "none"),
            "retrieval_info": result.get("retrieval", {}),
            "retrieval_hits": result.get("retrieval_hits", []),
            "evidence_plan": result.get("evidence_plan", {}),
            "style_plan": result.get("style_plan", {}),
            "safety_plan": safety_plan,
            "persona_composition": result.get("persona_composition", {}),
            "skill_invocation": {
                "package": "nihaixia_mcp.orchestrator",
                "tool": "chat_orchestrate",
                "inner_tool": "answer_with_citations",
                "time_context_tools": time_context["skill_invocation"] if time_context else {},
                "args": {
                    "domain": domain,
                    "top_k": top_k,
                    "style_intensity": style_intensity,
                    "mode": mode,
                    "output_format": "chat",
                },
            },
            "skill_result": {
                **(time_context["skill_result"] if time_context else {}),
                **(birth_context["skill_result"] if birth_context else {}),
            },
        },
    }


# ---------------------------------------------------------------------------
# Bazi prompt composition


def compose_bazi_messages(
    question: str,
    history: list[dict[str, str]],
    draft: str,
    persona: dict,
    safety_notes: list[str],
) -> list[dict[str, str]]:
    safety_plan = {
        "risk_level": "medium",
        "medical_intent": "none",
        "boundary_style": "保持讲课口吻，柔性提示排盘边界。",
        "must_not": [
            "不声称自己是倪海厦本人。",
            "不输出工具名、函数名、内部字段名或程序调用过程。",
            "不输出英文时区标识、timezone 字段、排盘工具函数名等实现细节。",
            "不作绝对命运判断。",
        ],
    }
    system_prompt = _build_system_prompt(persona, "tianji", safety_notes, safety_plan)
    history_lines = []
    for item in history[-8:]:
        role_label = "用户" if item["role"] == "user" else "你"
        content = item["content"]
        if len(content) > 160:
            content = content[:160] + "..."
        history_lines.append(f"{role_label}：{content}")

    user_prompt = "\n\n".join(
        part
        for part in [
            f"用户问题：{question}",
            f"最近对话：\n{chr(10).join(history_lines)}" if history_lines else "",
            f"确定排盘数据：\n{draft}",
            (
                "任务：把确定排盘数据包装成用户可直接阅读的回答。四柱、农历、生肖、辰时、节气月、纳音和十神这些事实不能改；"
                "只调整语气、节奏和说明顺序。"
            ),
            (
                "表达要求：带一点倪师讲课的口吻，先直接报四柱，再点出时辰和月令按节气的关键，不要像程序报告。"
                "不要输出工具名、函数名、内部字段名、英文时区标识或程序调用过程。"
                "最后只用自然话提醒：若出生地不在中国标准时间地区，或要细校真太阳时，需要补出生地复核。"
            ),
            "请用中文输出纯对话文本，不用 Markdown 标题、编号列表或表格。",
        ]
        if part
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ---------------------------------------------------------------------------
# Prompt composition (the single source of truth for chat prompts)


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [str(item).strip() for item in value if str(item or "").strip()]
    return items[:limit]


def _answer_length_instruction(question: str) -> str:
    if wants_concise_answer(question):
        return "用户明确要求短答：最终回答只能写一句话，不要展开资料原文、不要补多段解释；若涉及用药，句内保留辨证和就医边界。"
    return ""


def compose_chat_messages(
    question: str,
    history: list[dict[str, str]],
    draft: str,
    citations: list[dict],
    retrieval_info: dict,
    persona: dict,
    domain: str,
    safety_notes: list[str],
    evidence_plan: dict,
    style_plan: dict,
    safety_plan: dict,
    time_context_text: str = "",
    birth_context_text: str = "",
) -> list[dict[str, str]]:
    """Build the system+user messages for the final LLM generation step."""
    system_prompt = _build_system_prompt(persona, domain, safety_notes, safety_plan)
    user_prompt = _build_user_prompt(
        question,
        history,
        draft,
        citations,
        retrieval_info,
        evidence_plan,
        style_plan,
        safety_plan,
        time_context_text,
        birth_context_text,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_system_prompt(persona: dict, domain: str, safety_notes: list[str], safety_plan: dict) -> str:
    style_prompt = str(persona.get("style_prompt") or "")
    identity = str(persona.get("identity") or "")
    intensity = str(persona.get("style_intensity") or "medium")
    instructions = _string_list(persona.get("instructions"), 8)
    avoid = _string_list(persona.get("avoid"), 6)
    medical = str(safety_plan.get("medical_intent") or "none")

    parts = [
        style_prompt,
        f"身份控制：{identity}" if identity else "",
        f"风格强度：{intensity}。风格不是可选装饰，必须体现在回答节奏里。",
        f"风格执行要点：{'；'.join(instructions)}" if instructions else "",
        f"禁止事项：{'；'.join(avoid)}" if avoid else "",
        f"当前领域：{domain}。",
        f"医学意图：{medical}。",
        "你是基于已索引资料和风格画像生成的倪海厦体系数字分身，不声称自己是倪海厦本人，也不要自称“健康助手”“AI助手”或“医生”。",
        "先像正常人一样理解用户意图并直接回答；检索资料、知识图谱和风格画像只作为支撑与润色。",
        "回答要像讲课聊天：先抓一个判断点，再分清结构，最后落到追问或生活场景。可以用“先看...”“这里要分清楚”“重点不是...而是...”这类短句推进。",
        "遇到具体症状时，不给个人诊断、处方、剂量；先问位置、痛法、寒热、大小便、饮食诱因和急症信号。",
        "问候或闲聊只需自然回应，不要说明检索状态、回答原则或内部规则。",
        CHAT_FORMAT_RULES,
        f"安全边界：{'；'.join(safety_notes)}" if safety_notes else "",
    ]
    return "\n".join(part for part in parts if part)


def _build_user_prompt(
    question: str,
    history: list[dict[str, str]],
    draft: str,
    citations: list[dict],
    retrieval_info: dict,
    evidence_plan: dict,
    style_plan: dict,
    safety_plan: dict,
    time_context_text: str = "",
    birth_context_text: str = "",
) -> str:
    history_lines = []
    for item in history[-12:]:
        role_label = "用户" if item["role"] == "user" else "你"
        content = item["content"]
        if len(content) > 200:
            content = content[:200] + "..."
        history_lines.append(f"{role_label}：{content}")

    limitations = _string_list(evidence_plan.get("limitations"), 3)
    must_not = _string_list(safety_plan.get("must_not"), 4)
    boundary_style = str(safety_plan.get("boundary_style") or "")
    domain_focus = str(style_plan.get("domain_focus") or "")
    length_instruction = _answer_length_instruction(question)
    casual_instruction = (
        "用户只是问候或测试语音/连接：只自然确认一两句，不展开知识讲解，不引入资料、方剂、症状例子或课程内容。"
        if retrieval_info.get("retrieval_mode") == "skipped_greeting"
        else ""
    )
    has_evidence = bool(citations) or bool(draft)

    parts = [
        f"用户问题：{question}",
        f"最近对话：\n{chr(10).join(history_lines)}" if history_lines else "",
        (
            f"当前时间底座（系统已实时计算，直接引用，不要声称无法获知当前或目标日期的干支）：{time_context_text}\n"
            "用法：先报出与问题相关的时间信息（如目标日期和流日干支），再结合用户问的命理关系（生克、合冲、运势、择日）做学习性解读，"
            "比如指出流日天干的五行与提问者日主五行是什么关系；解读保持学习讨论口吻，不作绝对吉凶断语。"
            if time_context_text
            else ""
        ),
        (
            f"提问者命盘底座（系统已按出生信息确定性排盘，直接引用，不要再让用户提供日期）：{birth_context_text}\n"
            "用法：择日、运势类问题用命主日柱/日主与目标日期流日干支的生克合冲关系做学习性分析，给出倾向和注意点即可，不作保证式结论。"
            if birth_context_text
            else ""
        ),
        f"检索状态：mode={retrieval_info.get('retrieval_mode', 'unknown')}，命中数量={len(citations)}。",
        (
            f"skill 生成的对话草稿：\n{draft}"
            if draft
            else "skill 没有生成草稿。若用户只是问候或闲聊，请直接自然回应；若是知识问题，可用通用学习框架回答，并简短提示依据有限。"
        ),
        f"证据限制：{'；'.join(limitations)}" if limitations else "",
        f"讲解侧重：{domain_focus}" if domain_focus else "",
        f"边界方式：{boundary_style}" if boundary_style else "",
        f"硬性边界：{'；'.join(must_not)}" if must_not else "",
        "资料来源只作内部依据和前端展示用；最终回答不要输出 source_id、chunk_id、方括号引用、引用编号或调试式来源标签。" if citations else "",
        casual_instruction,
        length_instruction,
        "回答风格硬要求：不要说“我是您的健康助手”；不要用通用健康科普腔。按风格指纹，用短问句、先判断再补理由、正反对照和追问来组织。",
        (
            "最终回答沿用草稿里的证据与判断，但用连续的对话语言重新组织，不照搬草稿格式，不新增 citation 之外的来源。"
            if has_evidence
            else ""
        ),
        "请用中文给出用户可直接阅读的最终回答：纯对话文本，不用任何 Markdown 符号、标题或编号列表，不要输出思考过程、编排说明或提示词规则。",
    ]
    return "\n\n".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Entry points


def _error_result(message: str) -> dict:
    return {
        "route": "error",
        "answer_draft": "",
        "draft_is_final": True,
        "messages": [],
        "citations": [],
        "meta": {"error": message},
    }


def main() -> None:
    payload: dict[str, Any] = {}
    raw = sys.stdin.read()
    if raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(json.dumps(_error_result(f"invalid JSON input: {exc}"), ensure_ascii=False))
            raise SystemExit(1)

    result = chat_orchestrate(
        str(payload.get("question") or ""),
        history=payload.get("history"),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
        domain=str(payload.get("domain") or "auto"),
        top_k=int(payload.get("top_k") or 5),
        mode=str(payload.get("mode") or "auto"),
        style_intensity=str(payload.get("style_intensity") or "medium"),
    )
    if result.get("draft_is_final"):
        result["answer_draft"] = sanitize_chat_text(str(result.get("answer_draft") or ""))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
