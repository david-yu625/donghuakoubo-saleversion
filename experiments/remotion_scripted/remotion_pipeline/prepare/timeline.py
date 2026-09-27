from __future__ import annotations

import re
from typing import Any


SENTENCE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?|[^\s]+")


def build_voice_timeline(copywriting: dict[str, Any], duration_seconds: float) -> dict[str, Any]:
    text = str(copywriting["wenan"])
    sentences = [match.group().strip() for match in SENTENCE.finditer(text) if match.group().strip()]
    if not sentences:
        raise ValueError("copywriting contains no sentences")
    weights = [max(1, len(re.sub(r"\s", "", sentence))) for sentence in sentences]
    total = sum(weights)
    cursor = 0.0
    rows = []
    for index, (sentence, weight) in enumerate(zip(sentences, weights)):
        end = duration_seconds if index == len(sentences) - 1 else cursor + duration_seconds * weight / total
        rows.append({"index": index, "text": sentence, "start": round(cursor, 3), "end": round(end, 3)})
        cursor = end
    return {"durationSeconds": round(duration_seconds, 3), "alignment": "duration-weighted-sentence-estimate", "sentences": rows}
