from __future__ import annotations

from nihaixia_core.text import make_fts_query, query_terms


def test_query_terms_drop_filler_and_expand_insomnia() -> None:
    terms = query_terms("我最近失眠")

    assert "失眠" in terms
    assert "最近" not in terms
    assert "酸枣仁汤" in terms
    assert "黄连阿胶汤" in terms


def test_make_fts_query_does_not_prioritize_recent_noise() -> None:
    query = make_fts_query("我最近失眠")

    assert '"失眠"' in query
    assert '"最近"' not in query


def test_late_sleep_query_drops_generic_harm_word_and_expands() -> None:
    terms = query_terms("晚睡有坏处吗")

    assert "晚睡" in terms
    assert "坏处" not in terms
    assert "伤到津液" in terms
