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
from ..industry_profiles import DEFAULT_INDUSTRY, industry_prompt, resolve_industry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"
DEFAULT_REFERENCE = PROJECT_ROOT / "src" / "copywriting_style_reference.md"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_CHAR_BUDGET = 18000

SYSTEM_PROMPT = """
#背景
1.你是一名行业知识科普作者，负责把专业知识用准确、易懂的方式讲清楚。
2.现在想做抖音自媒体短视频。通过把当前行业中的复杂知识讲成普通用户能理解、能行动的内容。

#目标
 需要你根据主题帮我生成文案。

#要求
1.开头必须抛异常或者问题，要开门见山，直指主题
2.持续持续持续输出高密度价值信息，防止滑走。
3.拒绝废话。
4.文案要符合自媒体文案的特点，开头吸引人，信息密度高。
5.行文思路要有逻辑，一步一步递进式讲解，也可以分类说明，千万不可以杂乱无章。
6.不需要做其他的分镜头设计，只需要输出最终文案。分行服务于语义和 TTS：一句一行，每行表达一个完整动作、事实或因果；不要把一句话拆成多个空短句，也不要把多句话合并在一行。
7.要有一点口播感，千万别啰嗦。
8.不要虚构作者身份、账号名称、人物称呼或关注引导。用户没有提供身份信息时，不要在文案中自称。
9.每句话必须新增事实、因果或解释。同一个问题只问一次，同一个比喻只用一次，同一个结论只说一次。结尾不要复述全文；删掉后不影响理解的句子必须删除。

#文案框架
0.题意锁定：先识别完整题目及其问题类型，保留题目中的所有关键限定。不能只抓其中一个关键词，也不能把起源、原理、用途、比较、操作等题型互相替换。
1.开头：只提出一个真实、自然并且与当前主题直接相关的问题或异常现象。禁止虚构“大家都说”之类的前提，禁止强行反差、文字游戏和生造概念。
2.核心答案：紧接着用一句话正面回答开头，明确这篇文案要讲清的核心结论；如果正文不能直接回答，必须重新设计开头。
3.递进展开：只沿一条主线，按照“原因—关键过程—结果或影响”逐层讲解。
4.事实支撑：事实、例子和数据只用于解释主线，不扩展无关知识点，不中途换题。
5.结尾：回答开头的问题，给观众留下一个明确的新认识，不重复正文，不添加口号。
""".strip()

OUTPUT_PROTOCOL_PROMPT = """
#程序输出
程序需要可解析的 JSON，只输出以下对象，不要输出解释、Markdown 或分镜。wenan 中必须使用 \\n 分隔每句话：
{"wenan":"第一句话\\n第二句话\\n第三句话"}
""".strip()

REVISION_SYSTEM_PROMPT = """
#角色
你是一名谨慎的文案编辑。用户已经认可现有文案的大部分内容，只希望根据少量意见进行微调。

#修改原则
1. 只修改用户意见明确涉及的句子和为保证上下文连贯而必须联动的少量句子。
2. 未被意见涉及的事实、观点、结构、叙述顺序、表达风格和句子尽量原样保留，禁止借机重写整篇。
3. 不得擅自增加新的主题、事实、案例、数据、人物身份、关注引导或结论。
4. 用户要求删除时直接删除相关内容；用户要求补充时只补充必要信息；用户要求调整语气时保持原有信息不变。
5. 输出修改后的完整文案，不要输出修改说明、对比、批注或省略号。
6. 保持口播文案一句一行，每行表达一个完整动作、事实或因果。
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 src 的逐行口播文案。")
    parser.add_argument("topic", nargs="+")
    parser.add_argument("-o", "--output", type=Path, help="默认 output/<topic>/wenan.txt")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="参考样例文件或目录；默认读取 copywriting_style_reference.md")
    parser.add_argument("--target-chars", type=int, default=700, help="文案最长字数；0 表示不限制。")
    parser.add_argument("--story-world", default="", help="可选故事载体，例如快递站、图书馆、工厂、餐馆；留空或填写自动选择时由模型判断是否需要。")
    parser.add_argument("--context", default="", help="补充主题背景、概念定义或行文思路，帮助模型避免歧义。")
    parser.add_argument("--industry", default=DEFAULT_INDUSTRY, help="内容行业")
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
            context=args.context,
            industry=args.industry,
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
    context: str = "",
    industry: str = DEFAULT_INDUSTRY,
) -> dict[str, object]:
    if not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=base_url)
    del reference, story_world
    system_prompt = build_system_prompt(topic, industry)
    user_prompt = "\n\n".join([
        context_guidance(context, topic),
        length_guidance(target_chars),
    ])
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": OUTPUT_PROTOCOL_PROMPT},
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
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": OUTPUT_PROTOCOL_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_content},
                {
                    "role": "user",
                    "content": (
                        f"上一版文案未通过逐行格式校验：{validation_error}\n"
                        "请重写完整文案。一句话一行，每行语义完整，并输出严格 JSON。"
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
            raise RuntimeError("模型连续返回未按一句一行排版的文案，请重试") from exc
    payload["wenan"] = clean_wenan(str(payload["wenan"]))
    return payload


def revise_copywriting(
    *,
    original: str,
    feedback: str,
    topic: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    max_tokens: int = 4096,
) -> str:
    original = clean_wenan(original)
    feedback = feedback.strip()
    if not original:
        raise ValueError("现有文案不能为空")
    if not feedback:
        raise ValueError("请先填写修改意见")
    if not api_key.strip():
        raise ValueError("缺少 DEEPSEEK_API_KEY")

    user_prompt = "\n\n".join([
        f"#当前主题\n{topic.strip() or '未命名主题'}",
        f"#用户修改意见\n{feedback}",
        f"#现有文案\n{original}",
        "#任务\n基于现有文案做最小范围修改，并返回修改后的完整文案。",
    ])
    client = OpenAI(api_key=api_key.strip(), base_url=base_url.strip() or DEFAULT_BASE_URL)
    messages = [
        {"role": "system", "content": REVISION_SYSTEM_PROMPT},
        {"role": "system", "content": OUTPUT_PROTOCOL_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    response = client.chat.completions.create(
        model=model.strip() or DEFAULT_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    raw_content = response.choices[0].message.content or ""
    try:
        payload = parse_copywriting_payload(raw_content)
        revised = clean_wenan(str(payload["wenan"]))
        validate_copywriting_text(revised)
        return revised
    except (KeyError, ValueError) as first_error:
        repair_response = client.chat.completions.create(
            model=model.strip() or DEFAULT_MODEL,
            messages=[
                *messages,
                {"role": "assistant", "content": raw_content},
                {
                    "role": "user",
                    "content": (
                        f"上一版结果无法使用：{first_error}\n"
                        "请继续遵守最小修改原则，返回一句一行的完整文案和严格 JSON。"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )
        try:
            payload = parse_copywriting_payload(repair_response.choices[0].message.content or "")
            revised = clean_wenan(str(payload["wenan"]))
            validate_copywriting_text(revised)
            return revised
        except (KeyError, ValueError) as exc:
            raise RuntimeError("模型连续返回无法使用的微调文案，请重试") from exc


def validate_copywriting_text(text: str, target_chars: int = 0) -> None:
    lines = [line.strip() for line in clean_wenan(text).splitlines() if line.strip()]
    minimum_lines = 3 if 0 < target_chars < 60 else 6
    if len(lines) < minimum_lines:
        raise ValueError(f"文案必须至少拆成 {minimum_lines} 行，不能把多句话塞在一行")
    if len(set(lines)) != len(lines):
        raise ValueError("文案包含重复行")


def build_system_prompt(topic: str, industry: str = DEFAULT_INDUSTRY) -> str:
    """Insert the active topic into the initialization section sent to the model."""

    return "\n\n".join([
        SYSTEM_PROMPT,
        "#行业设定\n" + industry_prompt(industry),
        "#初始化",
        f"    1.我要讲解的题目是“{topic}”。",
    ])


def context_guidance(context: str, topic: str) -> str:
    value = context.strip()
    if not value:
        return (
            "#上下文与行文思路\n"
            f"当前题目是：{topic}\n"
            "未提供额外上下文。严格按照题目本身理解，不要擅自替换关键词含义。"
        )
    return (
        "#上下文与行文思路\n"
        f"当前题目是：{topic}\n"
        "用户补充的背景和要求如下。它用于消歧和限定表达方向，优先解释题目中的专有含义；"
        "不要把补充内容扩展成题目之外的新主题，也不要凭空添加其中没有提供的事实。\n"
        f"{value}"
    )


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
        normal_min = max(1, round(target_chars * 0.7))
        normal_max = max(normal_min, round(target_chars * 0.9))
        return (
            f"#字数要求\n文案最长不超过 {target_chars} 个有效字（中文、英文和数字，不计标点空白）。\n"
            f"通常以 {normal_min}~{normal_max} 字为合适篇幅；信息量大的主题可以写到接近 {target_chars} 字，"
            "只有内容简单的主题才明显缩短。"
            "这只是篇幅参考，不是最低字数；内容讲清楚后立即结束，不要为了接近上限补充废话。"
        )
    return (
        "#字数要求\n"
        "未设置最长字数。按信息完整度自然展开，不要用重复内容凑长度。"
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
