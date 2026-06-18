"""Chat-channel text sanitizer.

The chat/TTS channel of this project renders plain conversational text, so any
markdown the LLM emits (headings, bold, numbered lists, bullets, tables, code
fences) would show up as raw symbols. ``sanitize_chat_text`` strips that
formatting while keeping the wording, turning list markers into spoken Chinese
connectives.
"""

from __future__ import annotations

import re

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
NUMBERED_RE = re.compile(r"^\s*(\d{1,2})\s*[\.、)）]\s+")
BULLET_RE = re.compile(r"^\s*[-*•·]\s+")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
UNDERLINE_BOLD_RE = re.compile(r"__(.+?)__")
INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")
CODE_FENCE_RE = re.compile(r"^\s*```.*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
MULTI_BLANK_RE = re.compile(r"\n{3,}")

ORDINALS = ("一是", "二是", "三是", "四是", "五是", "六是", "七是", "八是", "九是", "十是")


def sanitize_chat_text(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if CODE_FENCE_RE.match(line):
            continue
        if TABLE_ROW_RE.match(line) and TABLE_RULE_RE.match(line):
            continue
        line = HEADING_RE.sub("", line)
        line = BULLET_RE.sub("", line)
        line = _replace_numbered_marker(line)
        if TABLE_ROW_RE.match(line):
            line = _flatten_table_row(line)
        cleaned.append(line)

    result = "\n".join(cleaned)
    result = BOLD_RE.sub(r"\1", result)
    result = UNDERLINE_BOLD_RE.sub(r"\1", result)
    result = ITALIC_RE.sub(r"\1", result)
    result = INLINE_CODE_RE.sub(r"\1", result)
    result = MULTI_BLANK_RE.sub("\n\n", result)
    return result.strip()


def _replace_numbered_marker(line: str) -> str:
    match = NUMBERED_RE.match(line)
    if not match:
        return line
    index = int(match.group(1))
    rest = line[match.end() :]
    if 1 <= index <= len(ORDINALS):
        return f"{ORDINALS[index - 1]}{rest}"
    return rest


def _flatten_table_row(line: str) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return "，".join(cell for cell in cells if cell)
