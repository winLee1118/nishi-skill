from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .eval_runner import read_jsonl, result_haystack, text_avoids_all, text_contains_all
from .retrieval import search_with_info


def run_one_case(case: dict[str, Any], db: str) -> dict[str, Any]:
    question = str(case["question"])
    domain = str(case.get("domain") or "auto")
    top_k = int(case.get("top_k") or 5)
    must_find = [str(item) for item in case.get("must_find", [])]
    must_avoid = [str(item) for item in case.get("must_avoid", [])]

    fts_results, fts_info = search_with_info(question, db, domain=domain, top_k=top_k, mode="fts")
    hybrid_results, hybrid_info = search_with_info(question, db, domain=domain, top_k=top_k, mode="hybrid")

    fts_haystack = result_haystack(fts_results)
    hybrid_haystack = result_haystack(hybrid_results)
    fts_find_ok, fts_missing = text_contains_all(fts_haystack, must_find)
    hybrid_find_ok, hybrid_missing = text_contains_all(hybrid_haystack, must_find)
    fts_avoid_ok, fts_forbidden = text_avoids_all(fts_haystack, must_avoid)
    hybrid_avoid_ok, hybrid_forbidden = text_avoids_all(hybrid_haystack, must_avoid)

    fts_passed = bool(fts_results) and fts_find_ok and fts_avoid_ok
    hybrid_passed = bool(hybrid_results) and hybrid_find_ok and hybrid_avoid_ok
    if hybrid_info.get("fallback"):
        outcome = "fallback"
    elif hybrid_passed and not fts_passed:
        outcome = "improved"
    elif hybrid_passed == fts_passed:
        outcome = "tie"
    else:
        outcome = "regressed"

    return {
        "id": case.get("id"),
        "question": question,
        "domain": domain,
        "top_k": top_k,
        "outcome": outcome,
        "fts": {
            "passed": fts_passed,
            "retrieval": fts_info,
            "missing": fts_missing,
            "forbidden_found": fts_forbidden,
            "top": asdict(fts_results[0]) if fts_results else None,
        },
        "hybrid": {
            "passed": hybrid_passed,
            "retrieval": hybrid_info,
            "missing": hybrid_missing,
            "forbidden_found": hybrid_forbidden,
            "top": asdict(hybrid_results[0]) if hybrid_results else None,
        },
    }


def run_hybrid_eval(db: str, cases_path: str | Path) -> dict[str, Any]:
    cases = read_jsonl(Path(cases_path))
    results = [run_one_case(case, db) for case in cases]
    outcomes = {name: 0 for name in ("improved", "tie", "regressed", "fallback")}
    for result in results:
        outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1
    return {
        "total": len(results),
        "outcomes": outcomes,
        "passed": outcomes.get("regressed", 0) == 0,
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare fts and optional hybrid retrieval.")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--cases", default="evals/hybrid_cases.jsonl")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()
    report = run_hybrid_eval(args.db, args.cases)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_regression and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
