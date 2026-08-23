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
你是短视频科普选题策划编辑。请为一个 60~120 秒的科普口播视频策划选题。

好选题必须满足：
- 能回答一个明确问题，而不是“介绍某某领域”或“盘点几个方向”。
- 能讲清一个真实机制、判断方法、常见误区、失败原因或具体因果链。
- 来自普通用户在工作、学习、生活或使用软件时会遇到的任务、故障、选择或困惑。
- 用户看完后能立刻获得实际帮助：完成一项操作、解决一个问题、作出更好的选择、避开一个风险、提高效率，或理解异常现象后知道下一步怎么做。
- 即使讲概念或底层机制，也必须落到一个可执行的判断、操作建议或验证方法，不能只增加知识而不解决问题。
- 标题具体、自然、不过度夸张；可以使用问题句，但不要机械套格式。
- 避开历史记录中已经生成或使用过的主题，也避开只是替换名词、换一种问法但仍回答同一个核心问题的主题。

不要生成：泛泛的行业趋势、纯概念介绍、百科定义、励志观点、纯产品宣传、没有可解释机制的热点、需要实时数据才能成立的结论、和历史主题同义的换皮标题。

输出前请在内部自检：这个主题面向谁、会在什么具体场景遇到什么问题、看完后能采取什么行动。任一项说不清就重新选题，不要输出自检过程。

请先提出 6 个候选主题，再在内部比较它们的实用性、方向匹配度、可讲清程度、可操作性和与历史主题的差异度，按综合评分从高到低输出。
每个候选必须包含：topic（标题）、audience（目标用户）、scenario（具体场景）、problem（要解决的问题）、action（用户看完后能采取的行动）、reason（推荐理由）、score（1 到 10 的整数）。
只输出严格 JSON：{"candidates":[{"topic":"一个具体主题","audience":"目标用户","scenario":"具体场景","problem":"核心问题","action":"可执行行动","reason":"推荐理由","score":9}]}
""".strip()


def normalize_topic(value: str) -> str:
    """Normalize punctuation, whitespace and common title wrappers for exact matching."""
    text = value.strip().casefold()
    text = re.sub(r"[“”‘’'\"「」『』（）()【】\[\]{}<>《》：:，,。.!！?？、/\\_—–-]+", "", text)
    return re.sub(r"\s+", "", text)


def topic_comparison_key(value: str) -> str:
    """Collapse harmless question wrappers so reordered titles still compare equal."""
    text = normalize_topic(value)
    for prefix in ("什么是", "为什么", "为何", "何为", "如何理解", "如何", "怎么理解", "怎么", "怎样"):
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    for suffix in ("是什么", "是怎么回事", "怎么回事", "怎么办", "怎么做"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _topic_is_similar(candidate: str, used: list[str]) -> bool:
    """Catch exact, wrapper-only and obvious title-subset duplicates locally."""
    candidate_key = topic_comparison_key(candidate)
    if not candidate_key:
        return True
    for item in used:
        used_key = topic_comparison_key(item)
        if candidate_key == used_key:
            return True
        shorter, longer = sorted((candidate_key, used_key), key=len)
        if len(shorter) >= 6 and shorter in longer:
            return True
    return False


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


def _parse_topic_candidates(value: str) -> list[dict[str, object]]:
    start, end = value.find("{"), value.rfind("}")
    candidate = value[start:end + 1] if start >= 0 and end > start else value
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("模型返回格式不是 JSON 对象")
    raw_candidates = data.get("candidates")
    if isinstance(raw_candidates, list):
        result = []
        for item in raw_candidates:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if topic:
                result.append(item)
        if result:
            return result
    # Backward compatibility for callers/models using the original format.
    topic = str(data.get("topic", "")).strip()
    if topic:
        return [{"topic": topic, "score": 0}]
    raise ValueError("模型没有返回有效主题候选")


def _parse_topic(value: str) -> str:
    """Return the highest-ranked topic for compatibility with older callers."""
    candidates = _parse_topic_candidates(value)
    return str(max(candidates, key=lambda item: _candidate_score(item)).get("topic", "")).strip()


def _candidate_score(candidate: dict[str, object]) -> int:
    try:
        return max(0, min(10, int(candidate.get("score", 0))))
    except (TypeError, ValueError):
        return 0


def _candidate_is_usable(candidate: dict[str, object]) -> bool:
    """Require the evidence fields for the new ranked-candidate contract."""
    topic = str(candidate.get("topic", "")).strip()
    if not 6 <= len(topic) <= 60:
        return False
    # score=0 marks the legacy {"topic": ...} compatibility shape.
    if _candidate_score(candidate) == 0 and "audience" not in candidate:
        return True
    return all(str(candidate.get(field, "")).strip() for field in (
        "audience", "scenario", "problem", "action", "reason",
    ))


def generate_unique_topic(
    *,
    direction: str = "",
    context: str = "",
    api_key: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    output_root: Path = OUTPUT_ROOT,
    history_path: Path = HISTORY_PATH,
    max_attempts: int = 4,
) -> str:
    load_env_file(PROJECT_ROOT / ".env")
    direction = direction.strip()
    context = context.strip()
    if len(direction) > 200:
        raise ValueError("选题方向不能超过 200 个字符")
    if len(context) > 1200:
        raise ValueError("选题上下文不能超过 1200 个字符")
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    used = load_used_topics(output_root=output_root, history_path=history_path)
    client = OpenAI(api_key=key, base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    history = "\n".join(f"- {topic}" for topic in used[-300:]) or "（暂无历史主题）"
    direction_prompt = (
        f"用户指定的选题大方向是：{direction}\n"
        "新主题必须直接属于这个方向，并下钻到一个具体概念、机制、操作细节、判断方法、常见误区或失败原因。\n"
        "优先选择用户真实会遇到、看完后能解决问题或立即采取行动的细节，不要只做知识介绍。\n"
        "不要把大方向本身当作主题，不要扩展到无关领域；标题中应能看出它与该方向的直接关系。\n\n"
        if direction
        else "优先选择计算机或科技领域中能讲清具体机制、真实场景和判断方法的问题。\n\n"
    )
    context_prompt = (
        f"用户补充的上下文/行文思路是：{context}\n"
        "上下文中的术语、隐喻和限定条件必须优先遵守；如果存在歧义，以用户上下文为准，不要擅自按字面扩展到无关领域。\n\n"
        if context else
        "用户没有补充上下文，请默认面向普通电脑和科技产品用户，优先选择能解决真实问题的主题。\n\n"
    )
    user_prompt = (
        direction_prompt
        + context_prompt
        + "请提出 6 个候选主题并按综合评分从高到低排列。以下主题已经生成过或使用过，不能重复，也不能只换同义词：\n"
        + history
        + "\n\n如果历史中已有相近主题，请改讲这个方向下的另一个具体问题。每个候选都必须能在 60~120 秒内讲清，并给出明确可执行行动。"
    )
    for _ in range(max_attempts):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": TOPIC_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            # Six candidates include audience, scenario and action fields;
            # 120 tokens is too small and can truncate the JSON mid-response.
            max_tokens=1200,
        )
        candidates = _parse_topic_candidates(response.choices[0].message.content or "")
        candidates.sort(key=_candidate_score, reverse=True)
        topic = next(
            (
                str(item.get("topic", "")).strip()
                for item in candidates
                if _candidate_is_usable(item)
                and not _topic_is_similar(str(item.get("topic", "")), used)
            ),
            "",
        )
        if not topic:
            user_prompt += "\n模型返回的候选主题都与历史重复、过短或无效，请重新提出一组不同核心问题。"
            continue
        record_topic(topic, status="generated", history_path=history_path)
        return topic
    raise RuntimeError("模型连续生成重复主题，请稍后重试")


def generate_unique_topics(count: int, **kwargs) -> list[str]:
    if count < 1 or count > 30:
        raise ValueError("批量主题数量必须在 1 到 30 之间")
    return [generate_unique_topic(**kwargs) for _ in range(count)]
