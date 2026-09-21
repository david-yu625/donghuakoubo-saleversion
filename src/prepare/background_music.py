"""Prepare project-local background music from the configured source video."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


DEFAULT_BACKGROUND_MUSIC_SOURCE = Path("audio/bgm/bgm2[Sub Title].mp3")
BACKGROUND_MUSIC_NAME = "background_music.m4a"
BACKGROUND_MUSIC_SOURCE_META_NAME = "background_music.source.json"


def ensure_project_background_music(
    project_dir: Path,
    project_root: Path,
    *,
    source: Path | None = None,
) -> Path:
    source_path = _resolve_source(project_root, source or DEFAULT_BACKGROUND_MUSIC_SOURCE)
    if not source_path.exists():
        raise FileNotFoundError(f"背景音乐源文件不存在：{source_path}")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("生成背景音乐需要 ffmpeg")

    target = project_dir / "prepared_assets" / BACKGROUND_MUSIC_NAME
    source_metadata = target.with_name(BACKGROUND_MUSIC_SOURCE_META_NAME)
    if _is_current(target, source_path, source_metadata):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.tmp{target.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        copied = _run_ffmpeg(source_path, temporary, codec_args=("-c:a", "copy"))
        if copied.returncode != 0:
            temporary.unlink(missing_ok=True)
            encoded = _run_ffmpeg(source_path, temporary, codec_args=("-c:a", "aac", "-b:a", "192k"))
            if encoded.returncode != 0:
                detail = encoded.stderr.strip() or copied.stderr.strip() or "未知错误"
                raise RuntimeError(f"背景音乐提取失败：{detail}")
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError("背景音乐提取失败：输出文件为空")
        temporary.replace(target)
        source_metadata.write_text(
            json.dumps(_source_identity(source_path), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _resolve_source(project_root: Path, source: Path) -> Path:
    source = source.expanduser()
    return source.resolve() if source.is_absolute() else (project_root / source).resolve()


def _source_identity(source: Path) -> dict[str, str | int]:
    stat = source.stat()
    return {
        "path": str(source.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _is_current(target: Path, source: Path, source_metadata: Path) -> bool:
    if not target.exists() or target.stat().st_size == 0 or not source_metadata.exists():
        return False
    try:
        recorded_source = json.loads(source_metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return recorded_source == _source_identity(source)


def _run_ffmpeg(source: Path, target: Path, *, codec_args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            *codec_args,
            "-movflags",
            "+faststart",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
