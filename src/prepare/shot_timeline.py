#!/usr/bin/env python3
"""Step 03: group the narration timeline into titled semantic Shots.

This step owns Shot boundaries and their semantic titles.  It does not design images, text
elements, framing, camera motion, lighting, layout, or visual style.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from openai import OpenAI

from ..env import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

MODEL_FIELDS = ["shot_id", "timeline_start_index", "timeline_end_index", "shot_title"]
SHOT_FIELDS = ["shot_id", "分镜标题", "开始时间ms", "结束时间ms", "分镜对应原始文案内容"]

SYSTEM_PROMPT = """你负责知识动画流水线的第03步：把配音时间线划分成语义 Shot，并为每个 Shot 提炼一个标题。

你的任务只有两个：识别原始文案已经存在的叙述阶段，决定哪些连续句子属于同一个阶段；为每个阶段提炼一个准确、简短的分镜标题。不要替原文创造总分结构、论点数量或新的逻辑层级。不要设计图片、背景、元素、画面文字、景别、运镜、光影、布局、颜色或风格；这些都属于后续步骤。

# 语义分组原则

- 完全服从原始文案已有的组织方式。原文是总分、递进、因果、并列、故事、问答或其他结构，就按它实际存在的结构分组，不能强行改造成另一种结构。
- 当叙述任务发生明确变化时才开始新的 Shot，例如从提出问题转为解释原因、从原理转为案例、从案例转为方法、从方法转为结论。以上只是边界信号，不是必须套用的结构。
- 同一叙述阶段内的连续句子必须放在一起。Shot 是完整的语义段，不是机械的一句一镜。
- 不预设 Shot 数量。数量由原文实际的语义阶段决定，不能为了凑数量拆段或合段。
- 开头、案例、转折和结尾是否单独成 Shot，只取决于它们是否承担独立的叙述任务。
- 每个 timeline 行必须且只能属于一个 Shot；Shot 必须按时间连续，不能遗漏、重叠或调换句子顺序。

# 分镜标题

- 每个 Shot 必须有一个标题，只概括该 Shot 覆盖文案的核心问题、核心关系或核心结论。
- 标题必须能够区分相邻 Shot 各自在讲什么，不能使用“第一部分”“继续讲解”“更多内容”等空泛文字。
- 标题应简短直接，不强制使用数字编号，不添加原文没有的判断，不写画面、风格或排版要求。
- 标题是后续背景图直接使用的标题，因此必须输出可直接显示的成品文字，不要写成解释句或提示词。

# 输出

只输出完整 CSV，不要输出解释、Markdown 或代码块。表头必须完全等于：
shot_id,timeline_start_index,timeline_end_index,shot_title

`timeline_start_index` 和 `timeline_end_index` 都是闭区间。shot_id 从 1 连续编号。
shot_title 是当前 Shot 可直接显示的分镜标题。
不要输出时间、文案内容或任何视觉字段；程序会根据索引从原始 timeline 确定时间和原文。
""".strip()


@dataclass(frozen=True)
class TimelineRow:
    index: int
    text: str
    start_ms: int
    end_ms: int
    duration_ms: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把配音时间线划分为语义 Shot。")
    parser.add_argument("wenan_txt", type=Path)
    parser.add_argument("timeline_csv", type=Path)
    parser.add_argument("--output", type=Path, help="默认写到 timeline 同目录 shot_timeline_source_time.csv")
    parser.add_argument("--request-output", type=Path, help="可选，保存发送给模型的完整提示词")
    parser.add_argument("--api-key", default="", help="默认读取 DEEPSEEK_API_KEY")
    parser.add_argument("--model", default="", help=f"默认读取 DEEPSEEK_MODEL 或 {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default="", help=f"默认读取 DEEPSEEK_BASE_URL 或 {DEFAULT_BASE_URL}")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--max-attempts", type=int, default=3, help="模型输出校验失败时的最大生成次数")
    parser.add_argument("--dry-run", action="store_true", help="不调用模型，按相邻句子生成规则化示例")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(PROJECT_ROOT / ".env")
        wenan_path = args.wenan_txt.expanduser().resolve()
        timeline_path = args.timeline_csv.expanduser().resolve()
        output = args.output.expanduser().resolve() if args.output else timeline_path.with_name("shot_timeline_source_time.csv")
        wenan = wenan_path.read_text(encoding="utf-8-sig").strip()
        timeline = parse_timeline_csv(timeline_path)
        user_prompt = build_user_prompt(wenan, timeline)
        if args.request_output:
            request_output = args.request_output.expanduser().resolve()
            request_output.parent.mkdir(parents=True, exist_ok=True)
            request_output.write_text(f"System:\n{SYSTEM_PROMPT}\n\nUser:\n{user_prompt}", encoding="utf-8")

        if args.dry_run:
            shots = build_shots(generate_dry_run(timeline), timeline)
        else:
            shots = generate_validated_shots(
                timeline=timeline,
                user_prompt=user_prompt,
                api_key=args.api_key or os.getenv("DEEPSEEK_API_KEY", ""),
                model=args.model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
                base_url=args.base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
                max_tokens=args.max_tokens,
                max_attempts=args.max_attempts,
            )
        write_csv(output, shots)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"Shot 时间线 CSV: {output}")
    return 0


def split_top_level_csv(line: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    for char in line:
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        if char == "," and bracket_depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def parse_time_values(raw: str) -> tuple[float, float, float]:
    match = re.fullmatch(r"\[\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]", raw.strip())
    if not match:
        raise ValueError(f"时间格式错误：{raw}")
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def parse_timeline_csv(path: Path) -> list[TimelineRow]:
    rows: list[TimelineRow] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line_number == 1 and line.startswith("index,"):
            continue
        parts = split_top_level_csv(line)
        if len(parts) != 3:
            raise ValueError(f"timeline 第 {line_number} 行应为 3 列：{line}")
        start_s, end_s, duration_s = parse_time_values(parts[2])
        rows.append(TimelineRow(
            index=int(parts[0]),
            text=parts[1].strip(),
            start_ms=round(start_s * 1000),
            end_ms=round(end_s * 1000),
            duration_ms=round(duration_s * 1000),
        ))
    if not rows:
        raise ValueError(f"timeline.csv 没有有效行：{path}")
    if len({row.index for row in rows}) != len(rows):
        raise ValueError("timeline.csv 的 index 不能重复")
    return rows


def build_user_prompt(wenan: str, timeline: list[TimelineRow]) -> str:
    lines = [
        "## 原始文案",
        wenan,
        "",
        "## 配音时间线",
        "| index | text | start_ms | end_ms | duration_ms |",
        "|---:|---|---:|---:|---:|",
    ]
    for row in timeline:
        lines.append(f"| {row.index} | {row.text} | {row.start_ms} | {row.end_ms} | {row.duration_ms} |")
    lines.extend([
        "",
        "只按语义逻辑把以上连续 index 分组，并为每组输出准确的 shot_title。不要设计任何画面内容或视觉参数。",
    ])
    return "\n".join(lines)


def generate_with_model(
    *, user_prompt: str, api_key: str, model: str, base_url: str, max_tokens: int,
    previous_output: str = "", validation_error: str = "",
) -> str:
    if not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
    if previous_output:
        messages.extend([
            {"role": "assistant", "content": previous_output},
            {"role": "user", "content": (
                f"上一版 CSV 未通过校验：{validation_error}\n"
                "请重新输出覆盖全部 timeline index 且每个 Shot 都有 shot_title 的完整 CSV。"
                "不要解释，不要增加视觉字段。"
            )},
        ])
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
    return response.choices[0].message.content or ""


def generate_validated_shots(
    *, timeline: list[TimelineRow], user_prompt: str, api_key: str,
    model: str, base_url: str, max_tokens: int, max_attempts: int,
) -> list[dict[str, str]]:
    if max_attempts < 1:
        raise ValueError("max_attempts 必须至少为 1")
    previous_output = ""
    validation_error = ""
    for attempt in range(1, max_attempts + 1):
        raw_output = generate_with_model(
            user_prompt=user_prompt,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            previous_output=previous_output,
            validation_error=validation_error,
        )
        try:
            return build_shots(parse_model_output(raw_output), timeline)
        except ValueError as exc:
            if attempt >= max_attempts:
                raise
            previous_output = raw_output
            validation_error = str(exc)
            print(f"第03步模型输出校验失败，正在要求模型修正（{attempt}/{max_attempts}）：{exc}", file=sys.stderr)
    raise RuntimeError("第03步模型输出校正流程异常结束")


def parse_model_output(text: str) -> list[dict[str, str]]:
    lines = strip_code_fence(text).splitlines()
    header = ",".join(MODEL_FIELDS)
    try:
        header_index = next(index for index, line in enumerate(lines) if line.strip() == header)
    except StopIteration as exc:
        raise ValueError("模型没有输出第03步 CSV 表头") from exc
    reader = csv.DictReader(lines[header_index:])
    if reader.fieldnames != MODEL_FIELDS:
        raise ValueError(f"第03步 CSV 列名不匹配：{reader.fieldnames}")
    rows = [{field: (row.get(field) or "").strip() for field in MODEL_FIELDS} for row in reader]
    if not rows:
        raise ValueError("模型没有输出任何 Shot")
    return rows


def strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def build_shots(groups: list[dict[str, str]], timeline: list[TimelineRow]) -> list[dict[str, str]]:
    positions = {row.index: position for position, row in enumerate(timeline)}
    expected_position = 0
    shots: list[dict[str, str]] = []
    for shot_number, group in enumerate(groups, start=1):
        start_raw = group.get("timeline_start_index", "")
        end_raw = group.get("timeline_end_index", "")
        shot_title = group.get("shot_title", "").strip()
        if not start_raw.isdigit() or not end_raw.isdigit():
            raise ValueError(f"Shot {shot_number} 的 timeline index 必须是整数")
        if not shot_title:
            raise ValueError(f"Shot {shot_number} 的 shot_title 不能为空")
        start_index, end_index = int(start_raw), int(end_raw)
        if start_index not in positions or end_index not in positions:
            raise ValueError(f"Shot {shot_number} 引用了不存在的 timeline index")
        start_position, end_position = positions[start_index], positions[end_index]
        if start_position != expected_position:
            raise ValueError(f"Shot {shot_number} 与上一 Shot 之间存在遗漏、重叠或顺序错误")
        if end_position < start_position:
            raise ValueError(f"Shot {shot_number} 的结束 index 早于开始 index")
        selected = timeline[start_position:end_position + 1]
        shots.append({
            "shot_id": str(shot_number),
            "分镜标题": shot_title,
            "开始时间ms": str(selected[0].start_ms),
            "结束时间ms": str(selected[-1].end_ms),
            "分镜对应原始文案内容": "".join(row.text for row in selected),
        })
        expected_position = end_position + 1
    if expected_position != len(timeline):
        raise ValueError("最后一个 Shot 没有覆盖 timeline 的全部句子")
    return shots


def generate_dry_run(timeline: list[TimelineRow]) -> list[dict[str, str]]:
    groups: list[dict[str, str]] = []
    position = 0
    while position < len(timeline):
        end_position = position
        duration = 0
        while end_position < len(timeline) and duration < 8000:
            duration += timeline[end_position].duration_ms
            end_position += 1
        selected = timeline[position:end_position]
        source_text = "".join(row.text for row in selected)
        groups.append({
            "shot_id": str(len(groups) + 1),
            "timeline_start_index": str(selected[0].index),
            "timeline_end_index": str(selected[-1].index),
            "shot_title": re.sub(r"\s+", "", source_text)[:16],
        })
        position = end_position
    return groups


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SHOT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
