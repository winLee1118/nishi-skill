#!/usr/bin/env python3
"""Build short persona-style samples from split SRT files."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


TARGETS = {"人纪": 80, "天纪": 60, "地纪": 30, "访谈": 50}
MIN_CHARS = 20
MAX_CHARS = 80

NOISE_ONLY = re.compile(r"^[啊哦嗯呃诶唉好对吧吗呢呀了的嘛\s,.，。！？!?、]+$")
TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


@dataclass
class Cue:
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
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", "", value)
    value = value.replace("（", "(").replace("）", ")")
    return value.strip()


def read_srt(path: Path) -> list[Cue]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for block in [item.strip() for item in text.split("\n\n") if item.strip()]:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        time_index = 1 if "-->" in lines[1] else 0
        if "-->" not in lines[time_index]:
            continue
        start_text, end_text = lines[time_index].split("-->", 1)
        cue_text = clean_text("".join(lines[time_index + 1 :]))
        if not cue_text or NOISE_ONLY.match(cue_text):
            continue
        cues.append(Cue(parse_time(start_text), parse_time(end_text), cue_text))
    return cues


def category_from_path(path: Path) -> str:
    parent = path.parent.name
    return parent if parent in TARGETS else "未分类"


def scene_from_path(path: Path) -> str:
    stem = path.stem
    if "针灸" in stem:
        return "人纪/针灸"
    if "黄帝内经" in stem:
        return "人纪/黄帝内经"
    if "伤寒" in stem:
        return "人纪/伤寒论"
    if "金匮" in stem:
        return "人纪/金匮要略"
    if "临床" in stem or "问诊" in stem:
        return "人纪/临床问答"
    if "紫微" in stem:
        return "天纪/紫微斗数"
    if "四柱" in stem:
        return "天纪/四柱命卦"
    if "易经" in stem:
        return "天纪/易经"
    if "天纪" in stem:
        return "天纪/总论"
    if "阳宅" in stem or "风水" in stem:
        return "地纪/阳宅风水"
    if "梁冬" in stem or "对话" in stem:
        return "访谈/长谈"
    return category_from_path(path)


FEATURE_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("problem_first", "问题式推进", ("为什么", "怎么", "怎么办", "是不是", "对不对", "有没有", "什么叫")),
    ("direct_judgment", "直接判断", ("就是", "一定", "你就", "不要", "不能", "不是")),
    ("contrastive_boundary", "正反对比", ("不是", "而是", "但是", "如果", "不能", "不要", "一定要")),
    ("operation_then_reason", "先操作后解释", ("先", "再", "然后", "这个时候", "一看", "我们看")),
    ("example_density", "例子落地", ("比如", "家里", "病人", "小孩", "太太", "先生", "房子", "厨房", "药", "针")),
    ("symbolic_image", "象义解释", ("卦", "象", "乾", "坤", "兑", "紫微", "命", "星", "宫", "阳宅")),
    ("classical_frame", "经典框架", ("经方", "伤寒", "金匮", "黄帝内经", "阴阳", "表里", "寒热", "虚实")),
    ("light_humor", "课堂轻松感", ("很好玩", "开玩笑", "好玩", "你看", "奇怪", "笨")),
]


def features_for(text: str, scene: str) -> list[str]:
    features: list[str] = []
    for feature_id, _label, needles in FEATURE_RULES:
        if any(needle in text or needle in scene for needle in needles):
            features.append(feature_id)
    if not features:
        features.append("plain_teaching")
    return features[:4]


def sample_type_for(features: list[str]) -> str:
    if "problem_first" in features:
        return "questioning"
    if "symbolic_image" in features:
        return "symbolic_reasoning"
    if "classical_frame" in features:
        return "classical_teaching"
    if "example_density" in features:
        return "example"
    if "contrastive_boundary" in features:
        return "boundary"
    return "style"


def build_windows(cues: list[Cue]) -> list[tuple[int, int, str]]:
    windows: list[tuple[int, int, str]] = []
    for index in range(len(cues)):
        text = ""
        start = cues[index].start_ms
        end = cues[index].end_ms
        for offset in range(4):
            if index + offset >= len(cues):
                break
            if offset and cues[index + offset].start_ms - end > 2500:
                break
            text += cues[index + offset].text
            end = cues[index + offset].end_ms
            length = len(text)
            if MIN_CHARS <= length <= MAX_CHARS:
                windows.append((start, end, text))
                break
            if length > MAX_CHARS:
                break
    return windows


def score_sample(text: str, features: list[str], picked_texts: set[str]) -> int:
    if text in picked_texts:
        return -999
    score = len(features) * 12
    score += min(len(text), MAX_CHARS)
    if any(feature in features for feature in ("problem_first", "operation_then_reason", "contrastive_boundary")):
        score += 20
    if "plain_teaching" in features:
        score -= 12
    if len(text) < 24:
        score -= 8
    if re.search(r"[A-Za-z0-9]{8,}|https?://", text):
        score -= 50
    return score


def extract_samples(srt_root: Path) -> list[dict[str, object]]:
    by_category: dict[str, list[dict[str, object]]] = {key: [] for key in TARGETS}
    for srt_path in sorted(srt_root.rglob("*.srt")):
        category = category_from_path(srt_path)
        if category not in TARGETS:
            continue
        scene = scene_from_path(srt_path)
        source_id = srt_path.stem
        candidates: list[dict[str, object]] = []
        for start, end, text in build_windows(read_srt(srt_path)):
            features = features_for(text, scene)
            candidates.append(
                {
                    "source_id": source_id,
                    "source_file": str(srt_path.as_posix()),
                    "category": category,
                    "scene": scene,
                    "start": format_time(start),
                    "end": format_time(end),
                    "sample_type": sample_type_for(features),
                    "text": text,
                    "features": features,
                    "notes": "短样本，仅用于表达结构和风格特征标注。",
                }
            )
        picked_texts: set[str] = set()
        per_file_limit = max(12, TARGETS[category])
        ranked = sorted(candidates, key=lambda item: score_sample(str(item["text"]), list(item["features"]), picked_texts), reverse=True)
        for candidate in ranked:
            text = str(candidate["text"])
            if score_sample(text, list(candidate["features"]), picked_texts) < 15:
                continue
            picked_texts.add(text)
            by_category[category].append(candidate)
            if len(picked_texts) >= per_file_limit:
                break

    samples: list[dict[str, object]] = []
    global_seen: set[str] = set()
    for category, target in TARGETS.items():
        ranked = sorted(
            by_category[category],
            key=lambda item: score_sample(str(item["text"]), list(item["features"]), set()),
            reverse=True,
        )
        for candidate in ranked:
            text = str(candidate["text"])
            if text in global_seen:
                continue
            global_seen.add(text)
            samples.append(candidate)
            if sum(1 for item in samples if item["category"] == category) >= target:
                break
    for index, sample in enumerate(samples, 1):
        sample["sample_id"] = f"style-v0.2-{index:04d}"
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract short style samples from split SRT subtitles.")
    parser.add_argument(
        "--srt-root",
        type=Path,
        default=Path("materials/bilibili-style-sources/private/jianying-subtitles/split"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("materials/bilibili-style-sources/samples/style-samples-v0.2.jsonl"),
    )
    args = parser.parse_args()

    samples = extract_samples(args.srt_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")

    counts: dict[str, int] = {}
    for sample in samples:
        counts[str(sample["category"])] = counts.get(str(sample["category"]), 0) + 1
    print(json.dumps({"total": len(samples), "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
