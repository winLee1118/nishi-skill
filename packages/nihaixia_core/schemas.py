from __future__ import annotations

from dataclasses import dataclass, field


Domain = str


@dataclass(slots=True)
class SourceDoc:
    id: str
    title: str
    domain: Domain
    course: str = ""
    chapter: str = ""
    source_type: str = "markdown"
    rights_status: str = "unknown"
    path: str = ""
    page: str = ""
    source_url: str = ""
    source_page: str = ""
    raw_file: str = ""
    notes: str = ""
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    timestamp: str = ""
    body: str = ""


@dataclass(slots=True)
class SearchResult:
    chunk_id: str
    source_id: str
    title: str
    domain: Domain
    course: str
    chapter: str
    timestamp: str
    page: str
    source_url: str
    snippet: str
    score: float
    topics: list[str]
    entities: list[str]
    rights_status: str
    match_source: str = "fts"
