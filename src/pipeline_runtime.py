"""Shared runtime for the PySide6 pipeline application."""

from __future__ import annotations

import csv
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .core.models import orientation_key
from .paths import default_draft_folder, resolve_draft_folder
from .prepare.image_generation import (
    DEFAULT_IMAGE_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    IMAGE_MODEL_CHOICES,
    is_valid_image_file,
)
from .prepare.voice_timeline import DEFAULT_TTS_SPEAKER
from .prepare.topic_generation import record_topic
from .settings import (
    DEFAULT_SUBTITLE_BACKGROUND_COLOR,
    DEFAULT_SUBTITLE_COLOR,
    DEFAULT_SUBTITLE_FONT,
    DEFAULT_TITLE_BACKGROUND_COLOR,
    DEFAULT_TITLE_COLOR,
    DEFAULT_TITLE_FONT,
    DEFAULT_VISUAL_THEME,
    VISUAL_THEME_CHOICES,
    default_background_image,
    resolve_visual_theme,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_DRAFT_FOLDER = default_draft_folder()


def find_default_bgm_path() -> Path:
    bgm_dir = PROJECT_ROOT / "audio" / "bgm"
    configured = bgm_dir / "bgm1.mp4"
    if configured.is_file():
        return configured
    candidates = sorted(
        (
            path
            for path in bgm_dir.glob("*")
            if path.is_file() and path.suffix.lower() in {".mp3", ".mp4"}
        ),
        key=lambda path: path.name,
    )
    return candidates[0] if candidates else configured


DEFAULT_BGM_PATH = find_default_bgm_path()


def resolve_project_file_path(value: str, default: Path) -> Path:
    raw = value.strip()
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate
    if not candidate.is_absolute():
        project_candidate = PROJECT_ROOT / candidate
        if project_candidate.is_file():
            return project_candidate

    parts = [part for part in candidate.parts if part not in (candidate.anchor, "\\", "/")]
    for depth in range(min(5, len(parts)), 1, -1):
        relocated = PROJECT_ROOT.joinpath(*parts[-depth:])
        if relocated.is_file():
            return relocated
    return candidate


API_FIELDS = [
    ("DeepSeek API Key", "DEEPSEEK_API_KEY", True),
    ("豆包 TTS Access Key", "DOUBAO_TTS_ACCESS_KEY", True),
    ("火山引擎 Access Key", "VOLC_ACCESSKEY", True),
    ("火山引擎 Secret Key", "VOLC_SECRETKEY", True),
    ("图片 API Key", "IMAGE_API_KEY", True),
    ("图片 API 地址", "IMAGE_BASE_URL", False),
    ("图片模型", "IMAGE_MODEL", False),
    ("图片质量", "IMAGE_QUALITY", False),
    ("豆包 TTS 音色 ID", "DOUBAO_TTS_SPEAKER", False),
]
API_DEFAULTS = {
    "IMAGE_MODEL": DEFAULT_IMAGE_MODEL,
    "IMAGE_BASE_URL": DEFAULT_IMAGE_BASE_URL,
    "IMAGE_QUALITY": "low",
    "DOUBAO_TTS_SPEAKER": DEFAULT_TTS_SPEAKER,
}
IMAGE_QUALITY_CHOICES = ("low", "medium", "high")
VIDEO_ORIENTATION_CHOICES = ("竖屏", "横屏")
SETTING_FIELDS = [
    ("视觉主题", "VISUAL_THEME", resolve_visual_theme(DEFAULT_VISUAL_THEME).label),
    ("标题字体", "TITLE_FONT", DEFAULT_TITLE_FONT),
    ("标题颜色", "TITLE_COLOR", DEFAULT_TITLE_COLOR),
    ("标题背景颜色", "TITLE_BACKGROUND_COLOR", DEFAULT_TITLE_BACKGROUND_COLOR),
    ("字幕字体", "SUBTITLE_FONT", DEFAULT_SUBTITLE_FONT),
    ("字幕颜色", "SUBTITLE_COLOR", DEFAULT_SUBTITLE_COLOR),
    ("字幕背景颜色", "SUBTITLE_BACKGROUND_COLOR", DEFAULT_SUBTITLE_BACKGROUND_COLOR),
    (
        "背景图片",
        "BACKGROUND_IMAGE",
        str(default_background_image(PROJECT_ROOT, DEFAULT_VISUAL_THEME)),
    ),
    ("草稿目录", "DRAFT_FOLDER", str(DEFAULT_DRAFT_FOLDER)),
    ("背景音乐", "BACKGROUND_MUSIC", str(DEFAULT_BGM_PATH)),
]
TITLE_FONT_CHOICES = (
    "雅酷黑简",
    "ResourceHanRoundedCN_Bold",
    "ResourceHanRoundedCN_Md",
    "得意黑",
    "Aa动员宋",
)
SUBTITLE_FONT_CHOICES = (
    "未光体",
    "ResourceHanRoundedCN_Nl",
    "今宋体",
    "芋圆体",
    "仓耳舒圆体W02",
)
TTS_VOICE_DOC_URL = "https://docs.volcengine.com/docs/6561/1257544?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8"

STEP_DEFS = [
    ("copy", "01 文案", "wenan.txt", "生成内容文案", "查看并修改文案"),
    ("voice", "02 配音", "narration.wav", "生成配音", "查看配音"),
    ("shots", "03 分镜", "shot_timeline_source_time.csv", "划分语义分镜", "查看分镜"),
    ("storyboard_prompts", "04 图片内容", "storyboard_prompts.csv", "扩展图片内容", "查看图片内容"),
    ("prompts", "05 生图提示词", "image_prompts_plus.csv", "生成生图提示词", "查看生图提示词"),
    ("images", "06 图片", "generated_assets_plus", "重新生成图片", "查看并修改图片"),
    ("layout", "07 布局", "layout_result.json", "编译画面布局", ""),
    ("draft", "08 草稿", "", "生成剪映草稿", ""),
]
STEP_BUTTON_DESCRIPTIONS = {
    "layout": (
        "读取现有文案时间线、分镜、图片和字幕\n"
        "重新计算图片尺寸、元素位置、关键词排布及动态重排"
    ),
}


@dataclass(frozen=True)
class Options:
    topic: str
    story_world: str
    target_chars: str
    image_model: str = DEFAULT_IMAGE_MODEL
    visual_theme: str = resolve_visual_theme(DEFAULT_VISUAL_THEME).label
    orientation: str = "竖屏"
    run_copy: bool = True
    run_voice: bool = True
    run_shots: bool = True
    run_storyboard_prompts: bool = True
    run_prompts: bool = True
    run_images: bool = True
    overwrite_images: bool = False
    run_layout: bool = True
    run_draft: bool = True
    draft_name: str = ""
    draft_folder: str = ""
    include_background_music: bool = True
    background_music: str = ""
    background_image: str = ""
    include_background: bool = True
    include_title: bool = True
    include_subtitles: bool = True


class Runner:
    def __init__(self, events: queue.Queue[tuple[str, str]]) -> None:
        self.events = events
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self._stop_requested = threading.Event()

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, options: Options) -> None:
        if self.running:
            raise RuntimeError("正在运行")
        self._stop_requested.clear()
        self.thread = threading.Thread(target=self._run, args=(options,), daemon=True)
        self.thread.start()

    def start_batch(self, options: list[Options]) -> None:
        if self.running:
            raise RuntimeError("正在运行")
        if not options:
            raise ValueError("批量主题不能为空")
        self._stop_requested.clear()
        self.thread = threading.Thread(target=self._run_batch, args=(options,), daemon=True)
        self.thread.start()

    def start_commands(
        self,
        commands: list[tuple[str, list[str]]],
        output_dir: Path,
    ) -> None:
        if self.running:
            raise RuntimeError("正在运行")
        self._stop_requested.clear()
        self.thread = threading.Thread(
            target=self._run_commands,
            args=(commands, output_dir),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def emit(self, kind: str, text: str) -> None:
        self.events.put((kind, text))

    def log(self, text: str = "") -> None:
        self.emit("log", f"[{time.strftime('%H:%M:%S')}] {text}")

    def _run(self, options: Options) -> None:
        try:
            record_topic(options.topic, status="used")
            commands, output_dir = build_commands(options)
            self._execute_commands(commands, output_dir)
        except Exception as exc:
            if self._stop_requested.is_set():
                self.log("任务已停止")
                self.emit("status", "已停止")
            else:
                self.log(f"错误：{exc}")
                self.emit("status", "失败")
        finally:
            self.process = None

    def _run_batch(self, options: list[Options]) -> None:
        total = len(options)
        succeeded = 0
        failed = 0
        self.emit("status", "运行中")
        self.log(f"批量任务开始，共 {total} 个主题")
        try:
            for index, item in enumerate(options, start=1):
                if self._stop_requested.is_set():
                    break
                self.emit("batch_progress", f"{index}/{total} {item.topic}")
                self.log(f"[{index}/{total}] 开始主题：{item.topic}")
                try:
                    record_topic(item.topic, status="used")
                    commands, output_dir = build_commands(item)
                    self._execute_commands(commands, output_dir, emit_lifecycle=False)
                except Exception as exc:
                    if self._stop_requested.is_set():
                        break
                    failed += 1
                    self.log(f"[{index}/{total}] 主题失败：{item.topic}：{exc}")
                    continue
                succeeded += 1
                self.log(f"[{index}/{total}] 主题完成：{item.topic}")

            completed = succeeded + failed
            if self._stop_requested.is_set():
                self.log(f"批量任务已停止，已处理 {completed}/{total} 个主题")
                self.emit("batch_progress", f"已停止 {completed}/{total}")
                self.emit("status", "已停止")
            else:
                self.log(f"批量任务完成：成功 {succeeded}，失败 {failed}")
                self.emit("batch_progress", f"成功 {succeeded}，失败 {failed}")
                self.emit("status", "完成" if failed == 0 else "部分失败")
        finally:
            self.process = None

    def _run_commands(
        self,
        commands: list[tuple[str, list[str]]],
        output_dir: Path,
    ) -> None:
        try:
            self._execute_commands(commands, output_dir)
        except Exception as exc:
            if self._stop_requested.is_set():
                self.log("任务已停止")
                self.emit("status", "已停止")
            else:
                self.log(f"错误：{exc}")
                self.emit("status", "失败")
        finally:
            self.process = None

    def _execute_commands(
        self,
        commands: list[tuple[str, list[str]]],
        output_dir: Path,
        *,
        emit_lifecycle: bool = True,
    ) -> None:
        env = build_child_env()
        output_dir.mkdir(parents=True, exist_ok=True)
        if emit_lifecycle:
            self.emit("status", "运行中")
        self.log(f"输出目录：{output_dir}")
        for label, command in commands:
            if self._stop_requested.is_set():
                raise RuntimeError("任务已停止")
            self.run_command(label, command, env)
        if emit_lifecycle:
            self.log("全部完成")
            self.emit("status", "完成")

    def run_command(self, label: str, command: list[str], env: dict[str, str]) -> None:
        self.log(f"开始：{label}")
        self.process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.log(line.rstrip())
        code = self.process.wait()
        if code != 0:
            raise subprocess.CalledProcessError(code, command)
        self.log(f"完成：{label}")


def safe_topic(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', "", value.strip())
    return name or "未命名"


def draft_name_for_orientation(name: str, orientation: str = "") -> str:
    """Make Jianying draft names unique across portrait and landscape renders."""
    base = name.strip() or "src"
    suffix = f"_{orientation_key(orientation)}"
    return base if base.casefold().endswith(suffix) else f"{base}{suffix}"


def parse_batch_topics(value: str) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        topic = line.strip()
        if not topic or topic in seen:
            continue
        seen.add(topic)
        topics.append(topic)
    return topics


def build_batch_options(base: Options, topics: list[str], *, batch_id: str) -> list[Options]:
    return [
        replace(
            base,
            topic=topic,
            draft_name=f"{safe_topic(topic)}_{batch_id}",
        )
        for topic in topics
    ]


def save_copywriting_text(path: Path, content: str) -> Path:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not normalized.strip():
        raise ValueError("文案不能为空")
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(normalized + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _is_current(output: Path, *inputs: Path) -> bool:
    if not output.is_file():
        return False
    try:
        output_time = output.stat().st_mtime_ns
        return all(source.is_file() and output_time >= source.stat().st_mtime_ns for source in inputs)
    except OSError:
        return False


def _images_complete(prompt_csv: Path) -> bool:
    if not prompt_csv.is_file():
        return False
    try:
        with prompt_csv.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    except (OSError, csv.Error):
        return False
    if not rows:
        return False
    prompt_time = prompt_csv.stat().st_mtime_ns
    for row in rows:
        raw_path = str(row.get("asset_path", "")).strip()
        if not raw_path:
            return False
        asset = Path(raw_path).expanduser()
        if not asset.is_absolute():
            asset = PROJECT_ROOT / asset
        try:
            if not is_valid_image_file(asset) or asset.stat().st_mtime_ns < prompt_time:
                return False
        except OSError:
            return False
    return True


def reuse_completed_materials(options: Options, *, output_root: Path = OUTPUT_ROOT) -> Options:
    """Skip completed 01-06 work while preserving dependency consistency."""
    topic_dir = output_root / safe_topic(options.topic) / orientation_key(options.orientation)
    wenan = topic_dir / "wenan.txt"
    timeline = topic_dir / "timeline.csv"
    narration = topic_dir / "narration.wav"
    shot_csv = topic_dir / "shot_timeline_source_time.csv"
    storyboard_csv = topic_dir / "storyboard_prompts.csv"
    prompt_csv = topic_dir / "image_prompts_plus.csv"
    element_csv = topic_dir / "element_timeline_with_assets.csv"

    complete = (
        wenan.is_file(),
        _is_current(narration, wenan) and _is_current(timeline, wenan),
        _is_current(shot_csv, wenan, timeline),
        _is_current(storyboard_csv, shot_csv),
        _is_current(prompt_csv, storyboard_csv) and _is_current(element_csv, storyboard_csv),
        _images_complete(prompt_csv),
    )
    try:
        first_incomplete = complete.index(False)
    except ValueError:
        first_incomplete = len(complete)

    requested = (
        options.run_copy,
        options.run_voice,
        options.run_shots,
        options.run_storyboard_prompts,
        options.run_prompts,
        options.run_images,
    )
    planned = tuple(enabled and index >= first_incomplete for index, enabled in enumerate(requested))
    return replace(
        options,
        run_copy=planned[0],
        run_voice=planned[1],
        run_shots=planned[2],
        run_storyboard_prompts=planned[3],
        run_prompts=planned[4],
        run_images=planned[5],
        overwrite_images=options.overwrite_images or (first_incomplete <= 4 and planned[5]),
    )


def build_child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def update_env_file(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    pending = dict(values)
    updated: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                updated.append(f"{key}={pending.pop(key)}")
                continue
        updated.append(line)
    if pending and updated and updated[-1] != "":
        updated.append("")
    updated.extend(f"{key}={value}" for key, value in pending.items())
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def build_commands(options: Options) -> tuple[list[tuple[str, list[str]]], Path]:
    py = sys.executable
    topic = options.topic.strip()
    if not topic:
        raise ValueError("主题不能为空")
    target_chars = options.target_chars.strip() or "0"
    if not target_chars.isdigit():
        raise ValueError("最长字数必须是非负整数")
    draft_folder = str(resolve_draft_folder(options.draft_folder))
    topic_dir = OUTPUT_ROOT / safe_topic(topic) / orientation_key(options.orientation)
    wenan = topic_dir / "wenan.txt"
    shot_csv = topic_dir / "shot_timeline_source_time.csv"
    storyboard_prompt_csv = topic_dir / "storyboard_prompts.csv"
    prompt_csv = topic_dir / "image_prompts_plus.csv"
    element_assets = topic_dir / "element_timeline_with_assets.csv"
    layout_json = topic_dir / "layout_result.json"
    draft_name = draft_name_for_orientation(
        options.draft_name or f"{safe_topic(topic)}_src",
        options.orientation,
    )
    visual_theme = resolve_visual_theme(options.visual_theme)

    commands: list[tuple[str, list[str]]] = []
    if options.run_copy:
        command = [
            py,
            "-m",
            "src.01_generate_copywriting",
            topic,
            "--output",
            str(wenan),
            "--target-chars",
            target_chars,
        ]
        if options.story_world.strip():
            command.extend(["--story-world", options.story_world.strip()])
        commands.append(("01 文案", command))
    if options.run_voice:
        commands.append(("02 配音", [py, "-m", "src.02_generate_voice_timeline", str(wenan)]))
    if options.run_shots:
        commands.append(("03 分镜", [
            py,
            "-m",
            "src.03_generate_shot_timeline",
            str(wenan),
            str(topic_dir / "timeline.csv"),
            "--output",
            str(shot_csv),
        ]))
    if options.run_storyboard_prompts:
        commands.append(("04 图片内容", [
            py,
            "-m",
            "src.04_generate_storyboard_prompts",
            str(shot_csv),
            "--prompt-output",
            str(storyboard_prompt_csv),
            "--orientation",
            options.orientation,
        ]))
    if options.run_prompts:
        image_model = options.image_model.strip() or DEFAULT_IMAGE_MODEL
        commands.append(("05 生图提示词", [
            py,
            "-m",
            "src.05_generate_image_prompts",
            str(storyboard_prompt_csv),
            "--prompt-output",
            str(prompt_csv),
            "--element-output",
            str(element_assets),
            "--model",
            image_model,
            "--theme",
            visual_theme.key,
            "--orientation",
            options.orientation,
        ]))
    if options.run_images:
        image_model = options.image_model.strip() or DEFAULT_IMAGE_MODEL
        image_command = [
            py,
            "-m",
            "src.06_generate_images",
            str(prompt_csv),
            "--model",
            image_model,
            "--theme",
            visual_theme.key,
        ]
        if options.overwrite_images:
            image_command.append("--overwrite")
        commands.append(("06 图片", image_command))
    if options.run_layout:
        layout_command = [
            py,
            "-m",
            "src.07_compile_layout",
            str(topic_dir),
            "--title",
            topic,
            "--theme",
            visual_theme.key,
            "--orientation",
            options.orientation,
            "--output",
            str(layout_json),
        ]
        layout_command.append("--subtitles" if options.include_subtitles else "--no-subtitles")
        commands.append(("07 布局", layout_command))
    if options.run_draft:
        background_image = None
        if options.include_background:
            background_image = resolve_project_file_path(
                options.background_image,
                default_background_image(PROJECT_ROOT, visual_theme.key),
            )
            if not background_image.is_file():
                raise FileNotFoundError(f"背景图片不存在：{background_image}")
        draft_command = [
            py,
            "-m",
            "src.08_generate_jianying_draft",
            str(topic_dir),
            "--layout",
            str(layout_json),
            "--title",
            topic if options.include_title else "",
            "--draft-folder",
            draft_folder,
            "--draft-name",
            draft_name,
            "--theme",
            visual_theme.key,
            "--orientation",
            options.orientation,
            "--replace",
        ]
        if background_image is not None:
            insert_at = draft_command.index("--replace")
            draft_command[insert_at:insert_at] = ["--background", str(background_image.resolve())]
        else:
            draft_command.insert(draft_command.index("--replace"), "--no-background")
        if options.include_background_music:
            background_music = resolve_project_file_path(options.background_music, DEFAULT_BGM_PATH)
            if background_music.suffix.lower() not in {".mp3", ".mp4"}:
                raise ValueError("背景音乐只支持 MP3 或 MP4 文件")
            if not background_music.is_file():
                raise FileNotFoundError(f"背景音乐文件不存在：{background_music}")
            draft_command.extend(["--bgm", str(background_music.resolve())])
        else:
            draft_command.append("--no-bgm")
        commands.append(("08 草稿", draft_command))
    return commands, topic_dir


def build_image_regeneration_command(
    prompt_csv: Path,
    element_ids: list[str],
    *,
    image_model: str,
    image_quality: str,
    visual_theme: str,
    overwrite: bool = True,
) -> list[str]:
    selected = [element_id.strip() for element_id in element_ids if element_id.strip()]
    if not selected:
        raise ValueError("至少选择一张图片")
    command = [
        sys.executable,
        "-m",
        "src.06_generate_images",
        str(prompt_csv.expanduser().resolve()),
        "--model",
        image_model.strip() or DEFAULT_IMAGE_MODEL,
        "--quality",
        image_quality.strip(),
        "--theme",
        resolve_visual_theme(visual_theme).key,
    ]
    if overwrite:
        command.append("--overwrite")
    for element_id in selected:
        command.extend(["--element-id", element_id])
    return command


def build_portrait_package_command(
    project_dir: Path,
    source_video: Path,
    *,
    draft_folder: str,
    draft_name: str,
    project_title: str,
    visual_theme: str,
    include_subtitles: bool = True,
    include_background: bool = True,
) -> list[str]:
    """Build the command for the post-production portrait wrapper workflow."""
    project_dir = project_dir.expanduser().resolve()
    source_video = source_video.expanduser().resolve()
    command = [
        sys.executable,
        "-m",
        "src.commands.build_portrait_package",
        str(project_dir),
        str(source_video),
        "--title",
        project_title.strip(),
        "--draft-folder",
        str(resolve_draft_folder(draft_folder)),
        "--draft-name",
        draft_name.strip() or "portrait_package",
        "--theme",
        resolve_visual_theme(visual_theme).key,
        "--replace",
    ]
    if not include_subtitles:
        command.append("--no-subtitles")
    if not include_background:
        command.append("--no-background")
    return command
