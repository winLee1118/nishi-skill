from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import connect, reset_index
from .schemas import SourceDoc
from .text import ensure_list, fts_payload, iter_markdown_files, json_dumps, parse_frontmatter, stable_id


REQUIRED_FIELDS = ("id", "title", "domain", "course", "chapter", "rights_status")
VALID_RIGHTS_STATUS = {"authorized", "public", "unknown"}
VALID_DOMAINS = {"renji", "tianji", "diji", "cross", "unknown"}


def load_markdown(path: Path, vault_root: Path) -> SourceDoc:
    raw = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw)
    rel_path = path.relative_to(vault_root).as_posix()
    source_id = str(metadata.get("id") or stable_id(rel_path))
    title = str(metadata.get("title") or path.stem)
    return SourceDoc(
        id=source_id,
        title=title,
        domain=str(metadata.get("domain") or infer_domain_from_path(rel_path)),
        course=str(metadata.get("course") or ""),
        chapter=str(metadata.get("chapter") or ""),
        source_type=str(metadata.get("source_type") or "markdown"),
        rights_status=str(metadata.get("rights_status") or "unknown"),
        path=rel_path,
        page=str(metadata.get("page") or ""),
        source_url=str(metadata.get("source_url") or ""),
        source_page=str(metadata.get("source_page") or ""),
        raw_file=str(metadata.get("raw_file") or ""),
        notes=str(metadata.get("notes") or ""),
        topics=ensure_list(metadata.get("topics")),
        entities=ensure_list(metadata.get("entities")),
        aliases=ensure_list(metadata.get("aliases")),
        timestamp=str(metadata.get("timestamp") or ""),
        body=body,
    )


def validate_doc(doc: SourceDoc, metadata: dict, path: Path) -> list[str]:
    warnings: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in metadata or str(metadata.get(field) or "").strip() == "":
            warnings.append(f"{path.as_posix()}: missing frontmatter field '{field}'")
    if doc.domain not in VALID_DOMAINS:
        warnings.append(f"{path.as_posix()}: invalid domain '{doc.domain}'")
    if doc.rights_status not in VALID_RIGHTS_STATUS:
        warnings.append(f"{path.as_posix()}: invalid rights_status '{doc.rights_status}'")
    if doc.rights_status == "unknown":
        warnings.append(f"{path.as_posix()}: rights_status is unknown; keep local-only until reviewed")
    return warnings


def infer_domain_from_path(path: str) -> str:
    lowered = path.lower()
    if "renji" in lowered or "人纪" in path:
        return "renji"
    if "tianji" in lowered or "天纪" in path:
        return "tianji"
    if "diji" in lowered or "地纪" in path:
        return "diji"
    return "unknown"


def chunk_text(text: str, max_chars: int = 900) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or ([text.strip()] if text.strip() else [])


def context_prefix(doc: SourceDoc) -> str:
    pieces = [doc.domain, doc.course, doc.chapter, doc.title]
    prefix = " > ".join(piece for piece in pieces if piece)
    if doc.topics:
        prefix += f" ; topics: {', '.join(doc.topics)}"
    if doc.entities:
        prefix += f" ; entities: {', '.join(doc.entities)}"
    if doc.aliases:
        prefix += f" ; aliases: {', '.join(doc.aliases)}"
    if doc.page:
        prefix += f" ; page: {doc.page}"
    return prefix


def upsert_source(conn: sqlite3.Connection, doc: SourceDoc) -> None:
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
            doc.id,
            doc.title,
            doc.domain,
            doc.course,
            doc.chapter,
            doc.source_type,
            doc.rights_status,
            doc.path,
            doc.page,
            doc.source_url,
            doc.source_page,
            doc.raw_file,
            doc.notes,
        ),
    )


def insert_chunks(conn: sqlite3.Connection, doc: SourceDoc) -> int:
    prefix = context_prefix(doc)
    count = 0
    for index, text in enumerate(chunk_text(doc.body), start=1):
        chunk_id = stable_id(doc.id, str(index))
        contextual_text = f"{prefix}\n\n{text}".strip()
        topics_json = json_dumps(doc.topics)
        entities_json = json_dumps(doc.entities)
        aliases_json = json_dumps(doc.aliases)
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
                doc.id,
                doc.title,
                doc.domain,
                doc.course,
                doc.chapter,
                doc.timestamp,
                doc.page,
                doc.source_url,
                text,
                prefix,
                contextual_text,
                topics_json,
                entities_json,
                aliases_json,
                doc.rights_status,
            ),
        )
        conn.execute(
            """
            INSERT INTO chunks_fts (chunk_id, domain, course, chapter, topics, entities, aliases, contextual_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                doc.domain,
                doc.course,
                doc.chapter,
                " ".join(doc.topics),
                " ".join(doc.entities),
                " ".join(doc.aliases),
                fts_payload(prefix, text, " ".join(doc.topics), " ".join(doc.entities), " ".join(doc.aliases)),
            ),
        )
        count += 1
    return count


def build_index(vault: str | Path, db_path: str | Path, reset: bool = True) -> dict[str, object]:
    vault_root = Path(vault)
    conn = connect(db_path)
    if reset:
        reset_index(conn)

    source_count = 0
    chunk_count = 0
    warnings: list[str] = []
    for path in iter_markdown_files(vault_root):
        raw = path.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(raw)
        doc = load_markdown(path, vault_root)
        warnings.extend(validate_doc(doc, metadata, path))
        if not doc.body:
            warnings.append(f"{path.as_posix()}: empty body, skipped")
            continue
        upsert_source(conn, doc)
        chunk_count += insert_chunks(conn, doc)
        source_count += 1
    conn.commit()
    conn.close()
    return {"sources": source_count, "chunks": chunk_count, "warnings": warnings}
