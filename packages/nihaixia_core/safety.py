from __future__ import annotations


MEDICAL_TERMS = (
    "病",
    "症",
    "药",
    "方",
    "剂量",
    "针灸",
    "疼",
    "痛",
    "失眠",
    "癌",
    "肿瘤",
    "诊断",
    "治疗",
    "口干",
    "舌燥",
    "胃胀",
    "胃疼",
    "恶心",
    "腹疼",
    "便秘",
    "腹泻",
    "发烧",
    "晚睡",
    "睡眠",
    "作息",
)
PRESCRIPTION_TERMS = (
    "吃什么药",
    "用什么药",
    "吃点什么药",
    "开什么方",
    "开方",
    "处方",
    "剂量",
    "能不能吃",
    "该吃什么",
    "要不要吃",
)
FATE_TERMS = ("一定", "必然", "绝对", "必死", "没救", "注定")


def medical_intent(question: str, domain: str) -> str:
    if domain != "renji" and not any(term in question for term in MEDICAL_TERMS):
        return "none"
    if any(term in question for term in PRESCRIPTION_TERMS):
        return "prescription_request"
    if any(term in question for term in MEDICAL_TERMS):
        return "clinical_caution"
    return "study_ok"


def safety_notes(question: str, domain: str) -> list[str]:
    notes: list[str] = []
    intent = medical_intent(question, domain)
    if intent == "study_ok":
        notes.append("可以讨论资料中的经方方义、辨证框架和原文脉络，但仍应区分学习解释和个人医疗决策。")
    elif intent == "clinical_caution":
        notes.append("可以按资料讲辨证方向、相关经方思路和需要补问的信息；不构成诊断、处方或个人治疗建议。")
    elif intent == "prescription_request":
        notes.append("可以讲资料中的经方适应证、禁忌和辨证追问；不构成诊断，不能直接替你生成个人处方、剂量或用药决定。")
    if domain in ("tianji", "diji", "cross") or any(term in question for term in FATE_TERMS):
        notes.append("天纪/地纪相关内容应作为传统文化学习和结构化分析，不作绝对化、恐吓式或宿命化判断。")
    notes.append("不能冒充倪海厦本人，应保持基于资料和风格画像生成的透明数字分身身份。")
    return notes
