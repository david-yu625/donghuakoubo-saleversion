from __future__ import annotations

from typing import Any

from ..contracts import VISUAL_STYLE_ID, validate_scene_facts, validate_storyboard
from .llm import json_chat


SYSTEM = """你负责知识短视频的单镜头视觉内容设计。每个镜头只设计一张可独立生成的组合插画，
不拆背景图和多个元素图。每张图只表达当前口播的一条核心关系，最多包含一个主对象和一个辅助对象；
删除装饰、重复信息和次要例子。标题和文字由后续视频层添加，图中不要出现字、数字或界面。
画布留白，主体清楚完整，能作为无限画布上的单个节点。严格按输入镜头顺序返回 JSON：
{"shots":[{"shot_id":"...","background_summary":"一句短结论","visual_brief":"一张图内的具体对象和关系","keyword":"口播原词"}]}。"""


def build_storyboard(facts: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, Any]:
    """Mirror Jianying step 04 semantics, adapted to one sparse canvas asset per scene."""
    validate_scene_facts(facts)
    values = values or {}
    source = [{"shot_id": shot["id"], "title": shot["title"], "voice": shot["voice"], "keyword": shot["keyword"]} for shot in facts["shots"]]
    payload = json_chat(values, SYSTEM, f"按输入逐镜头设计，不遗漏镜头：\n{source}")
    results = payload.get("shots")
    expected = [shot["id"] for shot in facts["shots"]]
    if not isinstance(results, list) or [str(item.get("shot_id", "")) for item in results] != expected:
        raise ValueError("storyboard must return every shot once and in order")
    rows = []
    for shot, item in zip(facts["shots"], results):
        visual = str(item.get("visual_brief", "")).strip()
        summary = str(item.get("background_summary", "")).strip()
        keyword = str(item.get("keyword", "")).strip()
        if not visual or not summary or not keyword or keyword not in shot["voice"]:
            raise ValueError(f"storyboard content is incomplete or keyword is not in source for {shot['id']}")
        rows.append({
            "shot_id": shot["id"], "background_summary": summary,
            "elements": [{"element_id": f"{shot['id']}_visual_01", "content": visual, "role": "single_composite"}],
            "element_count": 1, "asset_count": 1,
        })
    return validate_storyboard({"style_id": VISUAL_STYLE_ID, "density_policy": "one-composite-illustration-per-scene", "shots": rows}, [shot["id"] for shot in facts["shots"]])
