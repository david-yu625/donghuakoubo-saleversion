from __future__ import annotations

import re
from typing import Any

from ..contracts import validate_scene_facts, validate_screenplay


SENTENCE = re.compile(r"[^。！？!?；;，,：:\n]+[。！？!?；;，,：:]?")
MAX_CAPTION_CHARS = 24


def split_sentences(text: str) -> list[str]:
    """Split narration into readable semantic caption beats."""
    value = re.sub(r"\s+", " ", str(text)).strip()
    if not value:
        return []
    parts = [match.group().strip() for match in SENTENCE.finditer(value) if match.group().strip()]
    if len(parts) == 1 and len(parts[0]) > MAX_CAPTION_CHARS and not re.search(r"[。！？!?；;，,：:]", value):
        return [value[index:index + MAX_CAPTION_CHARS] for index in range(0, len(value), MAX_CAPTION_CHARS)]
    return parts or [value]


def build_captions(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for shot in shots:
        start = float(shot["start"])
        end = float(shot["end"])
        parts = split_sentences(str(shot["voice"]))
        weights = [max(1, len(re.sub(r"\s", "", part))) for part in parts]
        total = sum(weights)
        cursor = start
        for index, (part, weight) in enumerate(zip(parts, weights)):
            caption_end = end if index == len(parts) - 1 else cursor + (end - start) * weight / total
            captions.append({
                "start": round(cursor, 3),
                "end": round(caption_end, 3),
                "text": part,
            })
            cursor = caption_end
    return captions


def build_scene_facts(project: dict[str, Any], duration_seconds: float) -> dict[str, Any]:
    validate_screenplay(project)
    shots = project.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("screenplay must contain at least one shot")
    if duration_seconds <= 0:
        raise ValueError("narration duration must be positive")

    weights = [max(1, len(str(shot.get("voice", "")))) for shot in shots]
    total_weight = sum(weights)
    supplied_timing = all("start" in shot and "end" in shot for shot in shots)
    cursor = min(3.2, duration_seconds * 0.05)
    usable = max(1.0, duration_seconds - cursor)
    facts: list[dict[str, Any]] = []
    for index, (shot, weight) in enumerate(zip(shots, weights)):
        if not shot.get("voice") or not shot.get("title"):
            raise ValueError(f"shot {index + 1} is missing title or narration")
        start = float(shot["start"]) if supplied_timing else cursor
        end = float(shot["end"]) if supplied_timing else (duration_seconds if index == len(shots) - 1 else cursor + usable * weight / total_weight)
        facts.append({
            "id": str(shot.get("id", f"s{index + 1:02d}")),
            "index": index,
            "title": str(shot["title"]),
            "voice": str(shot["voice"]),
            "keyword": str(shot.get("keyword", "")),
            "visual": str(shot.get("visual", "")),
            "asset_type": str(shot.get("asset_type", "image")),
            "source": str(shot.get("source", "")),
            "start": round(start, 3),
            "end": round(end, 3),
        })
        cursor = end
    return validate_scene_facts({
        "title": str(project.get("title", "")),
        "durationSeconds": round(duration_seconds, 3),
        "shots": facts,
        "captions": build_captions(facts),
    })
