#!/usr/bin/env python3
"""Export text/subtitle tracks from JianyingPro template.json to SRT."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TEXT_MATERIAL_KEYS = (
    "texts",
    "text_templates",
    "captions",
    "subtitles",
    "lyrics",
)


def normalize_text(value: str) -> str:
    value = value.replace("\\n", "\n")
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def decode_json_string(value: str) -> Any:
    text = value.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def collect_strings(obj: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(obj, str):
        if obj.strip():
            strings.append(obj)
        decoded = decode_json_string(obj)
        if decoded is not None:
            strings.extend(collect_strings(decoded))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in {
                "text",
                "content",
                "caption",
                "subtitle",
                "words",
                "sentence",
                "value",
            }:
                strings.extend(collect_strings(value))
            elif isinstance(value, (dict, list)):
                strings.extend(collect_strings(value))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(collect_strings(item))
    return strings


def best_text_from_material(material: dict[str, Any]) -> str:
    preferred_fields = (
        "content",
        "text",
        "caption",
        "subtitle",
        "words",
        "sentence",
        "value",
    )
    candidates: list[str] = []
    for field in preferred_fields:
        if field in material:
            candidates.extend(collect_strings(material[field]))
    if not candidates:
        candidates.extend(collect_strings(material))

    cleaned: list[str] = []
    for candidate in candidates:
        text = normalize_text(candidate)
        if not text:
            continue
        if text.startswith("{") or text.startswith("["):
            continue
        if len(text) > 500:
            continue
        cleaned.append(text)

    if not cleaned:
        return ""
    return max(cleaned, key=lambda item: (len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", item)), len(item)))


def load_template(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def build_material_text_map(template: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    materials = template.get("materials") or {}
    if not isinstance(materials, dict):
        return result

    for key in TEXT_MATERIAL_KEYS:
        entries = materials.get(key) or []
        if not isinstance(entries, list):
            continue
        for material in entries:
            if not isinstance(material, dict):
                continue
            material_id = str(material.get("id") or material.get("material_id") or "")
            if not material_id:
                continue
            text = best_text_from_material(material)
            if text:
                result[material_id] = text
    return result


def micros_to_srt_time(value: int | float) -> str:
    millis = int(round(float(value) / 1000.0))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def segment_time(segment: dict[str, Any]) -> tuple[int, int]:
    timerange = segment.get("target_timerange") or segment.get("render_timerange") or {}
    start = int(timerange.get("start") or 0)
    duration = int(timerange.get("duration") or 0)
    if duration <= 0:
        source_range = segment.get("source_timerange") or {}
        duration = int(source_range.get("duration") or 0)
    return start, max(duration, 0)


def extract_subtitles(template: dict[str, Any]) -> list[tuple[int, int, str]]:
    material_text = build_material_text_map(template)
    subtitles: list[tuple[int, int, str]] = []

    for track in template.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        track_type = str(track.get("type") or "").lower()
        if track_type not in {"text", "subtitle", "caption", "lyrics"}:
            continue
        for segment in track.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            material_id = str(segment.get("material_id") or segment.get("id") or "")
            text = material_text.get(material_id, "")
            if not text:
                refs = segment.get("extra_material_refs") or []
                if isinstance(refs, list):
                    for ref in refs:
                        text = material_text.get(str(ref), "")
                        if text:
                            break
            if not text:
                text = best_text_from_material(segment)
            if not text:
                continue
            start, duration = segment_time(segment)
            subtitles.append((start, start + duration, text))

    subtitles.sort(key=lambda item: (item[0], item[1], item[2]))
    return subtitles


def write_srt(subtitles: list[tuple[int, int, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, (start, end, text) in enumerate(subtitles, 1):
        if end <= start:
            end = start + 1_000_000
        lines.extend(
            [
                str(index),
                f"{micros_to_srt_time(start)} --> {micros_to_srt_time(end)}",
                text,
                "",
            ]
        )
    output.write_text("\n".join(lines), encoding="utf-8")


def find_template_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("template.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export JianyingPro timeline text tracks to .srt.")
    parser.add_argument("input", type=Path, help="template.json file or a JianyingPro drafts directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("materials/bilibili-style-sources/private/jianying-subtitles"),
        help="Directory for exported .srt files.",
    )
    parser.add_argument("--list-only", action="store_true", help="Only list candidate template files.")
    args = parser.parse_args()

    templates = find_template_files(args.input)
    if args.list_only:
        for template in templates:
            print(template)
        return 0

    exported = 0
    for template_path in templates:
        try:
            template = load_template(template_path)
        except Exception as exc:
            print(f"[skip] {template_path}: {exc}")
            continue

        subtitles = extract_subtitles(template)
        if not subtitles:
            print(f"[empty] {template_path}")
            continue

        draft_name = template_path.parent.name
        if draft_name.lower() == "timelines":
            draft_name = template_path.parent.parent.name
        output = args.output_dir / f"{draft_name}.srt"
        write_srt(subtitles, output)
        print(f"[ok] {template_path} -> {output} ({len(subtitles)} items)")
        exported += 1

    return 0 if exported else 2


if __name__ == "__main__":
    raise SystemExit(main())
