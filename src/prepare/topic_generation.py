"""Generate non-repeating short-video topics and keep their local history."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from ..env import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "output"
HISTORY_PATH = OUTPUT_ROOT / "topic_history.jsonl"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

TOPIC_SYSTEM_PROMPT = """
你是短视频科普选题编辑。请生成一个适合 60~120 秒口播视频的具体选题，不要写宽泛栏目名。

好选题必须满足：
- 能回答一个明确问题，而不是“介绍某某领域”或“盘点几个方向”。
- 能讲清一个真实机制、判断方法、常见误区、失败原因或具体因果链。
- 普通观众能在工作、学习、生活或使用软件时遇到，或者能通过一个小实验或操作验证。
- 标题具体、自然、不过度夸张；可以使用问题句，但不要机械套格式。
- 避开历史记录中已经生成或使用过的主题，也避开只是替换名词、换一种问法但仍回答同一个核心问题的主题。

不要生成：泛泛的行业趋势、励志观点、纯产品宣传、没有可解释机制的热点、需要实时数据才能成立的结论、和历史主题同义的换皮标题。

只输出严格 JSON：{"topic":"一个主题"}
""".strip()


def normalize_topic(value: str) -> str:
    """Normalize punctuation, whitespace and common title wrappers for exact matching."""
    text = value.strip().casefold()
    text = re.sub(r"[“”‘’'\"「」『』（）()【】\[\]{}<>《》：:，,。.!！?？、/\\_—–-]+", "", text)
    return re.sub(r"\s+", "", text)


def topic_comparison_key(value: str) -> str:
    """Collapse harmless question wrappers so reordered titles still compare equal."""
    text = normalize_topic(value)
    for prefix in ("什么是", "何为", "如何理解", "如何", "怎么理解", "怎么", "怎样"):
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    for suffix in ("是什么", "是怎么回事", "怎么回事"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _read_history(path: Path = HISTORY_PATH) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        topic = str(value.get("topic", "")).strip()
        if topic:
            entries.append({"topic": topic, "status": str(value.get("status", "generated"))})
    return entries


def _scan_existing_projects(output_root: Path = OUTPUT_ROOT) -> list[str]:
    if not output_root.is_dir():
        return []
    topics: list[str] = []
    for directory in output_root.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if (directory / "wenan.txt").is_file() or (directory / "timeline.csv").is_file() or (directory / "landscape" / "timeline.csv").is_file():
            topics.append(directory.name)
    return topics


def load_used_topics(*, output_root: Path = OUTPUT_ROOT, history_path: Path = HISTORY_PATH) -> list[str]:
    values = [entry["topic"] for entry in _read_history(history_path)]
    values.extend(_scan_existing_projects(output_root))
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_topic(value)
        if key and key not in seen:
            seen.add(key)
            unique.append(value.strip())
    return unique


def record_topic(topic: str, *, status: str = "generated", history_path: Path = HISTORY_PATH) -> None:
    topic = topic.strip()
    if not topic:
        raise ValueError("主题不能为空")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {normalize_topic(item["topic"]): item for item in _read_history(history_path)}
    key = normalize_topic(topic)
    if key in existing:
        if status == "used" and existing[key].get("status") != "used":
            with history_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"topic": topic, "status": status, "updated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n")
        return
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"topic": topic, "status": status, "created_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n")


def _parse_topic(value: str) -> str:
    start, end = value.find("{"), value.rfind("}")
    candidate = value[start:end + 1] if start >= 0 and end > start else value
    data = json.loads(candidate)
    topic = str(data.get("topic", "")).strip() if isinstance(data, dict) else ""
    if not topic:
        raise ValueError("模型没有返回有效主题")
    return topic


def generate_unique_topic(
    *,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    output_root: Path = OUTPUT_ROOT,
    history_path: Path = HISTORY_PATH,
    max_attempts: int = 4,
) -> str:
    load_env_file(PROJECT_ROOT / ".env")
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    used = load_used_topics(output_root=output_root, history_path=history_path)
    client = OpenAI(api_key=key, base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    used_keys = {topic_comparison_key(item) for item in used}
    history = "\n".join(f"- {topic}" for topic in used[-300:]) or "（暂无历史主题）"
    user_prompt = (
        "请提出一个新主题。以下主题已经生成过或使用过，不能重复，也不能只换同义词：\n"
        + history
        + "\n\n优先选择能讲清具体机制、真实场景和判断方法的计算机或科技主题；如果历史中已有相近主题，请换到不同问题。"
    )
    for _ in range(max_attempts):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": TOPIC_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            max_tokens=120,
        )
        topic = _parse_topic(response.choices[0].message.content or "")
        if topic_comparison_key(topic) in used_keys:
            user_prompt += f"\n模型刚才返回的主题“{topic}”已重复，请换一个不同核心问题。"
            continue
        record_topic(topic, status="generated", history_path=history_path)
        return topic
    raise RuntimeError("模型连续生成重复主题，请稍后重试")


def generate_unique_topics(count: int, **kwargs) -> list[str]:
    if count < 1 or count > 30:
        raise ValueError("批量主题数量必须在 1 到 30 之间")
    return [generate_unique_topic(**kwargs) for _ in range(count)]
