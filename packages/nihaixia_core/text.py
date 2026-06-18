from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

CJK_RE = re.compile(r"[\u3400-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z0-9_+-]+")

QUERY_FILLERS = (
    "你好",
    "您好",
    "今天",
    "我最近",
    "最近",
    "这几天",
    "这两天",
    "这段时间",
    "有点",
    "感觉",
    "最近有点",
    "有坏处吗",
    "有坏处",
    "坏处吗",
    "吗",
)

QUERY_EXPANSIONS = {
    "失眠": ("睡不着", "不得眠", "虚烦", "心烦", "酸枣仁汤", "栀子豉汤", "黄连阿胶汤"),
    "睡不着": ("失眠", "不得眠", "虚烦", "心烦", "酸枣仁汤", "栀子豉汤", "黄连阿胶汤"),
    "晚睡": ("睡眠", "作息", "津液", "伤到津液", "乾咳", "痰饮"),
    "肚子痛": ("腹痛", "胃痛", "胃疼", "腹胀", "下利", "便秘", "寒热"),
    "肚子疼": ("腹痛", "肚子痛", "胃痛", "胃疼", "腹胀", "下利", "便秘", "寒热"),
    "腹疼": ("腹痛", "肚子痛", "肚子疼", "胃痛", "胃疼", "腹胀", "寒热"),
    "胃疼": ("胃痛", "腹痛", "肚子痛", "肚子疼", "反酸", "嗳气", "恶心", "中焦"),
    "胃胀": ("腹胀", "胃不和", "反酸", "嗳气", "恶心", "中焦"),
    "口干": ("口渴", "舌燥", "津液", "烦热"),
}


DOMAIN_ALIASES = {
    "renji": ("人纪", "中医", "伤寒", "金匮", "针灸", "经方", "本草", "内经", "太阳病", "少阳", "厥阴"),
    "tianji": (
        "天纪",
        "易经",
        "命理",
        "八字",
        "干支",
        "天干",
        "地支",
        "五行",
        "卦",
        "河图",
        "洛书",
        "四柱",
        "日柱",
        "年柱",
        "月柱",
        "时柱",
        "日主",
        "流年",
        "流月",
        "流日",
        "大运",
        "运势",
        "纳音",
        "十神",
        "紫微",
        "斗数",
    ),
    "diji": ("地纪", "风水", "阳宅", "阴宅", "方位", "地理", "形势", "理气", "罗盘"),
}

DOMAIN_LABELS = {
    "renji": "人纪",
    "tianji": "天纪",
    "diji": "地纪",
    "cross": "跨域",
    "auto": "自动",
}

RENJI_INTENT_TERMS = (
    "失眠",
    "睡不着",
    "晚睡",
    "睡眠",
    "作息",
    "口干",
    "舌燥",
    "口渴",
    "胃胀",
    "腹胀",
    "肚子痛",
    "肚子疼",
    "腹痛",
    "腹疼",
    "胃痛",
    "胃疼",
    "恶心",
    "反酸",
    "便秘",
    "腹泻",
    "发烧",
    "咳嗽",
    "吃点什么药",
    "吃什么药",
    "用什么药",
    "处方",
)


def stable_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    return value.strip("'\"")


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown

    metadata: dict[str, Any] = {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = parse_scalar(value)

    if end_index is None:
        return {}, markdown
    body = "\n".join(lines[end_index + 1 :]).strip()
    return metadata, body


def ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def cjk_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> list[str]:
    grams: list[str] = []
    for match in CJK_RE.finditer(text):
        segment = match.group(0)
        for size in range(min_n, max_n + 1):
            if len(segment) < size:
                continue
            grams.extend(segment[i : i + size] for i in range(len(segment) - size + 1))
    return grams


def lexical_terms(text: str) -> list[str]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    grams = cjk_ngrams(text)
    seen: set[str] = set()
    terms: list[str] = []
    for term in words + grams:
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def query_terms(text: str) -> list[str]:
    cleaned = normalize_query_text(text)
    terms = lexical_terms(cleaned)
    expanded: list[str] = []
    for trigger, additions in QUERY_EXPANSIONS.items():
        if trigger in cleaned:
            expanded.extend(additions)
    seen: set[str] = set()
    merged: list[str] = []
    for term in terms + expanded:
        if term not in seen:
            seen.add(term)
            merged.append(term)
    return merged


def normalize_query_text(text: str) -> str:
    cleaned = text
    for filler in QUERY_FILLERS:
        cleaned = cleaned.replace(filler, "")
    return cleaned.strip() or text


def fts_payload(*parts: str) -> str:
    text = "\n".join(part for part in parts if part)
    return f"{text}\n\n{' '.join(lexical_terms(text))}"


def classify_domain(question: str) -> str:
    if any(term in question for term in RENJI_INTENT_TERMS):
        return "renji"
    scores = {domain: 0 for domain in DOMAIN_ALIASES}
    for domain, aliases in DOMAIN_ALIASES.items():
        for alias in aliases:
            if alias.lower() in question.lower():
                scores[domain] += max(1, len(alias) // 2)
    best_domain, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score == 0:
        return "auto"
    tied = [domain for domain, score in scores.items() if score == best_score]
    return "cross" if len(tied) > 1 else best_domain


def make_fts_query(question: str, limit: int = 24) -> str:
    terms = query_terms(question)[:limit]
    if not terms:
        return escape_fts_term(question)
    return " OR ".join(escape_fts_term(term) for term in terms)


def escape_fts_term(term: str) -> str:
    cleaned = term.replace('"', " ").strip()
    if not cleaned:
        return '""'
    return f'"{cleaned}"'


def compact_snippet(text: str, query: str, max_chars: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    for token in query_terms(query):
        index = normalized.lower().find(token.lower())
        if index >= 0:
            start = max(0, index - max_chars // 3)
            end = min(len(normalized), start + max_chars)
            prefix = "..." if start else ""
            suffix = "..." if end < len(normalized) else ""
            return f"{prefix}{normalized[start:end]}{suffix}"
    return normalized[:max_chars] + "..."


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def iter_markdown_files(vault: str | Path) -> list[Path]:
    root = Path(vault)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())
