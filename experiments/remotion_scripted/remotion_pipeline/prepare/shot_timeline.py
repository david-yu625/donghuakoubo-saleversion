from __future__ import annotations

from typing import Any

from .llm import json_chat


SYSTEM = """你负责按口播已有语义阶段合并连续句子，决定分镜边界和短标题。
同一叙述任务的连续句子要合并；只在叙述任务明确改变时拆分。不设固定镜头数，不按每句一镜。
输入句子必须完整、连续、按原顺序覆盖一次。关键词必须是该镜头口播中的原文短语。
只输出 JSON：{"shots":[{"start_index":0,"end_index":1,"title":"...","keyword":"..."}]}。索引闭区间。"""


def create_shot_timeline(copywriting: dict[str, Any], voice_timeline: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    sentences = voice_timeline["sentences"]
    payload = json_chat(values, SYSTEM, "按语义阶段分组以下口播句子：\n" + "\n".join(f"{row['index']}: {row['text']}" for row in sentences))
    groups = payload.get("shots")
    if not isinstance(groups, list) or not groups:
        raise ValueError("shot timeline must return shots")
    shots = []
    next_index = 0
    for position, group in enumerate(groups):
        start_index, end_index = int(group["start_index"]), int(group["end_index"])
        if start_index != next_index or end_index < start_index or end_index >= len(sentences):
            raise ValueError("shot timeline must cover consecutive sentence indices exactly once")
        voice_rows = sentences[start_index:end_index + 1]
        voice = "".join(row["text"] for row in voice_rows)
        keyword = str(group.get("keyword", "")).strip()
        if not keyword or keyword not in voice:
            raise ValueError(f"shot {position + 1} keyword must occur verbatim in its narration")
        shots.append({
            "id": f"s{position + 1:02d}", "title": str(group["title"]).strip(), "voice": voice,
            "keyword": keyword, "visual": "", "asset_type": "image", "source": "",
            "start": voice_rows[0]["start"], "end": voice_rows[-1]["end"],
            "sentence_start": start_index, "sentence_end": end_index,
        })
        next_index = end_index + 1
    if next_index != len(sentences):
        raise ValueError("shot timeline did not cover all narration sentences")
    return {"title": copywriting["title"], "durationSeconds": voice_timeline["durationSeconds"], "shots": shots}
