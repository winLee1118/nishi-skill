from __future__ import annotations

import json
from pathlib import Path


def load_relations(graph_dir: str | Path) -> list[dict[str, str]]:
    path = Path(graph_dir) / "relations.jsonl"
    if not path.exists():
        return []
    relations: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        relations.append({key: str(value) for key, value in data.items()})
    return relations


def related_concepts(concept: str, graph_dir: str | Path, depth: int = 1) -> list[dict[str, str]]:
    frontier = {concept}
    seen = {concept}
    matches: list[dict[str, str]] = []
    relations = load_relations(graph_dir)
    for _ in range(max(1, depth)):
        next_frontier: set[str] = set()
        for relation in relations:
            source = relation.get("from") or relation.get("source_entity") or ""
            target = relation.get("to") or relation.get("target_entity") or ""
            if source in frontier or target in frontier:
                matches.append(relation)
                if source and source not in seen:
                    next_frontier.add(source)
                    seen.add(source)
                if target and target not in seen:
                    next_frontier.add(target)
                    seen.add(target)
        frontier = next_frontier
        if not frontier:
            break
    return matches

