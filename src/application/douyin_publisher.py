"""Independent Douyin creator-center upload automation.

The publisher deliberately lives outside the production pipeline.  It uses a
dedicated persistent browser profile so the user can log in once without the
pipeline reading or managing browser credentials.
"""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path


DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_PROFILE_NAME = "animation-narration-douyin"


class DouyinPublishError(RuntimeError):
    """Raised when the creator center cannot be opened or completed."""


@dataclass(frozen=True)
class DouyinPublishRequest:
    video_path: Path
    title: str
    description: str = ""

    def validated(self) -> "DouyinPublishRequest":
        video = self.video_path.expanduser().resolve()
        if not video.is_file():
            raise DouyinPublishError(f"视频文件不存在：{video}")
        if video.suffix.lower() not in {".mp4", ".mov", ".m4v", ".avi"}:
            raise DouyinPublishError("抖音发布只支持 MP4、MOV、M4V 或 AVI 视频")
        title = self.title.strip()
        if not title:
            raise DouyinPublishError("抖音标题不能为空")
        if len(title) > 55:
            raise DouyinPublishError("抖音标题不能超过 55 个字符")
        return DouyinPublishRequest(video, title, self.description.strip())


def douyin_browser_profile_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", ""))
    if not str(root):
        root = Path.home() / ".animation_narration"
    return root / DOUYIN_PROFILE_NAME


def _chrome_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"))
    return [
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]


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
        timeout_ms=10000,
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
        timeout_ms=10000,
    )
    if description_input is None:
        raise DouyinPublishError("没有找到抖音描述输入框")
    description_input.fill(description)


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
            _fill_title(page, request.title)
            _fill_description(page, request.description)
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
