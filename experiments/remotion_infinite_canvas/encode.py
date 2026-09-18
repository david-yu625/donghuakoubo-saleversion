"""Encode Remotion's JPEG frame sequence and the prepared narration."""

from __future__ import annotations

import json
import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / "public" / "manifest.json").read_text(encoding="utf-8"))
duration = float(manifest["durationSeconds"])
# Remotion's sequence renderer pads frame numbers to four digits.
frames = ROOT / "out" / "frames" / "element-%04d.jpeg"
audio = ROOT / "public" / "audio" / "narration.wav"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "infinite-canvas.mp4")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "30",
            "-i",
            str(frames),
            "-i",
            str(audio),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(ROOT / "out" / "infinite-canvas.mp4"),
        ],
        cwd=ROOT,
        check=True,
    )
    rendered = ROOT / "out" / "infinite-canvas.mp4"
    if output != rendered:
        shutil.copy2(rendered, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
