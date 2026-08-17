#!/usr/bin/env python3
"""src step 01: generate line-by-line copywriting."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from openai import OpenAI, OpenAIError

from ..env import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"
DEFAULT_REFERENCE = PROJECT_ROOT / "src" / "copywriting_style_reference.md"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_CHAR_BUDGET = 18000

SYSTEM_PROMPT = """
你是短视频科普口播文案作者。你的任务不是把题目说得漂亮，而是让观众看完后能复述：对象是什么、它怎么工作、为什么会这样，以及自己如何判断或使用。

先做一次内部取舍：本条只回答一个具体问题，确定一个结论；题目太大就主动缩小范围。不要输出取舍过程。

写作内容必须优先提供事实和机制：
- 技术、科学、工具类：用一个具体场景贯穿，写清输入是什么、经过哪些处理、输出怎样变化；第一次出现术语先用日常话解释，再给正式名称。
- 实用、职场、商业类：写清谁在什么场景遇到什么问题、能观察到什么信号、按什么条件做什么动作，以及动作后的结果。
- 历史、人物、故事类：写清人物或事件的目标、阻碍、关键选择、转折和结果；区分史实、传说和不确定说法。
- 不确定的事实、数字、价格、版本或性能不要编造；资料不足时明确范围，不用绝对结论填空。

正文按“具体问题或结果 -> 关键缺口 -> 机制或事件推进 -> 例子/边界 -> 可验证结论”展开。相邻两行要有因果或承接关系，但不要为了制造悬念故意隐藏一句话就能说清的事实。抽象判断后面必须紧跟对象、动作、例子、结果或判断标准。比喻只有在能降低理解难度时才使用，最多一个，并且不能替代主题本身。

删除以下内容：时代背景套话、空泛评价、正确但不能执行的建议、同义重复、没有新增事实的金句、点赞关注话术，以及连续堆砌的并列知识点。不要强行制造反常识、两次转折或戏剧冲突。

分行服务于语义和 TTS：一行表达一个完整动作或因果，不要把一句话拆成多个空短句。250 字左右通常写 10~16 行；目标字数变化时按信息完整度调整，不为凑行数重复。

自检后再输出：删掉任意一句后，若信息、因果或判断没有损失，就删掉它。全文至少包含一个具体对象、一个具体过程或事件、一个结果；适用时还要包含一个可观察信号和一个可执行动作。

输出严格 JSON，不要输出解释、Markdown 或额外字段：
{
  "wenan": "标题\n第一句\n第二句"
}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 src 的逐行口播文案。")
    parser.add_argument("topic", nargs="+")
    parser.add_argument("-o", "--output", type=Path, help="默认 output/<topic>/wenan.txt")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="参考样例文件或目录；默认读取 copywriting_style_reference.md")
    parser.add_argument("--target-chars", type=int, default=0, help="目标文案字数，按中文字数量估算；0 表示不指定。")
    parser.add_argument("--story-world", default="", help="可选故事载体，例如快递站、图书馆、工厂、餐馆；留空或填写自动选择时由模型判断是否需要。")
    parser.add_argument("--api-key", default="", help="默认读取 DEEPSEEK_API_KEY")
    parser.add_argument("--model", default="", help=f"默认读取 DEEPSEEK_MODEL 或 {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default="", help="默认 DeepSeek OpenAI 兼容地址")
    parser.add_argument("--max-tokens", type=int, default=4096)
    return parser.parse_args()


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    args = parse_args()
    topic = " ".join(args.topic).strip()
    output = args.output.expanduser().resolve() if args.output else default_output_path(topic, args.output_root)
    reference = read_reference(args.reference)
    try:
        payload = generate_copywriting(
            topic=topic,
            reference=reference,
            api_key=args.api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            model=args.model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            base_url=args.base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            max_tokens=args.max_tokens,
            target_chars=args.target_chars,
            story_world=args.story_world,
        )
        wenan = clean_wenan(str(payload["wenan"]))
    except (KeyError, ValueError, RuntimeError, OpenAIError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(wenan + "\n", encoding="utf-8")
    print(f"文案：{output}")
    return 0


def generate_copywriting(
    *,
    topic: str,
    reference: str,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int,
    target_chars: int,
    story_world: str,
) -> dict[str, object]:
    if not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=base_url)
    user_prompt = "\n".join([
        f"题目：{topic}",
        story_world_guidance(story_world, topic),
        "",
        length_guidance(target_chars),
        "",
        retention_guidance(),
        "",
        "参考样例和拆解：",
        reference,
    ])
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    raw_content = response.choices[0].message.content or ""
    try:
        payload = parse_copywriting_payload(raw_content)
    except ValueError:
        repair_response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你只负责修复 JSON 语法。保持 wenan 文本内容不变，只输出一个合法 JSON 对象，字段必须是 wenan。",
                },
                {"role": "user", "content": raw_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )
        repaired_content = repair_response.choices[0].message.content or ""
        try:
            payload = parse_copywriting_payload(repaired_content)
        except ValueError as exc:
            raise RuntimeError("模型连续返回无法解析的文案 JSON，请重试") from exc
    try:
        validate_copywriting_text(str(payload["wenan"]), target_chars)
    except ValueError as validation_error:
        rewrite_response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_content},
                {
                    "role": "user",
                    "content": (
                        f"上一版文案未通过结构校验：{validation_error}\n"
                        "请重写完整文案。保留具体对象、过程、结果和判断依据；每行保持语义完整，并输出严格 JSON。"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )
        try:
            payload = parse_copywriting_payload(rewrite_response.choices[0].message.content or "")
            validate_copywriting_text(str(payload["wenan"]), target_chars)
        except ValueError as exc:
            raise RuntimeError("模型连续返回不符合逐层展开要求的文案，请重试") from exc
    return payload


def validate_copywriting_text(text: str, target_chars: int = 0) -> None:
    lines = [line.strip() for line in clean_wenan(text).splitlines() if line.strip()]
    minimum_lines = 3 if 0 < target_chars < 60 else 6
    if len(lines) < minimum_lines:
        raise ValueError(f"文案必须至少拆成 {minimum_lines} 行，不能把多层内容塞在一行")
    if len(set(lines)) != len(lines):
        raise ValueError("文案包含重复行")


def parse_copywriting_payload(raw_content: str) -> dict[str, object]:
    candidate = extract_json_object(strip_code_fence(raw_content))
    for value in (candidate, repair_json_string_syntax(candidate)):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        wenan = payload.get("wenan")
        if isinstance(wenan, str) and wenan.strip():
            return payload
    raise ValueError("模型返回的文案不是合法 JSON")


def strip_code_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json_object(value: str) -> str:
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value.strip()
    return value[start:end + 1]


def repair_json_string_syntax(value: str) -> str:
    repaired: list[str] = []
    in_string = False
    escaped = False
    for index, character in enumerate(value):
        if not in_string:
            repaired.append(character)
            if character == '"':
                in_string = True
            continue
        if escaped:
            repaired.append(character)
            escaped = False
            continue
        if character == "\\":
            repaired.append(character)
            escaped = True
            continue
        if character == '"':
            next_character = next_non_space_character(value, index + 1)
            if next_character in {"", ":", ",", "}", "]"}:
                repaired.append(character)
                in_string = False
            else:
                repaired.append('\\"')
            continue
        if ord(character) < 0x20:
            repaired.append(json.dumps(character)[1:-1])
        else:
            repaired.append(character)
    return "".join(repaired)


def next_non_space_character(value: str, start: int) -> str:
    for character in value[start:]:
        if not character.isspace():
            return character
    return ""


def length_guidance(target_chars: int) -> str:
    if target_chars > 0:
        min_chars = max(40, round(target_chars * 0.88))
        max_chars = max(min_chars, round(target_chars * 1.12))
        # Keep semantic sentences intact. Around 16-22 Chinese characters per
        # line is more useful than forcing one short fragment per subtitle.
        target_lines = max(6, min(60, round(target_chars / 18)))
        min_lines = max(6, round(target_lines * 0.85))
        max_lines = max(min_lines, round(target_lines * 1.15))
        return (
            f"目标文案字数：约 {target_chars} 个中文字。\n"
            f"请按这个字数控制文案总量，而不是按参考 demo 的长度。\n"
            f"建议输出 {min_lines}~{max_lines} 行，全文约 {min_chars}~{max_chars} 个中文字。\n"
            "宁可少一点，也不要为了凑字数写废话。"
        )
    return "目标文案字数：未指定。请按信息完整度生成约 12~20 行，不要用短句或重复内容凑长度。"


def retention_guidance() -> str:
    return (
        "本次创作硬约束：\n"
        "只回答一个具体问题，正文必须给出具体对象、过程或事件，以及可见结果。\n"
        "技术和科学主题写清输入、处理、输出和一个边界；实用主题写清场景、观察信号、动作和判断条件；故事主题写清目标、阻碍、转折和结果。\n"
        "每一行都要新增事实、动作、因果、例子或判断依据；删掉不能影响理解的句子。\n"
        "不强行制造反常识、悬念或转折，不写空泛建议、重复总结和营销话术。"
    )


def story_world_guidance(story_world: str, topic: str) -> str:
    value = story_world.strip()
    if value and value not in {"自动选择", "自动", "通用故事"}:
        return (
            f"故事载体：{value}\n"
            f"请把文案规划成“以{value}故事讲{topic}”。\n"
            "要求：故事中的人物、地点、道具和冲突都服务于当前主题；不要引入与题目无关的领域概念。"
        )
    return (
        "故事载体：未指定。\n"
        "请根据题目本身选择最自然的表达：故事和人物题材直接讲事件，知识题材解释事实与原因，操作题材讲清步骤和结果。\n"
        "围绕题目本身展开，不要主动套用其他领域的比喻；确有必要时最多使用一个主要比喻，并及时回到主题。"
    )


def read_reference(path: Path) -> str:
    path = path.expanduser().resolve()
    if not path.exists():
        return ""
    if path.is_dir():
        files = sorted([item for item in path.glob("*.md") if item.name != "README.md" and item.is_file()])
        parts = []
        used = 0
        for file_path in files:
            if used >= DEFAULT_CHAR_BUDGET:
                break
            section = file_path.read_text(encoding="utf-8-sig")
            section = clean_reference(section)
            if not section.strip():
                continue
            budgeted = section[: max(0, DEFAULT_CHAR_BUDGET - used)]
            parts.append(f"## {file_path.name}\n\n{budgeted}")
            used += len(budgeted)
        return "\n\n".join(parts)
    return clean_reference(path.read_text(encoding="utf-8-sig"))


def clean_reference(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def clean_wenan(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def default_output_path(topic: str, output_root: Path) -> Path:
    safe = "".join(char for char in topic if char not in '/\\:*?"<>|') or "未命名"
    return output_root.expanduser().resolve() / safe / "wenan.txt"


if __name__ == "__main__":
    raise SystemExit(main())
