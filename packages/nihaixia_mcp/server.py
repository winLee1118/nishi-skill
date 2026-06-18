from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

from nihaixia_core.calendar import bazi_chart, calendar_report, four_pillars
from nihaixia_core.graph import related_concepts
from nihaixia_core.persona import persona_guidance
from nihaixia_core.retrieval import search_with_info
from nihaixia_core.safety import medical_intent, safety_notes
from nihaixia_core.text import classify_domain

CONCISE_ANSWER_TERMS = (
    "只回答我一句话",
    "只回答一句话",
    "只回答一句",
    "一句话回答",
    "用一句话",
    "一句话说",
    "一句话讲",
    "一句话",
    "简短回答",
    "简洁回答",
    "简单回答",
    "直接回答",
    "直接说结论",
    "只说结论",
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None


mcp = FastMCP("nihaixia-system") if FastMCP else None


def mcp_tool():
    if mcp is None:
        return lambda func: func
    return mcp.tool()


def db_path() -> str:
    return os.getenv("NIHAIXIA_DB", "data/nihaixia.sqlite")


def graph_path() -> str:
    return os.getenv("NIHAIXIA_GRAPH", "knowledge/graph")


@mcp_tool()
def classify_question(question: str) -> dict:
    """Classify a question into renji, tianji, diji, cross, or auto."""
    return {"domain": classify_domain(question)}


@mcp_tool()
def search_sources(question: str, domain: str = "auto", top_k: int = 5, mode: str = "auto") -> dict:
    """Search indexed source chunks with fts or optional hybrid retrieval."""
    results, info = search_with_info(question, db_path(), domain=domain, top_k=top_k, mode=mode)
    return {"retrieval": info, "results": [asdict(item) for item in results]}


@mcp_tool()
def get_related_concepts(concept: str, depth: int = 1) -> dict:
    """Return graph relations connected to a concept."""
    return {"concept": concept, "relations": related_concepts(concept, graph_path(), depth=depth)}


@mcp_tool()
def answer_with_citations(
    question: str,
    domain: str = "auto",
    top_k: int = 5,
    style_intensity: str = "medium",
    mode: str = "auto",
    output_format: str = "chat",
    history: list | None = None,
) -> dict:
    """Return a citation-first answer draft plus controlled persona-style guidance.

    output_format="chat" returns a conversational draft without markdown or numbered
    lists; output_format="report" keeps the legacy structured draft.
    history is an optional list of {"role", "content"} dicts used for follow-up
    context in domain classification and retrieval.
    """
    selected_format = output_format if output_format in {"chat", "report"} else "chat"
    recent_user_texts = recent_user_messages(history)
    selected_domain = resolve_domain(question, domain, recent_user_texts)
    if is_casual_greeting(question):
        results = []
        info = {
            "retrieval_mode": "skipped_greeting",
            "requested_mode": mode,
            "fallback": False,
            "warnings": [],
        }
    else:
        search_text = build_search_text(question, recent_user_texts)
        results, info = search_with_info(search_text, db_path(), domain=selected_domain, top_k=top_k, mode=mode)
    citations = [
        {
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "title": item.title,
            "course": item.course,
            "chapter": item.chapter,
            "timestamp": item.timestamp,
            "page": item.page,
            "source_url": item.source_url,
            "rights_status": item.rights_status,
        }
        for item in results
    ]
    retrieval_hits = [
        {
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "title": item.title,
            "course": item.course,
            "chapter": item.chapter,
            "timestamp": item.timestamp,
            "page": item.page,
            "source_url": item.source_url,
            "rights_status": item.rights_status,
            "snippet": item.snippet,
            "score": item.score,
            "match_source": item.match_source,
        }
        for item in results
    ]
    answer = build_answer_draft(question, selected_domain, results, output_format=selected_format)
    persona = persona_guidance(selected_domain, style_intensity)
    notes = safety_notes(question, selected_domain)
    evidence_plan = build_evidence_plan(results, citations, info)
    style_plan = build_style_plan(selected_domain, persona)
    safety_plan = build_safety_plan(question, selected_domain, notes)
    persona_composition = build_persona_composition(evidence_plan, style_plan, safety_plan)
    return {
        "domain": selected_domain,
        "output_format": selected_format,
        "retrieval": info,
        "evidence_plan": evidence_plan,
        "style_plan": style_plan,
        "safety_plan": safety_plan,
        "persona_composition": persona_composition,
        "persona": persona,
        "style_prompt": persona.get("style_prompt", ""),
        "answer": answer,
        "citations": citations,
        "retrieval_hits": retrieval_hits,
        "safety_notes": notes,
    }


def build_evidence_plan(results: list[Any], citations: list[dict[str, Any]], retrieval: dict[str, Any]) -> dict[str, Any]:
    top_sources = [
        {
            "source_id": item["source_id"],
            "title": item["title"],
            "course": item["course"],
            "chapter": item["chapter"],
            "rights_status": item["rights_status"],
        }
        for item in citations[:3]
    ]
    warnings = [str(item) for item in retrieval.get("warnings", [])]
    limitations: list[str] = []
    if not results:
        limitations.append("当前没有直接命中足够资料，回答只能给检索建议或学习框架。")
    if retrieval.get("fallback"):
        limitations.append("本次检索发生回退，应优先按返回的 retrieval_mode 解释结果。")

    return {
        "has_evidence": bool(results),
        "citation_count": len(citations),
        "retrieval_mode": retrieval.get("retrieval_mode", "unknown"),
        "requested_mode": retrieval.get("requested_mode", "unknown"),
        "fallback": bool(retrieval.get("fallback", False)),
        "top_sources": top_sources,
        "warnings": warnings,
        "limitations": limitations,
        "use_rules": [
            "先使用 citations 对应的命中资料，不用风格补证据。",
            "没有命中时说明资料不足，给出可继续检索的关键词方向。",
            "引用只来自 citations，不编造 source_id、页码或时间戳。",
        ],
    }


def build_style_plan(domain: str, persona: dict[str, object]) -> dict[str, Any]:
    profile = persona.get("style_profile", {})
    fingerprint_version = ""
    active_weights: dict[str, object] = {}
    if isinstance(profile, dict):
        active_weights = dict(profile.get("style_weights", {})) if isinstance(profile.get("style_weights"), dict) else {}
        fingerprint = profile.get("video_style_fingerprint", {})
        if isinstance(fingerprint, dict):
            fingerprint_version = str(fingerprint.get("version", ""))

    domain_focus = {
        "renji": "人纪：先放回辨证/方证/经典框架，再讲学习性解释。",
        "tianji": "天纪：先看象与结构，不作绝对命运判断。",
        "diji": "地纪：先看空间格局与使用状态，不作恐吓式判断。",
        "cross": "跨域：只有证据支持时才连接天、地、人。",
    }.get(domain, "按已分类领域选择讲解框架。")

    return {
        "style_intensity": persona.get("style_intensity", "medium"),
        "identity": persona.get("identity", ""),
        "fingerprint_version": fingerprint_version,
        "active_weights": active_weights,
        "domain_focus": domain_focus,
        "style_prompt": persona.get("style_prompt", ""),
        "composition_rules": [
            "风格只改变讲解节奏和表达结构，不改变证据含义。",
            "优先使用短问句、直接判断、正反对比和例子落地。",
            "普通学习问题自然讲，不反复声明边界。",
        ],
    }


def build_safety_plan(question: str, domain: str, notes: list[str]) -> dict[str, Any]:
    medical = medical_intent(question, domain)
    identity_request = has_identity_request(question)
    fate_request = has_absolute_fate_request(question)
    if identity_request or medical == "prescription_request":
        risk_level = "high"
    elif medical == "clinical_caution" or fate_request or domain in {"tianji", "diji", "cross"}:
        risk_level = "medium"
    else:
        risk_level = "ordinary"

    boundary_style = {
        "ordinary": "不硬性免责声明，自然讲解。",
        "medium": "保持讲课口吻，柔性提示资料边界。",
        "high": "先保留数字分身口吻，再明确收住身份、诊断、处方或绝对判断边界。",
    }[risk_level]

    return {
        "risk_level": risk_level,
        "medical_intent": medical,
        "identity_request": identity_request,
        "absolute_fate_request": fate_request,
        "boundary_style": boundary_style,
        "notes": notes,
        "must_not": [
            "不声称自己是倪海厦本人。",
            "不编造私人记忆、临床经历或未检索到的来源。",
            "不替代诊断、处方、剂量或个人治疗决策。",
            "不作绝对命运、恐吓式风水或保证结果的判断。",
        ],
    }


def has_identity_request(question: str) -> bool:
    return any(term in question for term in ("你是倪海厦", "你就是倪海厦", "扮演倪海厦", "以倪海厦本人", "假装倪海厦"))


def has_absolute_fate_request(question: str) -> bool:
    return any(term in question for term in ("一定", "必然", "绝对", "必死", "没救", "注定"))


def build_persona_composition(
    evidence_plan: dict[str, Any],
    style_plan: dict[str, Any],
    safety_plan: dict[str, Any],
) -> dict[str, Any]:
    if evidence_plan["has_evidence"]:
        evidence_instruction = f"使用 {evidence_plan['citation_count']} 条 citation 支撑回答。"
    else:
        evidence_instruction = "没有足够 citation 时，只给学习框架和继续检索方向。"

    return {
        "composition_order": ["evidence_plan", "style_plan", "safety_plan", "answer"],
        "summary": (
            f"{evidence_instruction}"
            f"风格强度为 {style_plan['style_intensity']}，风险等级为 {safety_plan['risk_level']}。"
            "回答时先证据、再风格、最后按需柔性收边界。"
        ),
        "final_answer_rules": [
            "先按用户意图给普通回答，不输出编排字段、规则清单或思考过程。",
            "将 evidence_plan、style_plan 和 safety_plan 作为内部控制信号，不要把字段名或计划内容粘贴给用户。",
            "检索资料、知识图谱和风格画像用于支撑与润色答案，不替代 LLM 底座的正常对话能力。",
            "遇到 safety_plan 标出的风险时，用柔性边界收住，不切换成生硬免责声明。",
            "不要让 persona 风格覆盖 evidence_plan 的限制。",
        ],
    }


def is_casual_greeting(question: str) -> bool:
    normalized = "".join(str(question or "").strip().lower().split())
    compact = normalized.translate(str.maketrans("", "", "，。！？、,.!?~～；;：:"))
    if compact in {"你好", "您好", "嗨", "hi", "hello", "hey", "在吗", "在不在"}:
        return True
    connection_checks = (
        "听到我说话",
        "能听到我",
        "听得到我",
        "听见我",
        "听得到吗",
        "听得到么",
        "听见了吗",
        "能听见吗",
        "麦克风",
        "声音能听到",
        "连上了吗",
        "通了吗",
    )
    return any(term in compact for term in connection_checks)


def wants_concise_answer(question: str) -> bool:
    normalized = "".join(str(question or "").split())
    return any(term in normalized for term in CONCISE_ANSWER_TERMS)


def recent_user_messages(history: list | None, limit: int = 8) -> list[str]:
    if not isinstance(history, list):
        return []
    texts: list[str] = []
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            texts.append(content)
        if len(texts) >= limit:
            break
    return texts


def resolve_domain(question: str, domain: str, recent_user_texts: list[str]) -> str:
    if domain != "auto":
        return domain
    classified = classify_domain(question)
    if classified != "auto":
        return classified
    for text in recent_user_texts:
        contextual = classify_domain(text)
        if contextual != "auto":
            return contextual
    return classified


def build_search_text(question: str, recent_user_texts: list[str]) -> str:
    # Short follow-ups like "继续说" or "你直接告诉我" carry no retrieval signal on
    # their own; fold in the latest user turns so retrieval keeps the topic.
    if len(question.strip()) >= 8 or not recent_user_texts:
        return question
    return "\n".join([question, *recent_user_texts[:2]])


def build_answer_draft(question: str, domain: str, results: list, output_format: str = "chat") -> str:
    if is_casual_greeting(question):
        return ""

    if output_format == "report":
        return build_report_draft(question, domain, results)
    return build_chat_draft(question, domain, results)


def build_report_draft(question: str, domain: str, results: list) -> str:
    evidence = "\n".join(f"- {item.snippet}" for item in results[:3])
    intro = "按已索引资料，我先给你一个学习用草稿；后面保留引用，方便你追来源。"
    intent = medical_intent(question, domain)
    if intent in {"clinical_caution", "prescription_request"}:
        return "\n\n".join(
            [
                intro,
                build_medical_learning_frame(question, intent, bool(results)),
                f"资料命中：\n{evidence}" if evidence else "资料命中：当前索引没有直接命中足够片段，建议改用症状词、病机词或方名继续检索。",
            ]
        )
    if domain == "tianji":
        return "\n\n".join(
            [
                intro,
                build_tianji_learning_frame(question, bool(results)),
                f"资料命中：\n{evidence}" if evidence else "资料命中：当前索引没有直接命中具体卦名，先按象义和结构做学习分析。",
            ]
        )
    return f"{intro}\n\n{evidence or '未检索到足够资料。'}"


def chat_evidence_text(results: list) -> str:
    snippets = []
    for item in results[:2]:
        snippet = clean_chat_snippet(item)
        if snippet:
            snippets.append(snippet[:160] + ("..." if len(snippet) > 160 else ""))
    if not snippets:
        return ""
    if len(snippets) == 1:
        return f"资料里讲到：{snippets[0]}"
    return f"资料里讲到：{snippets[0]} 另外一段也相关：{snippets[1]}"


def clean_chat_snippet(item: Any) -> str:
    snippet = str(getattr(item, "snippet", "") or "").strip()
    if not snippet:
        return ""
    prefix = "..." if snippet.startswith("...") else ""
    marker = "; entities:"
    if marker not in snippet:
        return snippet

    tail = snippet.split(marker, 1)[1].strip()
    for entity in sorted(getattr(item, "entities", []) or [], key=len, reverse=True):
        entity = str(entity).strip()
        if entity and tail.startswith(entity):
            tail = tail[len(entity) :].lstrip(" ,，;；")
            break
    return (prefix + tail).strip()


def build_chat_draft(question: str, domain: str, results: list) -> str:
    intent = medical_intent(question, domain)
    if wants_concise_answer(question):
        return build_concise_chat_draft(question, domain, results, intent)
    evidence = chat_evidence_text(results)
    if intent in {"clinical_caution", "prescription_request"}:
        frame = build_medical_chat_frame(question, intent, bool(results))
        return "\n\n".join(part for part in [frame, evidence] if part)
    if domain == "tianji":
        frame = build_tianji_learning_frame(question, bool(results))
        return "\n\n".join(part for part in [frame, evidence] if part)
    if evidence:
        return f"{evidence}\n\n先看原则，再对照你的具体情况；有不清楚的地方可以接着问。"
    return "这个问题我这里没有检索到很贴近的资料，先不把话说死。你可以把具体的症状、卦象、时间或场景说清楚一点，我再按体系帮你往下梳理。"


def build_concise_chat_draft(question: str, domain: str, results: list, intent: str) -> str:
    if "桂枝汤" in question:
        return "桂枝汤一般用于太阳中风、恶风发热、有汗、脉浮缓这类方证；具体能不能喝，要看当下症状辨证。"
    if intent in {"clinical_caution", "prescription_request"}:
        return "这类问题要先辨清主证和急症信号，不能凭一句话决定用药或剂量。"
    if domain == "tianji":
        return "一句话说，先看象和结构，不要把趋势讲成绝对断语。"
    if domain == "diji":
        return "一句话说，先看空间格局和实际使用状态，不要脱离现场硬断吉凶。"
    if results:
        return "一句话说，资料有相关线索，但要回到原文方证和具体场景对照，不能脱离条件硬套。"
    return "一句话说，我这里没有检索到足够贴近资料，先别下定论，把具体场景补清楚再判断。"


def build_tianji_learning_frame(question: str, has_evidence: bool) -> str:
    evidence_hint = (
        "下面的资料命中只能作结构参考，不作绝对断语。"
        if has_evidence
        else "这次没有直接命中具体卦名，所以只能先作结构化学习分析，不作绝对断语。"
    )
    if any(term in question for term in ("大泽", "兑卦", "兑为泽", "泽卦")):
        return (
            "先看象，不要急着断吉凶。\n\n"
            "你说“大泽”，如果按兑为泽的象来抓，重点在“悦”、在“口”、在沟通、吸引、交换。"
            "问感情，重点不是一句成不成，而是看双方说话是不是舒服，互动是不是有来有往，"
            "以及好听的话能不能落到行动。\n\n"
            "这里要分清楚：兑的好处是容易靠近、容易聊天、有愉悦感；兑的问题是容易停在表面，"
            "甜是甜，实不实要另外看。所以最近感情可以看作有互动、有话题、有靠近机会，"
            "但不要只听话，要看对方有没有稳定行动。\n\n"
            f"{evidence_hint}"
        )
    if "感情" in question:
        return (
            "先看象，再看人事，不要一句话定死。\n\n"
            "感情问题最怕只问结果，不看结构。天纪这里要看的是：现在双方有没有沟通，"
            "有没有阻隔，谁主动谁被动，话说出来以后有没有行动承接。"
            "如果只有情绪热、话很多、承诺少，那就是表面有象，内里未实。\n\n"
            f"{evidence_hint}"
        )
    return (
        "先抓结构，不急着下断语。\n\n"
        "天纪问题要先看象、看位、看动静，再落到人事。能讲趋势和结构，"
        "不能把它讲成绝对命运。你要问结果，我先看这个象在提醒哪一种关系、哪一种取舍。\n\n"
        f"{evidence_hint}"
    )


def build_medical_learning_frame(question: str, intent: str, has_evidence: bool) -> str:
    boundary = (
        "怎么办呢，先不要急着落到某一味药或某一个方。"
        "这里可以按经方资料做学习辨证，但不能直接替你生成个人处方、剂量或用药决定。"
        if intent == "prescription_request"
        else "先把症状放回辨证框架里看。这里可以讲经方资料里的方向，但不直接替你下诊断。"
    )
    evidence_hint = "下面的资料命中只能作为学习依据。" if has_evidence else "这次没有直接命中足够资料，所以先给辨证追问框架。"
    return f"{boundary}\n\n{medical_question_checklist(question)}\n\n{evidence_hint}"


def build_medical_chat_frame(question: str, intent: str, has_evidence: bool) -> str:
    boundary = (
        "怎么办呢，先不要急着问吃什么药。"
        "我可以按经方资料帮你做学习辨证，但不能替你开方定剂量，这一步要交给当面看诊的医师。"
        if intent == "prescription_request"
        else "先把症状放回辨证框架里看，不急着下结论。"
    )
    evidence_hint = "" if has_evidence else "我这里没有直接命中很贴近的资料，所以先帮你把要问清楚的东西理出来。"
    return "\n\n".join(part for part in [boundary, medical_chat_questions(question), evidence_hint] if part)


def medical_chat_questions(question: str) -> str:
    if any(term in question for term in ("失眠", "睡不着", "多梦", "早醒")):
        return (
            "失眠不能只看“睡不着”三个字。你先告诉我：是躺下睡不着，还是睡着以后容易醒，还是凌晨早早就醒了？"
            "有没有心烦、口苦、胃胀反酸、夜尿、盗汗、怕冷这些跟着的症状？"
            "最近有没有咖啡茶酒、熬夜、情绪压力，或者晚饭吃得太饱？"
            "白天是疲倦想睡，还是烦躁亢奋？这几个分清楚了，方向就出来了。"
            "经方学习上要看心神、少阳、痰饮、胃不和这些路子：有的人是胃不和卧不安，有的人是心烦热扰，有的人是虚烦。"
            "要注意，如果连续多日彻夜不眠，或者有明显焦虑、心悸胸痛，那要先及时就医。"
        )
    if any(term in question for term in ("肚子痛", "腹痛", "胃痛", "肚子疼", "腹疼")):
        return (
            "肚子痛先看急不急，再谈辨证。你先告诉我：痛在哪里，是上腹、肚脐周围还是小腹？"
            "是绞着痛、胀痛、刺痛还是隐隐作痛？跟吃饭、受凉、排便有没有关系？"
            "要是有发烧、呕吐、黑便血便、肚子变硬、越来越重这些信号，先去就医，不要拖。"
            "经方学习上，腹痛要分寒热虚实、气滞食积，不能一个痛字就定方。"
        )
    if any(term in question for term in ("口干", "舌燥", "胃胀", "腹胀")):
        return (
            "这里要分清楚。口干舌燥，是渴得想喝冷水，想喝热水，还是只是口干但不想喝？"
            "胃胀是饭后胀、空腹也胀，还是带着反酸嗳气恶心？大便是干结、黏滞还是腹泻？"
            "这些分清楚了，寒热虚实、津液和中焦运化的方向才看得出来。"
            "要是有发热、腹痛、持续呕吐、黑便这些情况，先及时就医。"
        )
    return (
        "先看几个关键的地方。症状是什么时候开始的，突然来的还是慢慢加重的？"
        "有没有怕冷发热、出汗、口渴，大小便、胃口、睡眠怎么样，痛在哪个位置？"
        "最近饮食、作息、情绪、受寒受热有没有明显变化？"
        "经方学习上，先抓主证和伴随证，再谈可能相关的方证。"
        "要是有剧烈疼痛、出血、胸痛、呼吸困难、持续高热这些急症信号，先就医，不要等。"
    )


def medical_question_checklist(question: str) -> str:
    if any(term in question for term in ("失眠", "睡不着", "多梦", "早醒")):
        return (
            "失眠先不要只问“吃什么”，要分清它是哪一种睡不着：\n"
            "1. 是入睡困难，还是睡着以后容易醒，还是凌晨早醒？\n"
            "2. 有没有心烦、口苦、胸胁胀、胃胀、反酸、夜尿、盗汗、怕冷？\n"
            "3. 最近有没有咖啡茶酒、熬夜、情绪压力、晚饭过饱或运动太晚？\n"
            "4. 白天精神怎样，是疲倦想睡，还是烦躁亢奋？\n"
            "5. 有没有连续多日彻夜不眠、明显焦虑抑郁、心悸胸痛等需要及时就医的信号？\n\n"
            "经方学习上，失眠不能只看“睡不着”三个字，要看心神、少阳、痰饮、胃不和、阴阳出入这些方向。"
            "有的人是胃不和卧不安，有的人是心烦热扰，有的人是虚烦，有的人是水饮或压力牵动。"
        )
    if any(term in question for term in ("肚子痛", "腹痛", "胃痛", "肚子疼", "腹疼")):
        return (
            "肚子痛先看急不急，再谈辨证：\n"
            "1. 痛在哪里：上腹、脐周、右下腹、左下腹，还是整片痛？\n"
            "2. 怎么痛：绞痛、胀痛、刺痛、隐痛、烧灼痛？\n"
            "3. 跟吃饭、受凉、排便、月经有没有关系？\n"
            "4. 有没有发烧、呕吐、黑便血便、腹部变硬、持续加重等急症信号？\n\n"
            "经方学习上，腹痛要分寒热虚实、气滞食积、少阳太阴阳明，不能一个痛字就定方。"
        )
    if any(term in question for term in ("口干", "舌燥", "胃胀", "腹胀")):
        return (
            "先看几个关键问题：\n"
            "1. 口干舌燥是口渴想冷饮、想热饮，还是只是口干不想喝？\n"
            "2. 胃胀是饭后胀、空腹胀，还是伴随反酸、嗳气、恶心？\n"
            "3. 大便是干结、黏滞、腹泻，还是正常？\n"
            "4. 有没有发热、腹痛、胸痛、持续呕吐、黑便、明显脱水等需要及时就医的信号？\n\n"
            "经方学习上，不能只凭“口干 + 胃胀”就定方，要看寒热、虚实、表里、津液和中焦运化。"
        )
    return (
        "先看几个关键问题：\n"
        "1. 症状从什么时候开始，是突然还是慢慢来的？\n"
        "2. 有没有寒热、汗出、口渴、大小便、胃口、睡眠、疼痛位置这些伴随信息？\n"
        "3. 最近饮食、作息、情绪、受寒受热有没有明显变化？\n"
        "4. 有没有剧烈疼痛、出血、胸痛、呼吸困难、持续高热、意识异常等急症信号？\n\n"
        "经方学习上，先抓主证和伴随证，再谈可能相关的方证。"
    )


@mcp_tool()
def get_persona_guidance(domain: str = "auto", style_intensity: str = "medium") -> dict:
    """Return controlled language style and personality guidance without source retrieval."""
    return {"domain": domain, "persona": persona_guidance(domain, style_intensity)}


@mcp_tool()
def safety_check(question: str, domain: str = "auto") -> dict:
    """Return safety notes for a question/domain pair."""
    selected_domain = classify_domain(question) if domain == "auto" else domain
    return {"domain": selected_domain, "safety_notes": safety_notes(question, selected_domain)}


@mcp_tool()
def convert_calendar(datetime_text: str, timezone: str = "Asia/Shanghai") -> dict:
    """Convert a Gregorian datetime to lunar date and Ganzhi time parameters."""
    try:
        return calendar_report(datetime_text, timezone=timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        return calendar_error(exc)


@mcp_tool()
def get_ganzhi(
    datetime_text: str,
    timezone: str = "Asia/Shanghai",
    day_boundary: str = "23:00",
) -> dict:
    """Return year/month/day/hour Ganzhi pillars for a Gregorian datetime."""
    try:
        return four_pillars(datetime_text, timezone=timezone, day_boundary=day_boundary)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        return calendar_error(exc)


@mcp_tool()
def get_bazi_chart(
    datetime_text: str,
    timezone: str = "Asia/Shanghai",
    gender: str = "unknown",
    location: str = "",
    use_true_solar_time: bool = False,
    day_boundary: str = "23:00",
    luck_cycle_count: int = 8,
    annual_start_year: int | None = None,
    annual_years: int = 10,
) -> dict:
    """Return a structured Four Pillars/Bazi chart for study-oriented analysis."""
    try:
        return bazi_chart(
            datetime_text,
            timezone=timezone,
            gender=gender,
            location=location,
            use_true_solar_time=use_true_solar_time,
            day_boundary=day_boundary,
            luck_cycle_count=luck_cycle_count,
            annual_start_year=annual_start_year,
            annual_years=annual_years,
        )
    except (ValueError, ZoneInfoNotFoundError) as exc:
        return calendar_error(exc)


@mcp_tool()
def get_ziwei_inputs(
    datetime_text: str,
    timezone: str = "Asia/Shanghai",
    gender: str = "unknown",
    location: str = "",
    use_true_solar_time: bool = False,
) -> dict:
    """Return lunar and Ganzhi inputs needed before Ziwei Doushu charting."""
    try:
        chart = bazi_chart(
            datetime_text,
            timezone=timezone,
            gender=gender,
            location=location,
            use_true_solar_time=use_true_solar_time,
            annual_years=0,
        )
    except (ValueError, ZoneInfoNotFoundError) as exc:
        return calendar_error(exc)
    return {
        "input": chart["input"],
        "lunar": chart["lunar"],
        "pillars": chart["pillars"],
        "day_master": chart["day_master"],
        "nayin": chart["nayin"],
        "rules": chart["rules"],
        "notes": [
            "这是紫微斗数起盘前置参数，不包含完整星曜排盘。",
            *chart["notes"],
        ],
    }


@mcp_tool()
def get_fengshui_time(
    datetime_text: str,
    timezone: str = "Asia/Shanghai",
    day_boundary: str = "23:00",
) -> dict:
    """Return time parameters used by Diji/feng-shui or date-selection study."""
    try:
        pillars = four_pillars(datetime_text, timezone=timezone, day_boundary=day_boundary)
        chart = bazi_chart(datetime_text, timezone=timezone, day_boundary=day_boundary, annual_years=0)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        return calendar_error(exc)
    return {
        "input": {"datetime": pillars["datetime"], "timezone": timezone},
        "pillars": pillars["pillars"],
        "nayin": chart["nayin"],
        "month_boundary_term": pillars["month_boundary_term"],
        "rules": pillars["rules"],
        "notes": [
            "这是地纪/风水/择日学习用时间底座，不包含完整择日体系。",
            *pillars["notes"],
        ],
    }


def calendar_error(exc: Exception) -> dict:
    return {
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
    }


def main() -> None:
    if mcp is None:
        raise SystemExit("Install MCP support with: pip install -e . or pip install mcp")
    # Imported here (not at module top) to register the chat_orchestrate tool
    # without creating a circular import: orchestrator imports from this module.
    from . import orchestrator  # noqa: F401

    mcp.run()


if __name__ == "__main__":
    main()
