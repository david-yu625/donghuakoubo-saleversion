#!/usr/bin/env python3
"""Step 04: turn Step 03 shots into image-generation prompt rows.

The input shot is treated as ``title|||narration``.  A shot produces one
background prompt containing the title and narration, plus at least two
separate visual-element prompts.  Step 05 may add model-specific styling, but
it must not have to reconstruct the storyboard semantics.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

from ..core.models import normalize_orientation
from ..env import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

CSV_FIELDS = ["element_id", "shot_id", "type", "role", "content", "start_ms", "end_ms"]
CONTENT_ROLES = {"background", "element"}
SHOT_FIELDS = ["shot_id", "分镜标题", "开始时间ms", "结束时间ms", "分镜对应原始文案内容"]

SYSTEM_PROMPT = """#目标
1. 按照我给你的每个分镜文案内容，生成后续工作流的文生图提示词。

#背景
1. 我是一名计算机资深从业者，硕士毕业，从事多年软件技术研发。
2. 现在想做抖音自媒体短视频。通过将科普知识以专业白板形式讲出来。
3. 每个分镜共有两部分元素组成，一部分元素以背景图的形式展示，另一部分以图片元素的形式插入。
4. 背景图的设计是以 Excalidraw 风格画面的形式展现，里面包含一些文字。
5. 背景图的最上面中间位置添加这个分镜的标题。
6. 文案相关内容在背景图中体现，就不需要在图片元素中体现。
7. 文案在图片元素中体现，就不要在背景元素中体现。

#要求
1. 生成每个分镜背景图的文生图提示词。
2. 生成每个分镜图片元素的提示词。
3. 只说明内容即可，图片的风格、分辨率都不需要指定。
4. 背景内容只需给出标题下的一句精简文字要点；标题、1920*1080 画布尺寸、纯白空白区域、留白规则和装饰线由程序自动补齐，模型不要重复输出这些机械内容。
5. 背景图只允许承载标题、少量精简文字要点、彩色装饰线和明确的空白区域；禁止绘制任何具体对象、设备、人物、图标、节点、连线、箭头、流程图、关系图或场景插图。
6. 分镜文案中的可见对象、动作、连接关系和结果，必须拆到 element 中；element 只说明图片中需要出现的具体内容，不要重复背景文字。
7. 每张 element 的信息不能重复，合起来才完整解释该分镜。
8. 禁止生成空白节点框、空白卡片、只有方块和箭头的抽象占位图、没有业务含义的通用流程图。节点、卡片、箭头只能作为承载具体内容的组成部分，必须看得出它表示什么输入、处理或结果。
9. element 的主体必须完整、清晰地占据画面大部分，四周仅保留少量纯白边；不要画大面积空白外框，不要把核心对象缩成很小的图标。除非文案必须出现极短标签，否则不放文字。

#初始化
1. 请开始你的表演，做得好我会给你奖励。

#输出格式
1. 不要输出 CSV、JSON、Markdown、代码块或解释。程序会自动生成 CSV、element_id、shot_id、type、role 和时间。
2. 严格按输入标题顺序逐段输出，每段使用以下纯文本结构；每条内容必须单独占一行：
【标题1】
背景图：标题下的一句精简文字要点
元素图：第一个具体可视化步骤
元素图：第二个具体可视化步骤
3. 每个标题段必须恰好 1 条“背景图：”和至少 2 条“元素图：”。优先用两张完整、信息密度高且不重复的图讲清知识点；内容复杂时可增加元素图。不要自行添加其他字段、编号或时间。""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成第04步背景和图片元素文生图提示词")
    parser.add_argument("shot_csv", type=Path)
    parser.add_argument("--prompt-output", type=Path)
    parser.add_argument("--request-output", type=Path)
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--max-tokens", type=int, default=10000)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--orientation", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(PROJECT_ROOT / ".env")
        shot_csv = args.shot_csv.expanduser().resolve()
        output = args.prompt_output.expanduser().resolve() if args.prompt_output else shot_csv.with_name("storyboard_prompts.csv")
        shots = read_shots(shot_csv)
        system_prompt = system_prompt_for_orientation(args.orientation)
        user_prompt = build_user_prompt(shots, args.orientation)
        if args.request_output:
            request_path = args.request_output.expanduser().resolve()
            request_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_text(f"System:\n{system_prompt}\n\nUser:\n{user_prompt}", encoding="utf-8")
        if args.dry_run:
            rows = prepare_rows_from_content_plans(generate_dry_run(shots), shots)
        else:
            rows = generate_validated_rows(
                shots=shots,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=args.api_key or os.getenv("DEEPSEEK_API_KEY", ""),
                model=args.model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
                base_url=args.base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
                max_tokens=args.max_tokens,
                max_attempts=args.max_attempts,
            )
        write_csv(output, rows)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(f"分镜提示词 CSV: {output}")
    return 0


def read_shots(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != SHOT_FIELDS:
            raise ValueError(f"Shot CSV 列名不匹配：{reader.fieldnames}")
        rows = [{field: (row.get(field) or "").strip() for field in SHOT_FIELDS} for row in reader]
    if not rows:
        raise ValueError(f"Shot CSV 没有有效行：{path}")
    _shot_map(rows)
    return rows


def split_title_content(shot: dict[str, str]) -> tuple[str, str]:
    """Return the canonical ``title|||narration`` pair used by the prompt."""
    title = shot["分镜标题"].strip()
    narration = shot["分镜对应原始文案内容"].strip()
    return title, narration


def build_user_prompt(shots: list[dict[str, str]], orientation: str = "") -> str:
    direction = "横屏" if normalize_orientation(orientation) == "landscape" else "竖屏"
    lines = [
        "#输入",
        "以下内容来自第03步。标题和分镜内容使用 ||| 隔开：",
    ]
    for index, shot in enumerate(shots, start=1):
        title, narration = split_title_content(shot)
        lines.append(f"标题{index}：{title}|||{narration}")
    lines.extend([
        "",
        "#画布方向",
        direction,
        "",
        "#说明",
        "只生成图片内容。CSV 字段、元素编号和时间由程序读取第03步数据后自动填写。",
    ])
    return "\n".join(lines)


def system_prompt_for_orientation(orientation: str = "") -> str:
    del orientation
    return SYSTEM_PROMPT


def generate_with_model(*, system_prompt: str, user_prompt: str, api_key: str, model: str,
                        base_url: str, max_tokens: int, previous_output: str = "",
                        validation_error: str = "") -> str:
    if not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    if previous_output:
        messages.extend([
            {"role": "assistant", "content": previous_output},
            {"role": "user", "content": build_correction_prompt(validation_error)},
        ])
    response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def generate_validated_rows(*, shots: list[dict[str, str]], system_prompt: str, user_prompt: str,
                            api_key: str, model: str, base_url: str, max_tokens: int,
                            max_attempts: int) -> list[dict[str, str]]:
    if max_attempts < 1:
        raise ValueError("max_attempts 必须至少为 1")
    previous_output = ""
    validation_error = ""
    for attempt in range(1, max_attempts + 1):
        raw = generate_with_model(system_prompt=system_prompt, user_prompt=user_prompt, api_key=api_key,
                                  model=model, base_url=base_url, max_tokens=max_tokens,
                                  previous_output=previous_output, validation_error=validation_error)
        try:
            return prepare_rows_from_content_plans(parse_model_content(raw, shots), shots)
        except ValueError as exc:
            if attempt >= max_attempts:
                raise
            previous_output, validation_error = raw, str(exc)
            print(f"第04步输出校验失败，要求模型修正（{attempt}/{max_attempts}）：{exc}", file=sys.stderr)
    raise RuntimeError("第04步输出校正流程异常结束")


def build_correction_prompt(error: str) -> str:
    return (f"上一版图片内容未通过校验，错误：{error}\n请重新输出覆盖所有标题段的图片内容。"
            "每个标题段必须有 1 条“背景图：”和至少 2 条“元素图：”；优先用两张完整且不重复的图讲清知识点，内容复杂时可增加元素图，背景只写精简文字要点，"
            "每条 element 必须表达一个不重复的具体知识步骤，主体占画面大部分；"
            "禁止空节点、空卡片和只有方块箭头的抽象占位图。不要输出 CSV、JSON、Markdown 或代码块。")


def parse_model_content(text: str, shots: list[dict[str, str]]) -> list[dict[str, object]]:
    """Parse only semantic image content; Python owns all CSV mechanics."""
    normalized = strip_code_fence(text)
    expected_headers = [f"【标题{index}】" for index in range(1, len(shots) + 1)]
    plans: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line_no, raw_line in enumerate(normalized.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line in expected_headers:
            if current is not None:
                plans.append(current)
            current = {"header": line, "background": "", "elements": []}
            continue
        if current is None:
            raise ValueError(f"第{line_no}行必须以标题段“【标题N】”开始")
        if line.startswith("背景图："):
            if current["background"]:
                raise ValueError(f"{current['header']} 有多条背景图内容")
            current["background"] = line.removeprefix("背景图：").strip()
            continue
        if line.startswith("元素图："):
            elements = current["elements"]
            assert isinstance(elements, list)
            elements.append(line.removeprefix("元素图：").strip())
            continue
        raise ValueError(f"第{line_no}行不是“背景图：”或“元素图：”内容")
    if current is not None:
        plans.append(current)
    headers = [str(plan["header"]) for plan in plans]
    if headers != expected_headers:
        raise ValueError(f"标题段不完整或顺序错误，应为：{'、'.join(expected_headers)}")
    for plan in plans:
        if not str(plan["background"]).strip():
            raise ValueError(f"{plan['header']} 缺少背景图内容")
        elements = plan["elements"]
        assert isinstance(elements, list)
        if len(elements) < 2:
            raise ValueError(f"{plan['header']} 至少需要 2 条元素图内容")
        if any(not str(item).strip() for item in elements):
            raise ValueError(f"{plan['header']} 存在空元素图内容")
    return plans


def strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def prepare_rows_from_content_plans(plans: list[dict[str, object]], shots: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(plans) != len(shots):
        raise ValueError("图片内容标题段数量与 Shot 数量不一致")
    prepared: list[dict[str, str]] = []
    for shot, plan in zip(shots, plans, strict=True):
        background = {
            "element_id": f"s{shot['shot_id']}_bg01",
            "shot_id": shot["shot_id"],
            "type": "image",
            "role": "background",
            "content": compose_background_content(shot["分镜标题"], str(plan["background"])),
            "start_ms": shot["开始时间ms"],
            "end_ms": shot["结束时间ms"],
        }
        prepared.append(background)
        elements = plan["elements"]
        assert isinstance(elements, list)
        for i, description in enumerate(elements, 1):
            item = {
                "element_id": f"s{shot['shot_id']}_img{i:02d}",
                "shot_id": shot["shot_id"],
                "type": "image",
                "role": "element",
                "content": compose_element_content(str(description)),
                "start_ms": shot["开始时间ms"],
                "end_ms": shot["结束时间ms"],
            }
            prepared.append(item)
    validate_rows(prepared, shots)
    return normalize_progressive_timing(prepared, shots)


def compose_background_content(title: str, summary: str) -> str:
    return (
        f"1920*1080 白板背景，顶部中间显示标题“{title}”，标题下只放精简短句“{summary}”；"
        "使用少量彩色装饰线分隔标题区；禁止具体插图/对象、设备、人物、图标、节点、连线、箭头、"
        "流程图、关系图和场景插图；下方和右侧保留纯白空白区域。"
    )


def compose_element_content(description: str) -> str:
    return (
        f"{description}；主体完整清晰地占据画面大部分，四周仅留少量白边，不出现长文字。"
    )


def _shot_map(shots: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for shot in shots:
        shot_id = shot.get("shot_id", "")
        if not shot_id or shot_id in result:
            raise ValueError(f"Shot ID 为空或重复：{shot_id}")
        start, end = _parse_range(shot.get("开始时间ms", ""), shot.get("结束时间ms", ""), f"Shot {shot_id}")
        if end <= start:
            raise ValueError(f"Shot {shot_id} 时间无效")
        if not shot.get("分镜标题", "").strip() or not shot.get("分镜对应原始文案内容", "").strip():
            raise ValueError(f"Shot {shot_id} 标题或文案为空")
        result[shot_id] = shot
    return result


def _validate_row(row: dict[str, str], shot: dict[str, str]) -> None:
    if row.get("type") != "image":
        raise ValueError(f"元素 {row.get('element_id')} type 必须为 image")
    if row.get("role") not in CONTENT_ROLES:
        raise ValueError(f"元素 {row.get('element_id')} role 不合法：{row.get('role')}")
    content = row.get("content", "").strip()
    if not content:
        raise ValueError(f"元素 {row.get('element_id')} content 不能为空")
    if len(re.sub(r"\s+", "", content)) < 12:
        raise ValueError(f"元素 {row.get('element_id')} 提示词过短")
    start, end = _parse_range(row.get("start_ms", ""), row.get("end_ms", ""), f"元素 {row.get('element_id')}")
    shot_start, shot_end = _parse_range(shot["开始时间ms"], shot["结束时间ms"], f"Shot {shot['shot_id']}")
    if not shot_start <= start < end <= shot_end:
        raise ValueError(f"元素 {row.get('element_id')} 超出 Shot {shot['shot_id']} 时间范围")
    title, narration = split_title_content(shot)
    if row["role"] == "background":
        if title not in content:
            raise ValueError(f"背景必须原样包含 Shot {shot['shot_id']} 的标题")
        if not re.search(r"1920\s*[x×*]\s*1080", content):
            raise ValueError("背景提示词必须说明 1920*1080 画布")
        forbidden = (
            "具体对象", "具体插图", "设备", "人物", "图标", "节点", "连线",
            "箭头", "流程图", "关系图", "场景插图", "纯白空白区域",
        )
        if not any(marker in content for marker in forbidden):
            raise ValueError(
                f"背景 Shot {shot['shot_id']} 必须明确禁止具体插图/对象并保留纯白空白区域"
            )
    else:
        if _contains_long_text(content) or title in content:
            raise ValueError(f"元素 {row.get('element_id')} 不应重复标题、文案或长段文字")


def _contains_long_text(content: str) -> bool:
    return bool(re.search(r"(?:完整文字|大段文字|完整文案|长句字幕)", content))


def _parse_range(start_raw: str, end_raw: str, label: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d+", str(start_raw)) or not re.fullmatch(r"\d+", str(end_raw)):
        raise ValueError(f"{label} 时间必须是整数毫秒")
    return int(start_raw), int(end_raw)


def validate_rows(rows: list[dict[str, str]], shots: list[dict[str, str]]) -> None:
    shot_map = _shot_map(shots)
    seen: set[str] = set()
    groups: dict[str, list[dict[str, str]]] = {key: [] for key in shot_map}
    for row in rows:
        if row["element_id"] in seen:
            raise ValueError(f"element_id 重复：{row['element_id']}")
        seen.add(row["element_id"])
        if row["shot_id"] not in shot_map:
            raise ValueError(f"元素所属 Shot 不存在：{row['shot_id']}")
        _validate_row(row, shot_map[row["shot_id"]])
        groups[row["shot_id"]].append(row)
    for shot_id, shot_rows in groups.items():
        if len([r for r in shot_rows if r["role"] == "background"]) != 1:
            raise ValueError(f"Shot {shot_id} 必须有且仅有一条 background")
        if len([r for r in shot_rows if r["role"] == "element"]) < 2:
            raise ValueError(f"Shot {shot_id} 至少需要 2 张元素图")


def normalize_progressive_timing(rows: list[dict[str, str]], shots: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = [dict(row) for row in rows]
    shot_map = _shot_map(shots)
    for shot_id, shot in shot_map.items():
        elements = [r for r in normalized if r["shot_id"] == shot_id and r["role"] == "element"]
        if not elements:
            continue
        start, end = int(shot["开始时间ms"]), int(shot["结束时间ms"])
        for row in elements:
            row["end_ms"] = str(end)
        if all(row["start_ms"] == str(start) for row in elements):
            duration = end - start
            divisor = len(elements) + 1
            for index, row in enumerate(sorted(elements, key=lambda item: item.get("element_id", ""))):
                row["start_ms"] = str(start + round(duration * index / divisor))
    return normalized


def generate_dry_run(shots: list[dict[str, str]]) -> list[dict[str, object]]:
    """Return semantic plans in the same shape as the model, for offline verification."""
    plans: list[dict[str, object]] = []
    for index, shot in enumerate(shots, start=1):
        title, narration = split_title_content(shot)
        plans.append({
            "header": f"【标题{index}】",
            "background": f"{title}的核心要点：{narration}",
            "elements": [
                "文案中第一个具体输入、对象或前提条件，展示其可见外观",
                "文案中发生的明确处理动作或因果关系，展示参与对象和实际变化",
                "文案中可见的最终结果或完整关系，展示结果如何产生",
            ],
        })
    return plans


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
