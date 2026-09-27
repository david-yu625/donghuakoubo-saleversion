from __future__ import annotations

import json
import re
from typing import Any

import requests


def json_chat(values: dict[str, str], system: str, user: str, *, temperature: float = 0.35) -> dict[str, Any]:
    """Use the same DeepSeek-compatible model configured by Jianying mode."""
    key = values.get("DEEPSEEK_API_KEY") or values.get("DOUBAO_TEXT_API_KEY")
    if not key:
        raise ValueError("text generation requires DEEPSEEK_API_KEY or DOUBAO_TEXT_API_KEY")
    base = values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": values.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=(15, 120),
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("text model must return a JSON object")
    return value
