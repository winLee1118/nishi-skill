from __future__ import annotations

import argparse
import json

from .calendar import bazi_chart, calendar_report, four_pillars
from .ingest import build_index
from .retrieval import search_with_info
from .embedding import load_embedding_config, sanitize_config_for_report
from .subtitle_ingest import import_subtitle_directory
from .vector_store import build_chunk_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Ni Haixia lightweight RAG CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-index", help="Build the SQLite FTS index.")
    build_parser.add_argument("--vault", default="knowledge/vault")
    build_parser.add_argument("--db", default="data/nihaixia.sqlite")
    build_parser.add_argument("--no-reset", action="store_true")

    subtitles_parser = subparsers.add_parser("import-subtitles", help="Import private SRT subtitles into the knowledge index.")
    subtitles_parser.add_argument("--srt-root", default="materials/bilibili-style-sources/private/jianying-subtitles/split")
    subtitles_parser.add_argument("--db", default="data/nihaixia.sqlite")
    subtitles_parser.add_argument("--no-reset-subtitles", action="store_true")
    subtitles_parser.add_argument("--max-chars", type=int, default=700)

    search_parser = subparsers.add_parser("search", help="Search the SQLite FTS index.")
    search_parser.add_argument("question")
    search_parser.add_argument("--db", default="data/nihaixia.sqlite")
    search_parser.add_argument("--domain", default="auto", choices=["auto", "cross", "renji", "tianji", "diji"])
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--mode", default="auto", choices=["auto", "fts", "hybrid"])

    embeddings_parser = subparsers.add_parser("build-embeddings", help="Build optional chunk embedding cache.")
    embeddings_parser.add_argument("--db", default="data/nihaixia.sqlite")
    embeddings_parser.add_argument("--limit", type=int, default=None)
    embeddings_parser.add_argument("--batch-size", type=int, default=16)

    subparsers.add_parser("embedding-status", help="Show sanitized embedding configuration.")

    calendar_parser = subparsers.add_parser("calendar", help="Convert Gregorian datetime to lunar/Ganzhi parameters.")
    calendar_parser.add_argument("datetime_text")
    calendar_parser.add_argument("--timezone", default="Asia/Shanghai")

    ganzhi_parser = subparsers.add_parser("ganzhi", help="Return year/month/day/hour Ganzhi pillars.")
    ganzhi_parser.add_argument("datetime_text")
    ganzhi_parser.add_argument("--timezone", default="Asia/Shanghai")
    ganzhi_parser.add_argument("--day-boundary", default="23:00")

    bazi_parser = subparsers.add_parser("bazi", help="Return a structured Four Pillars/Bazi chart.")
    bazi_parser.add_argument("datetime_text")
    bazi_parser.add_argument("--timezone", default="Asia/Shanghai")
    bazi_parser.add_argument("--gender", default="unknown")
    bazi_parser.add_argument("--location", default="")
    bazi_parser.add_argument("--true-solar-time", action="store_true")
    bazi_parser.add_argument("--day-boundary", default="23:00")
    bazi_parser.add_argument("--luck-cycle-count", type=int, default=8)
    bazi_parser.add_argument("--annual-start-year", type=int, default=None)
    bazi_parser.add_argument("--annual-years", type=int, default=10)

    args = parser.parse_args()
    if args.command == "build-index":
        stats = build_index(args.vault, args.db, reset=not args.no_reset)
        print(json.dumps(stats, ensure_ascii=False))
    elif args.command == "import-subtitles":
        stats = import_subtitle_directory(
            args.srt_root,
            args.db,
            reset_subtitles=not args.no_reset_subtitles,
            max_chars=args.max_chars,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif args.command == "search":
        print_search_results(args.question, args.db, args.domain, args.top_k, args.mode)
    elif args.command == "build-embeddings":
        stats = build_chunk_embeddings(args.db, limit=args.limit, batch_size=args.batch_size)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif args.command == "embedding-status":
        print(json.dumps(sanitize_config_for_report(load_embedding_config()), ensure_ascii=False, indent=2))
    elif args.command == "calendar":
        print(json.dumps(calendar_report(args.datetime_text, timezone=args.timezone), ensure_ascii=False, indent=2))
    elif args.command == "ganzhi":
        print(json.dumps(four_pillars(args.datetime_text, timezone=args.timezone, day_boundary=args.day_boundary), ensure_ascii=False, indent=2))
    elif args.command == "bazi":
        print(
            json.dumps(
                bazi_chart(
                    args.datetime_text,
                    timezone=args.timezone,
                    gender=args.gender,
                    location=args.location,
                    use_true_solar_time=args.true_solar_time,
                    day_boundary=args.day_boundary,
                    luck_cycle_count=args.luck_cycle_count,
                    annual_start_year=args.annual_start_year,
                    annual_years=args.annual_years,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )


def build_index_main() -> None:
    parser = argparse.ArgumentParser(description="Build the Ni Haixia SQLite FTS index.")
    parser.add_argument("--vault", default="knowledge/vault")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()
    stats = build_index(args.vault, args.db, reset=not args.no_reset)
    print(json.dumps(stats, ensure_ascii=False))


def import_subtitles_main() -> None:
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


def search_main() -> None:
    parser = argparse.ArgumentParser(description="Search the Ni Haixia SQLite FTS index.")
    parser.add_argument("question")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--domain", default="auto", choices=["auto", "cross", "renji", "tianji", "diji"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", default="auto", choices=["auto", "fts", "hybrid"])
    args = parser.parse_args()
    print_search_results(args.question, args.db, args.domain, args.top_k, args.mode)


def build_embeddings_main() -> None:
    parser = argparse.ArgumentParser(description="Build optional Ni Haixia chunk embedding cache.")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    stats = build_chunk_embeddings(args.db, limit=args.limit, batch_size=args.batch_size)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def embedding_status_main() -> None:
    print(json.dumps(sanitize_config_for_report(load_embedding_config()), ensure_ascii=False, indent=2))


def calendar_main() -> None:
    parser = argparse.ArgumentParser(description="Convert Gregorian datetime to lunar/Ganzhi parameters.")
    parser.add_argument("datetime_text")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    args = parser.parse_args()
    print(json.dumps(calendar_report(args.datetime_text, timezone=args.timezone), ensure_ascii=False, indent=2))


def ganzhi_main() -> None:
    parser = argparse.ArgumentParser(description="Return year/month/day/hour Ganzhi pillars.")
    parser.add_argument("datetime_text")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--day-boundary", default="23:00")
    args = parser.parse_args()
    print(json.dumps(four_pillars(args.datetime_text, timezone=args.timezone, day_boundary=args.day_boundary), ensure_ascii=False, indent=2))


def bazi_main() -> None:
    parser = argparse.ArgumentParser(description="Return a structured Four Pillars/Bazi chart.")
    parser.add_argument("datetime_text")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--gender", default="unknown")
    parser.add_argument("--location", default="")
    parser.add_argument("--true-solar-time", action="store_true")
    parser.add_argument("--day-boundary", default="23:00")
    parser.add_argument("--luck-cycle-count", type=int, default=8)
    parser.add_argument("--annual-start-year", type=int, default=None)
    parser.add_argument("--annual-years", type=int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            bazi_chart(
                args.datetime_text,
                timezone=args.timezone,
                gender=args.gender,
                location=args.location,
                use_true_solar_time=args.true_solar_time,
                day_boundary=args.day_boundary,
                luck_cycle_count=args.luck_cycle_count,
                annual_start_year=args.annual_start_year,
                annual_years=args.annual_years,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def print_search_results(question: str, db: str, domain: str, top_k: int, mode: str = "auto") -> None:
    results, info = search_with_info(question, db, domain=domain, top_k=top_k, mode=mode)
    payload = {
        "retrieval": info,
        "results": [
            {
                "chunk_id": item.chunk_id,
                "source_id": item.source_id,
                "title": item.title,
                "domain": item.domain,
                "course": item.course,
                "chapter": item.chapter,
                "timestamp": item.timestamp,
                "page": item.page,
                "source_url": item.source_url,
                "score": round(item.score, 4),
                "match_source": item.match_source,
                "snippet": item.snippet,
                "topics": item.topics,
                "entities": item.entities,
                "rights_status": item.rights_status,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
