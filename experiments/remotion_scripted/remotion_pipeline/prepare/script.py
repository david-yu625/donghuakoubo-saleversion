from __future__ import annotations

import json
import re
from typing import Any

import requests

from ..contracts import validate_screenplay as validate_screenplay_contract


def create_screenplay(topic: str, values: dict[str, str], supplied_path=None) -> dict[str, Any]:
    if supplied_path:
        project = json.loads(supplied_path.read_text(encoding="utf-8"))
    else:
        key = values.get("DEEPSEEK_API_KEY") or values.get("DOUBAO_TEXT_API_KEY")
        if not key:
            raise ValueError("screenplay generation requires DEEPSEEK_API_KEY or DOUBAO_TEXT_API_KEY")
        base = values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        model = values.get("DEEPSEEK_MODEL", "deepseek-chat")
        prompt = f"""Write a Chinese short-video screenplay about: {topic}.
Return JSON only: {{"title": string, "voice": string, "shots": [..]}}.
Create 5 to 8 shots in a clear cause-and-effect progression. Each shot must have id, title, voice, keyword, visual. Each voice is one or two spoken sentences and expresses one claim. Keywords are concise and must appear verbatim in the shot narration. Visual describes a concrete editorial documentary image, not a layout, diagram, or text. Do not put any readable text in image descriptions."""
        response = requests.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0.45, "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        project = json.loads(content)
    return validate_screenplay_contract(project)


def validate_screenplay(project: dict[str, Any]) -> None:
    shots = project.get("shots")
    if not isinstance(shots, list) or not 4 <= len(shots) <= 10:
        raise ValueError("screenplay must contain between 4 and 10 shots")
    for index, shot in enumerate(shots):
        for field in ("title", "voice", "keyword"):
            if not str(shot.get(field, "")).strip():
                raise ValueError(f"shot {index + 1} is missing {field}")
