from __future__ import annotations

from typing import Any

from .llm import json_chat


SYSTEM = """你负责短视频生产的文案步骤，只写口播，不写分镜、画面或提示词。
开头用真实问题或异常现象切题，然后立即回答核心问题；正文沿一条清楚的因果主线递进。
每句话都新增事实、因果或解释，拒绝废话、重复结论、虚构身份和关注引导。保持自然口播感，
句子完整清楚，适合中文语音合成。事实不确定时不要编造。只输出 JSON：{"title":"...","wenan":"..."}。"""


def create_copywriting(topic: str, values: dict[str, str], supplied_path=None) -> dict[str, Any]:
    if supplied_path:
        import json
        payload = json.loads(supplied_path.read_text(encoding="utf-8"))
        if "wenan" in payload:
            result = payload
        else:
            voice = "\n".join([payload.get("voice", ""), *(shot.get("voice", "") for shot in payload.get("shots", []))]).strip()
            result = {"title": payload.get("title", topic), "wenan": voice}
    else:
        result = json_chat(values, SYSTEM, f"主题：{topic}\n控制在约 400～700 个汉字，避免拆成分镜。", temperature=0.45)
    title = str(result.get("title", topic)).strip()
    wenan = "\n".join(line.strip() for line in str(result.get("wenan", "")).splitlines() if line.strip())
    if not title or len(wenan) < 40:
        raise ValueError("copywriting output requires a title and at least 40 characters of narration")
    return {"title": title, "wenan": wenan}
