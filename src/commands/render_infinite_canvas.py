"""Render the latest scripted Remotion infinite-canvas effect for one project."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "remotion_scripted"


def validate_project_state(project_dir: Path, *, manifest: bool = False) -> None:
    state_path = EXPERIMENT_ROOT / ("public/manifest.json" if manifest else "out/source.json")
    if not state_path.is_file():
        raise RuntimeError(f"missing current Remotion stage input: {state_path}; run the previous stage first")
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    expected = project_dir.expanduser().resolve()
    actual = Path(str(payload.get("projectDir", ""))).expanduser().resolve()
    if actual != expected:
        raise RuntimeError(f"Remotion stage belongs to {actual}, not {expected}; prepare the current project first")


def remotion_voice_paths(project_dir: Path) -> tuple[Path, Path]:
    """Return the isolated Remotion voice artifacts for one prepared project."""
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", project_dir.name).strip("_") or "project"
    voice_dir = EXPERIMENT_ROOT / "out" / "voice" / slug
    return voice_dir / "narration.wav", voice_dir / "timeline.csv"


def prepare_remotion_voice(project_dir: Path) -> tuple[Path, Path]:
    """Copy the Jianying narration contract into the isolated Remotion run."""
    narration, timeline = remotion_voice_paths(project_dir)
    marker = narration.parent / "mode.json"
    source_narration = project_dir / "narration.wav"
    source_timeline = project_dir / "timeline.csv"
    desired_mode = "jianying-audio-contract-copy-v1"
    current_mode = ""
    if marker.is_file():
        try:
            current_mode = str(json.loads(marker.read_text(encoding="utf-8")).get("mode", ""))
        except (OSError, ValueError, TypeError):
            current_mode = ""
    if not narration.is_file() or not timeline.is_file() or current_mode != desired_mode:
        narration.parent.mkdir(parents=True, exist_ok=True)
        if not source_narration.is_file() or not source_timeline.is_file():
            raise FileNotFoundError(f"Jianying audio contract is incomplete in {project_dir}")
        print("Remotion voice: copy Jianying narration and sentence timeline", flush=True)
        shutil.copy2(source_narration, narration)
        shutil.copy2(source_timeline, timeline)
        marker.write_text(json.dumps({"mode": desired_mode}, ensure_ascii=False, indent=2), encoding="utf-8")
    return narration, timeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path, help="prepared landscape project directory")
    parser.add_argument("--title", default="")
    parser.add_argument("--output", type=Path, required=True, help="final MP4 output path")
    parser.add_argument("--stage", choices=("all", "prepare", "plan", "frames", "encode"), default="all")
    args = parser.parse_args()

    project_dir = args.project_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not (EXPERIMENT_ROOT / "package.json").is_file():
        raise FileNotFoundError(f"scripted Remotion project is missing: {EXPERIMENT_ROOT}")
    if not (EXPERIMENT_ROOT / "node_modules").is_dir():
        raise RuntimeError(f"Remotion dependencies are not installed; run npm install in {EXPERIMENT_ROOT}")

    python = sys.executable
    title_args = ["--title", args.title.strip()] if args.title.strip() else []
    narration_path = timeline_path = None
    if args.stage in {"all", "prepare", "plan"}:
        narration_path, timeline_path = prepare_remotion_voice(project_dir)
    prepare = [
        python,
        "scripts/build_from_project.py",
        "--project-dir",
        str(project_dir),
    ]
    if narration_path and timeline_path:
        prepare.extend(["--narration-path", str(narration_path), "--timeline-path", str(timeline_path)])
    prepare.extend(title_args)
    if args.stage in {"all", "prepare", "plan"}:
        print(f"07/08 prepare latest Remotion inputs: {project_dir}", flush=True)
        subprocess.run(prepare, cwd=EXPERIMENT_ROOT, check=True)
    if args.stage in {"all", "frames"}:
        validate_project_state(project_dir, manifest=True)
        print("09 render latest infinite canvas frames", flush=True)
        subprocess.run(["npm.cmd", "run", "render:frames"], cwd=EXPERIMENT_ROOT, check=True)
    if args.stage in {"all", "encode"}:
        validate_project_state(project_dir, manifest=True)
        print("10 encode latest infinite canvas video", flush=True)
        subprocess.run([python, "scripts/encode.py", "--output", str(output)], cwd=EXPERIMENT_ROOT, check=True)
    if args.stage == "all":
        print(f"latest Remotion infinite canvas: {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
