from __future__ import annotations

import sqlite3
from uuid import uuid4
from pathlib import Path

from nihaixia_core.retrieval import search
from nihaixia_core.subtitle_ingest import import_subtitle_directory


def test_import_subtitles_builds_searchable_chunks(monkeypatch) -> None:
    monkeypatch.setenv("NIHAIXIA_SQLITE_JOURNAL_MODE", "OFF")
    workspace_tmp = Path("test_artifacts") / f"test_subtitle_ingest_{uuid4().hex}"
    srt_root = workspace_tmp / "private" / "jianying-subtitles" / "split"
    source_dir = srt_root / "人纪"
    source_dir.mkdir(parents=True)
    (source_dir / "倪海厦《伤寒论》测试.srt").write_text(
        "\n".join(
            [
                "1",
                "00:00:01,000 --> 00:00:03,000",
                "太阳病这个时候先看表证",
                "",
                "2",
                "00:00:03,300 --> 00:00:06,000",
                "不是先补而是先解表对不对",
                "",
            ]
        ),
        encoding="utf-8",
    )
    db_path = workspace_tmp / "nihaixia.sqlite"

    stats = import_subtitle_directory(srt_root, db_path, project_root=workspace_tmp, max_chars=200)

    assert stats["sources"] == 1
    assert stats["chunks"] == 1
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT source_type, rights_status, notes FROM sources").fetchone()
    conn.close()
    assert row == ("subtitle", "unknown", "private_local_subtitle; local-only full SRT transcript for retrieval, not style prompt injection.")

    results = search("太阳病先解表", db_path, domain="renji", top_k=3, mode="fts")

    assert results
    assert results[0].title == "倪海厦《伤寒论》测试"
    assert "先解表" in results[0].snippet
    assert results[0].timestamp == "00:00:01,000 --> 00:00:06,000"
