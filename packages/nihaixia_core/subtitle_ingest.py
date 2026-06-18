from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import connect
from .text import fts_payload, json_dumps, stable_id


TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")
SOURCE_ID_PREFIX = "subtitle:"
IMPORT_MARKER = "private_local_subtitle"


@dataclass(slots=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True)
class SubtitleChunk:
    index: int
    start_ms: int
    end_ms: int
    text: str


def parse_time(value: str) -> int:
    match = TIME_RE.search(value)
    if not match:
        raise ValueError(f"Invalid SRT time: {value}")
    h, m, s, ms = (int(part) for part in match.groups())
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def format_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clean_subtitle_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", "", value)
    return value.strip()


def read_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for block in [item.strip() for item in raw.split("\n\n") if item.strip()]:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        time_index = 1 if len(lines) > 1 and "-->" in lines[1] else 0
        if "-->" not in lines[time_index]:
            continue
        start_text, end_text = lines[time_index].split("-->", 1)
        text = clean_subtitle_text("".join(lines[time_index + 1 :]))
        if not text:
            continue
        cues.append(Cue(parse_time(start_text), parse_time(end_text), text))
    return cues


def infer_domain(category: str, title: str) -> str:
    haystack = f"{category} {title}"
    if "人纪" in haystack or any(term in haystack for term in ("针灸", "伤寒", "金匮", "内经", "本草", "临床", "问诊")):
        return "renji"
    if "天纪" in haystack or any(term in haystack for term in ("易经", "四柱", "紫微", "命卦", "斗数")):
        return "tianji"
    if "地纪" in haystack or any(term in haystack for term in ("阳宅", "风水", "地理")):
        return "diji"
    return "cross" if "访谈" in haystack or "对话" in haystack else "unknown"


def scene_for(category: str, title: str) -> str:
    if "针灸" in title:
        return f"{category}/针灸"
    if "黄帝内经" in title:
        return f"{category}/黄帝内经"
    if "伤寒" in title:
        return f"{category}/伤寒论"
    if "金匮" in title:
        return f"{category}/金匮要略"
    if "临床" in title or "问诊" in title:
        return f"{category}/临床问答"
    if "紫微" in title:
        return f"{category}/紫微斗数"
    if "四柱" in title:
        return f"{category}/四柱命卦"
    if "易经" in title:
        return f"{category}/易经"
    if "阳宅" in title or "风水" in title:
        return f"{category}/阳宅风水"
    if "梁冬" in title or "对话" in title:
        return f"{category}/长谈"
    return category


def build_subtitle_chunks(
    cues: list[Cue],
    max_chars: int = 700,
    max_duration_ms: int = 90_000,
    max_gap_ms: int = 3_000,
) -> list[SubtitleChunk]:
    chunks: list[SubtitleChunk] = []
    current: list[Cue] = []

    def flush() -> None:
        if not current:
            return
        text = "".join(cue.text for cue in current)
        if text:
            chunks.append(
                SubtitleChunk(
                    index=len(chunks) + 1,
                    start_ms=current[0].start_ms,
                    end_ms=current[-1].end_ms,
                    text=text,
                )
            )
        current.clear()

    for cue in cues:
        if not current:
            current.append(cue)
            continue
        projected_text = "".join(item.text for item in current) + cue.text
        projected_duration = cue.end_ms - current[0].start_ms
        gap = cue.start_ms - current[-1].end_ms
        if len(projected_text) > max_chars or projected_duration > max_duration_ms or gap > max_gap_ms:
            flush()
        current.append(cue)
    flush()
    return chunks


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def purge_previous_subtitles(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT id FROM sources
        WHERE source_type = 'subtitle'
           OR id LIKE ?
           OR notes LIKE ?
        """,
        (f"{SOURCE_ID_PREFIX}%", f"%{IMPORT_MARKER}%"),
    ).fetchall()
    source_ids = [str(row["id"]) for row in rows]
    if not source_ids:
        return 0

    placeholders = ",".join("?" for _ in source_ids)
    chunk_rows = conn.execute(f"SELECT id FROM chunks WHERE source_id IN ({placeholders})", source_ids).fetchall()
    chunk_ids = [str(row["id"]) for row in chunk_rows]
    if chunk_ids:
        chunk_placeholders = ",".join("?" for _ in chunk_ids)
        conn.execute(f"DELETE FROM chunk_embeddings WHERE chunk_id IN ({chunk_placeholders})", chunk_ids)
        conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({chunk_placeholders})", chunk_ids)
        conn.execute(f"DELETE FROM chunks WHERE id IN ({chunk_placeholders})", chunk_ids)
    conn.execute(f"DELETE FROM sources WHERE id IN ({placeholders})", source_ids)
    return len(source_ids)


def insert_subtitle_source(conn: sqlite3.Connection, source: dict[str, str]) -> None:
    conn.execute(
        """
        INSERT INTO sources (
          id, title, domain, course, chapter, source_type, rights_status, path,
          page, source_url, source_page, raw_file, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,
          domain=excluded.domain,
          course=excluded.course,
          chapter=excluded.chapter,
          source_type=excluded.source_type,
          rights_status=excluded.rights_status,
          path=excluded.path,
          page=excluded.page,
          source_url=excluded.source_url,
          source_page=excluded.source_page,
          raw_file=excluded.raw_file,
          notes=excluded.notes
        """,
        (
            source["id"],
            source["title"],
            source["domain"],
            source["course"],
            source["chapter"],
            "subtitle",
            "unknown",
            source["path"],
            "",
            "",
            "",
            source["raw_file"],
            source["notes"],
        ),
    )


def insert_subtitle_chunk(conn: sqlite3.Connection, source: dict[str, str], chunk: SubtitleChunk) -> None:
    chunk_id = stable_id(source["id"], str(chunk.index))
    timestamp = f"{format_time(chunk.start_ms)} --> {format_time(chunk.end_ms)}"
    topics = [source["course"], source["chapter"], source["scene"], "字幕逐字稿"]
    entities = ["倪海厦"]
    aliases = [source["title"]]
    context_prefix = (
        f"{source['domain']} > {source['course']} > {source['chapter']} > {source['title']}"
        f" ; scene: {source['scene']} ; time: {timestamp}"
        " ; rights: private_local_subtitle"
    )
    contextual_text = f"{context_prefix}\n\n{chunk.text}"
    topics_json = json_dumps([item for item in topics if item])
    entities_json = json_dumps(entities)
    aliases_json = json_dumps(aliases)
    conn.execute(
        """
        INSERT OR REPLACE INTO chunks (
          id, source_id, title, domain, course, chapter, timestamp, page, source_url,
          original_text, context_prefix, contextual_text, topics_json, entities_json, aliases_json, rights_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            source["id"],
            source["title"],
            source["domain"],
            source["course"],
            source["chapter"],
            timestamp,
            format_time(chunk.start_ms),
            "",
            chunk.text,
            context_prefix,
            contextual_text,
            topics_json,
            entities_json,
            aliases_json,
            "unknown",
        ),
    )
    conn.execute(
        """
        INSERT INTO chunks_fts (chunk_id, domain, course, chapter, topics, entities, aliases, contextual_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            source["domain"],
            source["course"],
            source["chapter"],
            " ".join([item for item in topics if item]),
            " ".join(entities),
            " ".join(aliases),
            fts_payload(context_prefix, chunk.text, source["scene"], source["title"]),
        ),
    )


def import_subtitle_directory(
    srt_root: str | Path,
    db_path: str | Path,
    reset_subtitles: bool = True,
    project_root: str | Path | None = None,
    max_chars: int = 700,
) -> dict[str, object]:
    root = Path(srt_root)
    base = Path(project_root) if project_root is not None else Path.cwd()
    conn = connect(db_path)
    removed_sources = purge_previous_subtitles(conn) if reset_subtitles else 0
    source_count = 0
    chunk_count = 0
    warnings: list[str] = []

    for srt_path in sorted(root.rglob("*.srt")):
        rel = relative_path(srt_path, base)
        try:
            cues = read_srt(srt_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            warnings.append(f"{rel}: skipped ({type(exc).__name__}: {exc})")
            continue
        if not cues:
            warnings.append(f"{rel}: no subtitle cues, skipped")
            continue

        category = srt_path.parent.name if srt_path.parent != root else ""
        title = srt_path.stem
        domain = infer_domain(category, title)
        scene = scene_for(category or "字幕", title)
        source = {
            "id": f"{SOURCE_ID_PREFIX}{stable_id(rel)}",
            "title": title,
            "domain": domain,
            "course": category or "字幕",
            "chapter": scene.split("/", 1)[-1],
            "scene": scene,
            "path": rel,
            "raw_file": rel,
            "notes": f"{IMPORT_MARKER}; local-only full SRT transcript for retrieval, not style prompt injection.",
        }
        chunks = build_subtitle_chunks(cues, max_chars=max_chars)
        if not chunks:
            warnings.append(f"{rel}: no chunks, skipped")
            continue

        insert_subtitle_source(conn, source)
        for chunk in chunks:
            insert_subtitle_chunk(conn, source, chunk)
        source_count += 1
        chunk_count += len(chunks)

    conn.commit()
    conn.close()
    return {
        "sources": source_count,
        "chunks": chunk_count,
        "removed_previous_sources": removed_sources,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import private SRT subtitles into the Ni Haixia knowledge index.")
    parser.add_argument("--srt-root", default="materials/bilibili-style-sources/private/jianying-subtitles/split")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--no-reset-subtitles", action="store_true")
    parser.add_argument("--max-chars", type=int, default=700)
    args = parser.parse_args()
    stats = import_subtitle_directory(
        args.srt_root,
        args.db,
        reset_subtitles=not args.no_reset_subtitles,
        max_chars=args.max_chars,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
