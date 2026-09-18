"""Install the rendered sample as an isolated Jianying review draft."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.models import Canvas, LayoutResult
from src.paths import default_draft_folder
from src.renderers.jianying_renderer import JianyingRenderer


EXPERIMENT = Path(__file__).resolve().parent
OUT = EXPERIMENT / "out"
PUBLIC = EXPERIMENT / "public"
DEFAULT_DRAFT_NAME = "实验_Remotion无限画布_硬盘起源"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="覆盖同名实验草稿")
    parser.add_argument("--draft-name", default=DEFAULT_DRAFT_NAME)
    args = parser.parse_args()

    video = OUT / "infinite-canvas.mp4"
    if not video.is_file():
        raise FileNotFoundError(f"请先渲染样片：{video}")
    silent_video = OUT / "infinite-canvas-silent.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-an",
            "-c:v",
            "copy",
            str(silent_video),
        ],
        check=True,
    )
    result = LayoutResult(
        template="remotion_infinite_canvas",
        canvas=Canvas(width=1920, height=1080, safe_margin=64, top_reserved=0, bottom_reserved=0),
        elements=[],
        decisions=["实验 Remotion 无限知识画布成片"],
    )
    path = JianyingRenderer(project_root=PROJECT_ROOT).render(
        result,
        draft_folder=default_draft_folder(),
        draft_name=args.draft_name.strip() or DEFAULT_DRAFT_NAME,
        foreground_video=silent_video,
        audio_path=PUBLIC / "audio" / "narration.wav",
        include_sound_effects=False,
        extra_hold_ms=0,
        cover_image=OUT / "frame-230.png",
        replace=args.replace,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
