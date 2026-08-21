"""Independent Douyin creator-center upload automation.

The publisher deliberately lives outside the production pipeline.  It uses a
dedicated persistent browser profile so the user can log in once without the
pipeline reading or managing browser credentials.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_PROFILE_NAME = "animation-narration-douyin"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class DouyinPublishError(RuntimeError):
    """Raised when the creator center cannot be opened or completed."""


@dataclass(frozen=True)
class DouyinPublishRequest:
    video_path: Path
    title: str
    description: str = ""
    cover_path: Path | None = None
    topics: tuple[str, ...] = ()

    def validated(self) -> "DouyinPublishRequest":
        video = self.video_path.expanduser().resolve()
        if not video.is_file():
            raise DouyinPublishError(f"视频文件不存在：{video}")
        if video.suffix.lower() not in VIDEO_SUFFIXES:
            raise DouyinPublishError("抖音发布只支持 MP4、MOV、M4V 或 AVI 视频")
        title = self.title.strip()
        if not title:
            raise DouyinPublishError("抖音标题不能为空")
        if len(title) > 55:
            raise DouyinPublishError("抖音标题不能超过 55 个字符")
        cover = None
        if self.cover_path is not None and str(self.cover_path).strip():
            cover = Path(self.cover_path).expanduser().resolve()
            if not cover.is_file():
                raise DouyinPublishError(f"封面图片不存在：{cover}")
            if cover.suffix.lower() not in IMAGE_SUFFIXES:
                raise DouyinPublishError("封面只支持 PNG、JPG、JPEG 或 WEBP 图片")
        topics = normalize_topics(self.topics)
        return DouyinPublishRequest(video, title, self.description.strip(), cover, topics)


def normalize_topics(value: str | Iterable[str]) -> tuple[str, ...]:
    """Normalize user-entered topic tags to unique ``#话题`` values."""
    values = value.splitlines() if isinstance(value, str) else value
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        for token in re.split(r"[\s,，;；]+", str(item).strip()):
            token = token.strip().lstrip("#")
            if not token:
                continue
            normalized = f"#{token}"
            if normalized.casefold() not in seen:
                seen.add(normalized.casefold())
                result.append(normalized)
    return tuple(result)


def publish_description(request: DouyinPublishRequest) -> str:
    """Combine optional copy and topic tags for the creator-center description."""
    request = request.validated()
    parts = [request.description.strip(), " ".join(request.topics)]
    return " ".join(part for part in parts if part)


def discover_publish_assets(
    topic: str,
    *,
    output_root: Path,
    preferred_video: Path | None = None,
    preferred_cover: Path | None = None,
    home: Path | None = None,
) -> tuple[Path | None, Path | None]:
    """Find the current topic's latest video and generated cover.

    Export destinations are user-configurable in Jianying, so the search uses
    the project output first and then common local video folders.  A preferred
    path (for example the path returned by the export automation) always wins.
    """
    topic = topic.strip()
    topic_key = _normalized_name(topic)
    output_root = output_root.expanduser().resolve()
    home = (home or Path.home()).expanduser().resolve()

    video_candidates: dict[Path, int] = {}
    roots = [output_root / topic, output_root / _safe_topic(topic)]
    roots.extend(home / name for name in ("Movies", "Videos", "Downloads", "Desktop"))
    for root in roots:
        if not root.is_dir():
            continue
        try:
            paths = root.rglob("*") if root in roots[:2] else root.glob("*")
            for path in paths:
                if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                score = 0
                if topic_key and topic_key in _normalized_name(path.stem):
                    score += 1000
                if root == output_root / topic or root == output_root / _safe_topic(topic):
                    score += 500
                video_candidates[path.resolve()] = score
        except OSError:
            continue
    video = _choose_asset(preferred_video, video_candidates)

    cover_candidates: list[Path] = []
    cover_root = output_root / _safe_topic(topic) / "cover"
    if cover_root.is_dir():
        try:
            cover_candidates = [
                path.resolve()
                for path in cover_root.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            ]
        except OSError:
            cover_candidates = []
    cover = preferred_cover.expanduser().resolve() if preferred_cover and preferred_cover.is_file() else None
    if cover is None and cover_candidates:
        cover = max(cover_candidates, key=_mtime_ns)
    return video, cover


def _choose_asset(preferred: Path | None, candidates: dict[Path, int]) -> Path | None:
    if preferred is not None:
        preferred = preferred.expanduser().resolve()
        if preferred.is_file() and preferred.suffix.lower() in VIDEO_SUFFIXES:
            return preferred
    if not candidates:
        return None
    return max(candidates, key=lambda path: (candidates[path], _mtime_ns(path)))


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _safe_topic(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .") or "未命名主题"


def _normalized_name(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def douyin_browser_profile_dir() -> Path:
    configured = os.environ.get("LOCALAPPDATA", "").strip()
    root = Path(configured) if configured else Path.home() / ".animation_narration"
    if not configured and os.name == "nt":
        root = Path.home() / "AppData" / "Local" / "animation_narration"
    if not str(root):
        root = Path.home() / ".animation_narration"
    return root / DOUYIN_PROFILE_NAME


def _chrome_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"))
    candidates = [
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    if sys_platform_is_macos():
        candidates.extend([
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ])
    else:
        candidates.extend([
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/microsoft-edge"),
        ])
    return candidates


def sys_platform_is_macos() -> bool:
    return os.sys.platform == "darwin"


def open_douyin_upload_page() -> Path:
    """Open the dedicated creator-center profile for manual login or upload."""
    profile = douyin_browser_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    executable = next((path for path in _chrome_candidates() if path.is_file()), None)
    if executable is None:
        webbrowser.open(DOUYIN_UPLOAD_URL)
        return profile
    subprocess.Popen(
        [str(executable), f"--user-data-dir={profile}", "--new-window", DOUYIN_UPLOAD_URL],
        close_fds=True,
    )
    return profile


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise DouyinPublishError("缺少 Playwright，请先安装项目依赖") from exc
    return sync_playwright


def _first_visible(page, selectors: tuple[str, ...], timeout_ms: int = 5000):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if locator.is_visible(timeout=250):
                    return locator
            except Exception:
                continue
        time.sleep(0.2)
    return None


def _fill_title(page, title: str) -> None:
    title_input = _first_visible(
        page,
        (
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            'input[placeholder*="作品"]',
        ),
        timeout_ms=30000,
    )
    if title_input is None:
        raise DouyinPublishError("没有找到抖音标题输入框，请确认页面仍是创作中心上传页")
    title_input.fill(title)


def _fill_description(page, description: str) -> None:
    if not description:
        return
    description_input = _first_visible(
        page,
        (
            'textarea[placeholder*="描述"]',
            'textarea[placeholder*="简介"]',
            '[contenteditable="true"]',
        ),
        timeout_ms=30000,
    )
    if description_input is None:
        raise DouyinPublishError("没有找到抖音描述输入框")
    description_input.fill(description)


def _upload_cover(page, cover_path: Path) -> None:
    """Open the creator-center cover picker and upload the generated image."""
    cover_button = _first_visible(
        page,
        (
            'button:has-text("封面")',
            '[role="button"]:has-text("封面")',
            'button:has-text("Cover")',
            '[role="button"]:has-text("Cover")',
        ),
        timeout_ms=30000,
    )
    if cover_button is None:
        raise DouyinPublishError("没有找到抖音封面设置入口，请确认视频已上传完成")
    cover_button.click()
    page.wait_for_timeout(500)
    inputs = page.locator('input[type="file"]')
    chosen = None
    for index in range(inputs.count() - 1, -1, -1):
        candidate = inputs.nth(index)
        try:
            accept = (candidate.get_attribute("accept") or "").lower()
        except Exception:
            accept = ""
        if not accept or "image" in accept or any(ext.lstrip(".") in accept for ext in IMAGE_SUFFIXES):
            chosen = candidate
            break
    if chosen is None:
        raise DouyinPublishError("没有找到抖音封面图片上传控件")
    chosen.set_input_files(str(cover_path))
    confirm = _first_visible(
        page,
        (
            'button:has-text("完成")',
            'button:has-text("确定")',
            'button:has-text("保存")',
            '[role="button"]:has-text("完成")',
        ),
        timeout_ms=30000,
    )
    if confirm is not None:
        confirm.click()


def publish_to_douyin(request: DouyinPublishRequest, *, timeout_ms: int = 120000) -> None:
    """Upload, fill metadata, and click publish in a visible browser window."""
    request = request.validated()
    sync_playwright = _load_playwright()
    profile = douyin_browser_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            executable = next((path for path in _chrome_candidates() if path.is_file()), None)
            launch_options = {"headless": False}
            if executable is not None:
                launch_options["executable_path"] = str(executable)
            context = playwright.chromium.launch_persistent_context(str(profile), **launch_options)
        except Exception as exc:
            raise DouyinPublishError(f"无法启动专用浏览器：{exc}") from exc
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(DOUYIN_UPLOAD_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            file_input = page.locator('input[type="file"]').first
            try:
                file_input.wait_for(state="attached", timeout=timeout_ms)
            except Exception as exc:
                raise DouyinPublishError("抖音页面未进入上传状态，请先在专用浏览器中完成登录") from exc
            file_input.set_input_files(str(request.video_path))
            time.sleep(2)
            if request.cover_path is not None:
                _upload_cover(page, request.cover_path)
            _fill_title(page, request.title)
            _fill_description(page, publish_description(request))
            publish_button = _first_visible(
                page,
                (
                    'button:has-text("发布")',
                    '[role="button"]:has-text("发布")',
                ),
                timeout_ms=15000,
            )
            if publish_button is None:
                raise DouyinPublishError("没有找到抖音发布按钮，请检查账号登录状态和页面版本")
            publish_button.click()
            page.wait_for_timeout(3000)
        finally:
            context.close()
