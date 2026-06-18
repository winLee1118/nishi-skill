from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .persona import persona_guidance
from .retrieval import search
from .safety import safety_notes
from .text import classify_domain

# Chat-channel output must stay plain conversational text. These patterns flag
# markdown formatting that the chat contract forbids.
FORMAT_VIOLATION_PATTERNS = {
    "markdown_heading": re.compile(r"(?m)^\s{0,3}#{1,6}\s"),
    "markdown_bold": re.compile(r"\*\*[^*\n]+\*\*"),
    "numbered_list": re.compile(r"(?m)^\s*\d{1,2}[\.、)）]\s"),
    "bullet_list": re.compile(r"(?m)^\s*[-*•]\s"),
    "table_row": re.compile(r"(?m)^\s*\|.*\|\s*$"),
}


def format_violations(text: str) -> list[str]:
    return [name for name, pattern in FORMAT_VIOLATION_PATTERNS.items() if pattern.search(text)]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not path.exists():
        return cases
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
    return cases


def text_contains_all(text: str, terms: list[str]) -> tuple[bool, list[str]]:
    missing = [term for term in terms if term not in text]
    return not missing, missing


def text_avoids_all(text: str, terms: list[str]) -> tuple[bool, list[str]]:
    found = [term for term in terms if term in text]
    return not found, found


def result_haystack(results: list[Any]) -> str:
    parts: list[str] = []
    for result in results:
        if hasattr(result, "__dataclass_fields__"):
            data = asdict(result)
        else:
            data = dict(result)
        for key in (
            "source_id",
            "title",
            "domain",
            "course",
            "chapter",
            "timestamp",
            "page",
            "source_url",
            "snippet",
            "rights_status",
        ):
            parts.append(str(data.get(key, "")))
        parts.extend(str(item) for item in data.get("topics", []))
        parts.extend(str(item) for item in data.get("entities", []))
    return "\n".join(parts)


def run_retrieval_case(case: dict[str, Any], db: str) -> dict[str, Any]:
    top_k = int(case.get("top_k") or 3)
    results = search(case["question"], db, domain=str(case.get("domain") or "auto"), top_k=top_k)
    haystack = result_haystack(results)
    ok_find, missing = text_contains_all(haystack, [str(item) for item in case.get("must_find", [])])
    ok_avoid, found = text_avoids_all(haystack, [str(item) for item in case.get("must_avoid", [])])
    passed = bool(results) and ok_find and ok_avoid
    return {
        "id": case.get("id"),
        "type": "retrieval",
        "passed": passed,
        "details": {
            "result_count": len(results),
            "missing": missing,
            "forbidden_found": found,
            "top_source_id": results[0].source_id if results else None,
        },
    }


def run_style_case(case: dict[str, Any], db: str) -> dict[str, Any]:
    domain = str(case.get("domain") or classify_domain(case["question"]))
    top_k = int(case.get("top_k") or 3)
    results = search(case["question"], db, domain=domain, top_k=top_k)
    persona = persona_guidance(domain, str(case.get("style_intensity") or "medium"))
    safety = safety_notes(case["question"], domain)
    include_haystack = "\n".join(
        [
            result_haystack(results),
            str(persona.get("identity", "")),
            str(persona.get("style_prompt", "")),
            json.dumps(persona.get("style_profile", {}), ensure_ascii=False),
            json.dumps(persona.get("boundary_policy", {}), ensure_ascii=False),
            "\n".join(str(item) for item in persona.get("instructions", [])),
            "\n".join(str(item) for item in persona.get("avoid", [])),
            "\n".join(safety),
        ]
    )
    # Forbidden terms are allowed inside guardrail metadata such as "Do not say X".
    # Check them only against positive style instructions and retrieved visible evidence.
    avoid_haystack = "\n".join(
        [
            str(persona.get("identity", "")),
            "\n".join(str(item) for item in persona.get("instructions", [])),
        ]
    )
    ok_find, missing = text_contains_all(include_haystack, [str(item) for item in case.get("must_include", [])])
    ok_avoid, found = text_avoids_all(avoid_haystack, [str(item) for item in case.get("must_avoid", [])])
    return {
        "id": case.get("id"),
        "type": "style",
        "passed": ok_find and ok_avoid,
        "details": {
            "domain": domain,
            "style_intensity": persona.get("style_intensity"),
            "missing": missing,
            "forbidden_found": found,
        },
    }


def run_safety_case(case: dict[str, Any]) -> dict[str, Any]:
    domain = str(case.get("domain") or classify_domain(case["question"]))
    notes = safety_notes(case["question"], domain)
    haystack = "\n".join(notes)
    ok_find, missing = text_contains_all(haystack, [str(item) for item in case.get("must_include", [])])
    ok_avoid, found = text_avoids_all(haystack, [str(item) for item in case.get("must_avoid", [])])
    return {
        "id": case.get("id"),
        "type": "safety",
        "passed": bool(notes) and ok_find and ok_avoid,
        "details": {
            "domain": domain,
            "missing": missing,
            "forbidden_found": found,
            "safety_notes": notes,
        },
    }


def run_format_case(case: dict[str, Any], db: str) -> dict[str, Any]:
    # Imported lazily: the MCP layer depends on this core package, not the other
    # way around, so this stays a soft dependency for eval runs only.
    from nihaixia_mcp.server import answer_with_citations

    result = answer_with_citations(
        case["question"],
        domain=str(case.get("domain") or "auto"),
        top_k=int(case.get("top_k") or 5),
        style_intensity=str(case.get("style_intensity") or "medium"),
        mode=str(case.get("mode") or "auto"),
        output_format="chat",
    )
    answer = str(result.get("answer") or "")
    style_prompt = str(result.get("style_prompt") or "")
    violations = format_violations(answer)
    has_format_rule = "纯对话文本" in style_prompt
    ok_avoid, found = text_avoids_all(answer, [str(item) for item in case.get("must_avoid", [])])
    return {
        "id": case.get("id"),
        "type": "format",
        "passed": not violations and has_format_rule and ok_avoid,
        "details": {
            "domain": result.get("domain"),
            "violations": violations,
            "style_prompt_has_format_rule": has_format_rule,
            "forbidden_found": found,
        },
    }


def run_eval(db: str, eval_dir: str | Path) -> dict[str, Any]:
    root = Path(eval_dir)
    case_results: list[dict[str, Any]] = []

    for path_name in ("questions.jsonl", "retrieval_cases.jsonl"):
        for case in read_jsonl(root / path_name):
            case_results.append(run_retrieval_case(case, db))

    for case in read_jsonl(root / "style_cases.jsonl"):
        case_results.append(run_style_case(case, db))

    for case in read_jsonl(root / "safety_cases.jsonl"):
        case_results.append(run_safety_case(case))

    for case in read_jsonl(root / "format_cases.jsonl"):
        case_results.append(run_format_case(case, db))

    failed = [case for case in case_results if not case["passed"]]
    return {
        "total": len(case_results),
        "passed": len(case_results) - len(failed),
        "failed": len(failed),
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Ni Haixia lightweight RAG evaluations.")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--eval-dir", default="evals")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    report = run_eval(args.db, args.eval_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_error and report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
