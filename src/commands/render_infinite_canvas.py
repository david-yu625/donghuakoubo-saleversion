"""Render the optional Remotion infinite-canvas effect for one prepared project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "remotion_infinite_canvas"


def validate_project_state(project_dir: Path, *, manifest: bool = False) -> None:
    state_path = EXPERIMENT_ROOT / ("public/manifest.json" if manifest else "out/source.json")
    if not state_path.is_file():
        raise RuntimeError(f"缺少当前阶段输入：{state_path}，请先执行上一个 Stage")
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    expected = project_dir.expanduser().resolve()
    actual = Path(str(payload.get("projectDir", ""))).expanduser().resolve()
    if actual != expected:
        raise RuntimeError(
            f"实验目录当前属于主题项目 {actual}，不是 {expected}；请先为当前主题执行 07 准备素材"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path, help="主题的横版项目目录")
    parser.add_argument("--title", default="")
    parser.add_argument("--output", type=Path, required=True, help="最终 MP4 输出路径")
    parser.add_argument(
        "--stage",
        choices=("all", "prepare", "plan", "frames", "encode"),
        default="all",
        help="只执行一个无限画布阶段，默认执行全部阶段",
    )
    args = parser.parse_args()

    project_dir = args.project_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    package = EXPERIMENT_ROOT / "package.json"
    if not package.is_file():
        raise FileNotFoundError(f"无限画布实验目录不存在：{EXPERIMENT_ROOT}")
    if not (EXPERIMENT_ROOT / "node_modules").is_dir():
        raise RuntimeError(
            "无限画布依赖尚未安装，请先执行："
            f" cd {EXPERIMENT_ROOT} && npm install"
        )

    python = sys.executable
    prepare = [python, "prepare_assets.py", "--project-dir", str(project_dir), "--skip-manifest"]
    if args.title.strip():
        prepare.extend(["--title", args.title.strip()])
    if args.stage in {"all", "prepare"}:
        print(f"07 准备素材：{project_dir}", flush=True)
        subprocess.run(prepare, cwd=EXPERIMENT_ROOT, check=True)
    if args.stage in {"all", "plan"}:
        validate_project_state(project_dir)
        print("08 规划镜头和空间", flush=True)
        subprocess.run([python, "plan_scene.py"], cwd=EXPERIMENT_ROOT, check=True)
    if args.stage in {"all", "frames"}:
        validate_project_state(project_dir, manifest=True)
        print("09 生成动画画面帧", flush=True)
        subprocess.run(["npm", "run", "render:frames"], cwd=EXPERIMENT_ROOT, check=True)
    if args.stage in {"all", "encode"}:
        validate_project_state(project_dir, manifest=True)
        print("10 合成最终视频", flush=True)
        subprocess.run(
            [python, "encode.py", "--output", str(output)],
            cwd=EXPERIMENT_ROOT,
            check=True,
        )

    if args.stage == "all":
        print(f"无限画布成片：{output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
