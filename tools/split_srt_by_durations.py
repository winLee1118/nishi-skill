#!/usr/bin/env python3
"""Split a combined SRT by ordered source media durations."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})"
)


@dataclass
class Cue:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class Segment:
    path: Path
    title: str
    category: str
    start_ms: int
    end_ms: int


def parse_time(value: str) -> int:
    match = TIME_RE.search(value)
    if not match:
        raise ValueError(f"Invalid SRT time: {value}")
    h = int(match.group("h"))
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = int(match.group("ms"))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def format_time(value_ms: int) -> str:
    value_ms = max(0, int(round(value_ms)))
    h, rem = divmod(value_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def read_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    cues: list[Cue] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        time_line_index = 1 if "-->" in lines[1] else 0
        if "-->" not in lines[time_line_index]:
            continue
        start_text, end_text = lines[time_line_index].split("-->", 1)
        text = "\n".join(lines[time_line_index + 1 :]).strip()
        if not text:
            continue
        cues.append(Cue(parse_time(start_text), parse_time(end_text), text))
    return cues


def write_srt(path: Path, cues: list[Cue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, cue in enumerate(cues, 1):
        lines.extend(
            [
                str(index),
                f"{format_time(cue.start_ms)} --> {format_time(cue.end_ms)}",
                cue.text,
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def media_duration_ms(path: Path) -> int:
    command = [
        "ffprobe.exe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(completed.stdout)
    return int(round(float(data["format"]["duration"]) * 1000))


def slugify(name: str) -> str:
    name = Path(name).stem
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "untitled"


def load_order(order_file: Path) -> list[Path]:
    paths: list[Path] = []
    for line in order_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(Path(line))
    return paths


def build_segments(paths: list[Path], gap_ms: int) -> list[Segment]:
    current = 0
    segments: list[Segment] = []
    for path in paths:
        duration = media_duration_ms(path)
        segments.append(
            Segment(
                path=path,
                title=path.stem,
                category=path.parent.name,
                start_ms=current,
                end_ms=current + duration,
            )
        )
        current += duration + gap_ms
    return segments


def split_cues(cues: list[Cue], segments: list[Segment]) -> dict[str, list[Cue]]:
    result: dict[str, list[Cue]] = {}
    for segment in segments:
        key = f"{segment.category}/{slugify(segment.title)}.srt"
        scoped: list[Cue] = []
        for cue in cues:
            if cue.end_ms <= segment.start_ms or cue.start_ms >= segment.end_ms:
                continue
            start = max(cue.start_ms, segment.start_ms) - segment.start_ms
            end = min(cue.end_ms, segment.end_ms) - segment.start_ms
            scoped.append(Cue(start, end, cue.text))
        result[key] = scoped
    return result


def write_manifest(path: Path, segments: list[Segment], split: dict[str, list[Cue]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["category", "title", "source_path", "start", "end", "duration_ms", "cue_count", "output"])
        for segment in segments:
            output = f"{segment.category}/{slugify(segment.title)}.srt"
            writer.writerow(
                [
                    segment.category,
                    segment.title,
                    str(segment.path),
                    format_time(segment.start_ms),
                    format_time(segment.end_ms),
                    segment.end_ms - segment.start_ms,
                    len(split.get(output, [])),
                    output,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a combined SRT by ordered media durations.")
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--order", required=True, type=Path, help="UTF-8 text file with one media path per line.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gap-ms", type=int, default=0, help="Gap between clips on the timeline.")
    args = parser.parse_args()

    cues = read_srt(args.srt)
    paths = load_order(args.order)
    segments = build_segments(paths, args.gap_ms)
    split = split_cues(cues, segments)

    total_written = 0
    for relative, scoped in split.items():
        output = args.output_dir / relative
        write_srt(output, scoped)
        print(f"[ok] {relative}: {len(scoped)} cues")
        total_written += len(scoped)

    write_manifest(args.output_dir / "manifest.csv", segments, split)
    print(f"[done] {len(cues)} input cues, {total_written} written cues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
