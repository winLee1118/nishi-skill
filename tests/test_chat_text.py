from __future__ import annotations

from nihaixia_core.chat_text import sanitize_chat_text


def test_strips_markdown_headings() -> None:
    assert sanitize_chat_text("## 先看原则\n内容") == "先看原则\n内容"


def test_strips_bold_and_italic_and_inline_code() -> None:
    assert sanitize_chat_text("**重点**不是看症状，*而是*辨证，用 `桂枝汤` 举例") == "重点不是看症状，而是辨证，用 桂枝汤 举例"


def test_numbered_list_becomes_spoken_connectives() -> None:
    text = "1. 先看寒热\n2. 再看虚实\n3. 最后看表里"
    assert sanitize_chat_text(text) == "一是先看寒热\n二是再看虚实\n三是最后看表里"


def test_bullet_list_markers_removed() -> None:
    assert sanitize_chat_text("- 桂枝汤\n* 麻黄汤") == "桂枝汤\n麻黄汤"


def test_table_flattened_and_rule_row_dropped() -> None:
    text = "| 方名 | 主证 |\n|---|---|\n| 桂枝汤 | 中风 |"
    assert sanitize_chat_text(text) == "方名，主证\n桂枝汤，中风"


def test_code_fence_lines_dropped() -> None:
    assert sanitize_chat_text("```python\nprint(1)\n```") == "print(1)"


def test_collapses_extra_blank_lines() -> None:
    assert sanitize_chat_text("第一段\n\n\n\n第二段") == "第一段\n\n第二段"


def test_plain_chat_text_unchanged() -> None:
    text = "先看原则。这里要分清楚：营卫不和，重点不是出汗多少，而是营卫的开合。"
    assert sanitize_chat_text(text) == text


def test_empty_input() -> None:
    assert sanitize_chat_text("") == ""
