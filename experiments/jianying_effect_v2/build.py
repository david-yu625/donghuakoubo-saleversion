"""Build an isolated Jianying effect experiment from an existing project.

This module deliberately lives outside ``src``. It reads the project's existing
layout and assets, applies only experimental animation metadata, and writes the
draft under ``experiments/jianying_effect_v2/runs`` instead of the production
Jianying project folder.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from src.application.draft_builder import build_project_draft
from src.core.models import ElementLayout, LayoutResult
from src.env import load_env_file
from src.paths import default_draft_folder, safe_topic


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "jianying_effect_v2"
RUNS_ROOT = EXPERIMENT_ROOT / "runs"
ORIENTATION_DIR_NAMES = {"landscape", "portrait", "portrait_package"}


def _project_title(project_dir: Path) -> str:
    for filename in ("wenan.txt", "copy.txt"):
        path = project_dir / filename
        if path.is_file():
            first_line = path.read_text(encoding="utf-8-sig").splitlines()
            if first_line and first_line[0].strip():
                return first_line[0].strip()
    return project_dir.name


def _experiment_name(project_dir: Path) -> str:
    """Use the topic directory, not a shared orientation directory, as run id."""
    source = project_dir.parent.name if project_dir.name in ORIENTATION_DIR_NAMES else project_dir.name
    return safe_topic(source)


def _effect_layout(layout: LayoutResult) -> LayoutResult:
    """Return a copy with the v2 motion language, leaving source JSON untouched."""
    image_motions = ("push_in", "pan", "pull_out")
    image_enters = ("scale_in", "slide_left", "drop_bounce")
    text_enters = ("slide_up", "fade_scale", "slide_left")
    image_index = 0
    text_index = 0
    elements: list[ElementLayout] = []
    for element in layout.elements:
        metadata = dict(element.metadata)
        if element.element_type == "image":
            metadata["hold_motion"] = image_motions[image_index % len(image_motions)]
            metadata["experimental_effect"] = "v2_rhythm_focus"
            animation = replace(
                element.animation,
                enter=image_enters[image_index % len(image_enters)],
                enter_duration_ms=max(260, min(520, element.animation.enter_duration_ms + 80)),
            )
            image_index += 1
        else:
            metadata["experimental_effect"] = "v2_rhythm_focus"
            animation = replace(
                element.animation,
                enter=text_enters[text_index % len(text_enters)],
                enter_duration_ms=max(220, min(460, element.animation.enter_duration_ms + 60)),
            )
            text_index += 1
        elements.append(replace(element, animation=animation, metadata=metadata))
    return replace(
        layout,
        elements=elements,
        decisions=[*layout.decisions, "实验效果 v2：图片按镜头轮换推近/横移/拉远，文字采用节奏化分段入场"],
    )


def build_effect_v2(
    project_dir: Path,
    *,
    draft_name: str | None = None,
    replace_draft: bool = False,
    install_to_jianying: bool = False,
) -> tuple[Path, Path]:
    """Build and persist one isolated experimental draft.

    Returns ``(draft_path, experiment_layout_path)``.
    """
    project_dir = project_dir.expanduser().resolve()
    layout_path = project_dir / "layout_result.json"
    if not layout_path.is_file():
        raise FileNotFoundError(f"实验需要已完成第07步的布局文件：{layout_path}")
    layout = LayoutResult.from_dict(json.loads(layout_path.read_text(encoding="utf-8-sig")))
    effect_layout = _effect_layout(layout)

    run_name = _experiment_name(project_dir)
    run_root = RUNS_ROOT / run_name
    run_root.mkdir(parents=True, exist_ok=True)
    experiment_layout_path = run_root / "layout_result_effect_v2.json"
    experiment_layout_path.write_text(
        json.dumps(effect_layout.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_root / "source_project.txt").write_text(str(project_dir) + "\n", encoding="utf-8")

    name = draft_name or f"实验_v2_{run_name}"
    draft_folder = default_draft_folder() if install_to_jianying else run_root / "jianying_drafts"
    draft_path = build_project_draft(
        project_dir,
        layout=effect_layout,
        draft_folder=draft_folder,
        draft_name=name,
        project_title=_project_title(project_dir),
        replace=replace_draft,
    ).path
    return draft_path, experiment_layout_path


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path, help="已有 output/<主题>/landscape 或项目目录")
    parser.add_argument("--draft-name", default="", help="实验草稿名称")
    parser.add_argument("--replace", action="store_true", help="允许覆盖同名实验草稿")
    parser.add_argument(
        "--install-to-jianying",
        action="store_true",
        help="将独立实验草稿写入剪映草稿目录，便于在剪映首页查看",
    )
    args = parser.parse_args()
    draft_path, layout_path = build_effect_v2(
        args.project_dir,
        draft_name=args.draft_name.strip() or None,
        replace_draft=args.replace,
        install_to_jianying=args.install_to_jianying,
    )
    print(f"实验布局：{layout_path}")
    print(f"实验剪映草稿：{draft_path}")
    print("正式 src 流程未被修改，原项目素材为共享引用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
