from __future__ import annotations

import json
import re
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "scripted-canvas.mp4")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "public" / "manifest.json").read_text(encoding="utf-8"))
    frames_dir = ROOT / "out" / "frames"
    frame_count = max(1, round(float(manifest["durationSeconds"]) * 30))
    frame_width = len(str(frame_count - 1))
    frame_paths = sorted(
        (path for path in frames_dir.glob("element-*.jpeg") if re.fullmatch(rf"element-\d{{{frame_width}}}\.jpeg", path.name)),
        key=lambda path: int(path.stem.split("-")[-1]),
    )
    if len(frame_paths) < frame_count:
        raise FileNotFoundError(f"expected {frame_count} {frame_width}-digit Remotion frames, found {len(frame_paths)} in {frames_dir}")
    frame_list = ROOT / "out" / "frames.txt"
    frame_list.write_text("\n".join(f"file '{path.as_posix()}'" for path in frame_paths) + "\n", encoding="utf-8")
    audio = ROOT / "public" / "audio" / "narration.wav"
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(frame_list), "-i", str(audio), "-r", "30", "-frames:v", str(frame_count), "-t", f"{float(manifest['durationSeconds']):.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)], cwd=ROOT, check=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
