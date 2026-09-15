"""Independent Douyin creator-center upload automation.

The publisher deliberately lives outside the production pipeline.  It uses a
dedicated persistent browser profile so the user can log in once without the
pipeline reading or managing browser credentials.

Some selector fallbacks mirror the MIT-licensed ``vendor/social-auto-upload``
Douyin uploader, while this module keeps the project's Playwright/profile API.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..paths import VIDEO_EXPORT_VARIANTS, safe_topic, video_export_path


DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_PROFILE_NAME = "animation-narration-douyin"
DOUYIN_DEBUG_PORT_FILE = "remote_debug_port.txt"
DOUYIN_PUBLISH_URL_MARKERS = (
    "/creator-micro/content/publish",
    "/creator-micro/content/post/video",
)
DOUYIN_MANAGE_URL_MARKER = "/creator-micro/content/manage"
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

    Canonical project exports are preferred. Common local video folders remain
    as a compatibility fallback for videos exported before project-managed paths.
    """
    topic = topic.strip()
    topic_key = _normalized_name(topic)
    output_root = output_root.expanduser().resolve()
    home = (home or Path.home()).expanduser().resolve()

    video_candidates: dict[Path, int] = {}
    for variant in VIDEO_EXPORT_VARIANTS:
        canonical = video_export_path(output_root, topic, variant)
        if canonical.is_file():
            video_candidates[canonical] = 3000

    project_roots = list(dict.fromkeys((output_root / topic, output_root / safe_topic(topic))))
    roots = list(project_roots)
    roots.extend(home / name for name in ("Movies", "Videos", "Downloads", "Desktop"))
    for root in roots:
        if not root.is_dir():
            continue
        try:
            paths = root.rglob("*") if root in project_roots else root.glob("*")
            for path in paths:
                if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                score = 0
                if topic_key and topic_key in _normalized_name(path.stem):
                    score += 1000
                if root in project_roots:
                    score += 500
                video_candidates[path.resolve()] = score
        except OSError:
            continue
    video = _choose_asset(preferred_video, video_candidates)

    cover_candidates: list[Path] = []
    cover_root = output_root / safe_topic(topic) / "cover"
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
    existing_endpoint = _saved_debug_endpoint(profile)
    if existing_endpoint is not None and _debug_endpoint_available(existing_endpoint):
        return profile
    executable = next((path for path in _chrome_candidates() if path.is_file()), None)
    if executable is None:
        webbrowser.open(DOUYIN_UPLOAD_URL)
        return profile
    port = _available_debug_port()
    (profile / DOUYIN_DEBUG_PORT_FILE).write_text(str(port), encoding="ascii")
    chrome_args = [
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--new-window",
        DOUYIN_UPLOAD_URL,
    ]
    if sys_platform_is_macos():
        # ``open -a`` may reuse an existing Chrome process and silently discard
        # the debugging flags. ``-n`` forces a separate instance for this profile.
        subprocess.Popen(["open", "-na", "Google Chrome", "--args", *chrome_args], close_fds=True)
    else:
        subprocess.Popen([str(executable), *chrome_args], close_fds=True)
    return profile


def _available_debug_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _saved_debug_endpoint(profile: Path) -> str | None:
    try:
        port = int((profile / DOUYIN_DEBUG_PORT_FILE).read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    return f"http://127.0.0.1:{port}"


def _debug_endpoint_available(endpoint: str) -> bool:
    try:
        port = int(endpoint.rsplit(":", 1)[-1])
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except (OSError, ValueError):
        return False


def _wait_for_debug_endpoint(endpoint: str, timeout_ms: int = 10000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _debug_endpoint_available(endpoint):
            return True
        time.sleep(0.2)
    return False


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


def _find_publish_button(page, timeout_ms: int = 5000):
    """Find the exact form submit button, excluding the ``作品发布`` nav item."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        candidates = (
            page.get_by_role("button", name="发布", exact=True).first,
            page.locator('button:text-is("发布")').first,
            page.locator('[role="button"]:text-is("发布")').first,
        )
        for candidate in candidates:
            try:
                if candidate.is_visible(timeout=250):
                    return candidate
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


def _remove_blocking_overlays(page) -> None:
    """Remove onboarding and topic-mention layers that can intercept clicks."""
    try:
        page.evaluate(
            """() => document.querySelectorAll(
                '.shepherd-element, .shepherd-modal-overlay-container, [class*="mention-wrapper"]'
            ).forEach((element) => element.remove())"""
        )
    except Exception:
        # Overlay cleanup is best effort; older page revisions may reject evaluate.
        pass


def _find_video_upload_input(page, timeout_ms: int = 60000):
    """Find Douyin's video input without accidentally selecting a cover input."""
    selectors = (
        'input.upload-btn-input',
        'div[class^="container"] input[accept*="video"]',
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    )
    # File inputs are commonly hidden.  Visibility is not required for
    # set_input_files, so wait for the DOM attachment directly.
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for selector in selectors:
            candidate = page.locator(selector).first
            try:
                candidate.wait_for(state="attached", timeout=250)
                return candidate
            except Exception:
                continue
        time.sleep(0.2)
    return None


def _set_file_input(page, locator, file_path: Path, *, selectors: tuple[str, ...] = ()) -> None:
    """Set a file input, bypassing Playwright's 50MB CDP transfer limit.

    When connected over CDP, Playwright normally uploads the local file through
    its protocol server and rejects files over 50MB.  ``DOM.setFileInputFiles``
    instead passes the local path to the already-local Chrome process.
    """
    try:
        size = file_path.stat().st_size
    except OSError:
        size = 0
    if size <= 50 * 1024 * 1024:
        locator.set_input_files(str(file_path))
        return

    # The CDP path is only needed for large files.  A normal Playwright context
    # still uses the public API, which is more portable across browser engines.
    try:
        session = page.context.new_cdp_session(page)
        document = session.send("DOM.getDocument", {"depth": 1})
        root_id = document["root"]["nodeId"]
        selectors = selectors or ('input[type="file"]',)
        node_id = 0
        for selector in selectors:
            result = session.send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
            if result.get("nodeId"):
                node_id = result["nodeId"]
                break
        if not node_id:
            raise DouyinPublishError("找不到大视频对应的上传控件")
        session.send("DOM.setFileInputFiles", {"nodeId": node_id, "files": [str(file_path)]})
        try:
            session.detach()
        except Exception:
            pass
    except DouyinPublishError:
        raise
    except Exception as exc:
        raise DouyinPublishError(
            f"大视频上传失败（CDP无法让浏览器直接读取本地文件）：{exc}"
        ) from exc


def _upload_cover(page, cover_path: Path) -> None:
    """Open Douyin's cover picker and upload an image using vendor-tested fallbacks."""
    _remove_blocking_overlays(page)
    cover_area = page.locator('[class*="cover-"]').filter(has=page.locator("img")).first
    if cover_area.count() == 0:
        cover_area = page.locator('[class*="cover"]').first
    cover_button = _first_visible(
        page,
        (
            'button:has-text("封面")',
            '[role="button"]:has-text("封面")',
            'text="编辑封面"',
            'text="选择封面"',
            'text="设置封面"',
            'button:has-text("Cover")',
        ),
        timeout_ms=30000,
    ) or cover_area
    if cover_button is None or cover_button.count() == 0:
        raise DouyinPublishError("没有找到抖音封面设置入口，请确认视频已上传完成")

    modal = None
    opened = False
    for _ in range(3):
        try:
            cover_button.click(timeout=5000)
        except Exception:
            try:
                cover_button.evaluate("(element) => element.click()")
            except Exception:
                pass
        try:
            for selector in ("div.dy-creator-content-modal", ".semi-modal-content"):
                candidate = page.locator(selector).first
                try:
                    candidate.wait_for(state="visible", timeout=1500)
                    modal = candidate
                    opened = True
                    break
                except Exception:
                    continue
            if opened:
                break
        except Exception:
            page.wait_for_timeout(500)
    if not opened:
        raise DouyinPublishError("抖音封面设置窗口未打开")

    assert modal is not None
    upload = modal.locator(
        '.semi-upload:has(.semi-upload-drag-area-main-text) input[type="file"]'
    ).first
    if upload.count() == 0:
        upload = modal.locator('input[type="file"]').last
    if upload.count() == 0:
        raise DouyinPublishError("没有找到抖音封面图片上传控件")
    _set_file_input(page, upload, cover_path, selectors=('input[type="file"]',))
    _dismiss_horizontal_cover_prompt(page)

    confirm = None
    for selector in ('button:has-text("完成")', 'button:has-text("确定")', 'button:has-text("保存")'):
        candidate = modal.locator(selector).first
        try:
            if candidate.is_visible(timeout=500):
                confirm = candidate
                break
        except Exception:
            continue
    if confirm is None:
        confirm = _first_visible(page, ('button:has-text("完成")', 'button:has-text("确定")'), timeout_ms=3000)
    if confirm is None:
        raise DouyinPublishError("抖音封面上传后没有找到完成按钮")
    # The button remains disabled while Douyin processes the image.
    deadline = time.monotonic() + 15000 / 1000
    enabled = False
    while time.monotonic() < deadline:
        try:
            if confirm.is_enabled(timeout=250):
                enabled = True
                break
        except Exception:
            pass
        page.wait_for_timeout(300)
    if not enabled:
        raise DouyinPublishError("抖音封面处理超时，请检查图片尺寸或重新生成封面")
    _dismiss_horizontal_cover_prompt(page, timeout_ms=1500)
    confirm.click()
    try:
        modal.wait_for(state="hidden", timeout=10000)
    except Exception:
        # A second confirmation is shown by some page revisions.
        second = _first_visible(page, ('button:has-text("确定")', 'button:has-text("继续")'), timeout_ms=2000)
        if second is not None:
            second.click()
            try:
                modal.wait_for(state="hidden", timeout=5000)
            except Exception:
                pass


def _dismiss_horizontal_cover_prompt(page, timeout_ms: int = 5000) -> bool:
    """Dismiss Douyin's optional horizontal-cover traffic recommendation."""
    prompt_markers = (
        "设置横封面获得更多流量",
        "设置横封面",
    )
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for marker in prompt_markers:
            try:
                prompt = page.locator(".semi-modal-content").filter(has_text=marker).last
                if not prompt.is_visible(timeout=300):
                    continue
                skip = prompt.locator('button:has-text("暂不设置")').first
                if skip.count() == 0:
                    skip = page.get_by_role("button", name="暂不设置").last
                if skip.count() == 0:
                    skip = page.get_by_text("暂不设置", exact=True).last
                if skip.count() and skip.is_visible(timeout=500):
                    skip.click(timeout=5000)
                    try:
                        prompt.wait_for(state="hidden", timeout=5000)
                    except Exception:
                        pass
                    return True
            except Exception:
                continue
        page.wait_for_timeout(200)
    return False


def _wait_for_upload_complete(page, timeout_ms: int) -> None:
    """Wait for Douyin's real upload-complete marker and an enabled publish action."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        _remove_blocking_overlays(page)
        try:
            if page.locator('[class^="long-card"] div:has-text("重新上传")').count() > 0:
                publish_button = _find_publish_button(page, timeout_ms=1000)
                if publish_button is not None and publish_button.is_enabled(timeout=250):
                    return
        except Exception:
            pass
        try:
            if page.locator('div.progress-div:has-text("上传失败")').count() > 0:
                raise DouyinPublishError("抖音视频上传失败，请重新选择视频后再试")
        except DouyinPublishError:
            raise
        except Exception:
            pass
        publish_button = _find_publish_button(page, timeout_ms=500)
        if publish_button is not None:
            try:
                if publish_button.is_enabled(timeout=250):
                    return
            except Exception:
                pass
        time.sleep(0.5)
    raise DouyinPublishError("视频上传或处理超时，请检查抖音页面状态")


def _set_ai_declaration(page) -> bool:
    """Best-effort selection of Douyin's ``内容由AI生成`` declaration."""
    _remove_blocking_overlays(page)
    entry = _first_visible(
        page,
        (
            'text="请选择自主声明"',
            'text="请选择声明类型"',
            'text="添加自主声明"',
            'text="自主声明"',
            'text="作品声明"',
        ),
        timeout_ms=3000,
    )
    if entry is None:
        return False
    try:
        entry.click(timeout=5000)
        dialog = None
        for selector in (".semi-modal-content", ".semi-modal-body"):
            candidate = page.locator(selector).filter(has_text="请选择声明类型").first
            try:
                candidate.wait_for(state="visible", timeout=1500)
                dialog = candidate
                break
            except Exception:
                continue
        if dialog is None:
            return False
        option = dialog.locator("label.semi-radio").filter(has_text="内容由AI生成").first
        if option.count() == 0:
            option = dialog.get_by_text("内容由AI生成", exact=True).first
        if option.count() == 0:
            return False
        option.click(timeout=5000)
        confirm = dialog.get_by_role("button", name="确定").first
        if confirm.count() == 0:
            confirm = page.get_by_role("button", name="确定").first
        if confirm.count():
            confirm.click(timeout=5000)
        return True
    except Exception:
        return False


def _wait_for_publish_success(page, timeout_ms: int) -> None:
    markers = (
        'text="发布成功"',
        'text="作品发布成功"',
        '[role="alert"]:has-text("成功")',
    )
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for selector in markers:
            try:
                if page.locator(selector).first.is_visible(timeout=250):
                    return
            except Exception:
                continue
        try:
            if DOUYIN_MANAGE_URL_MARKER in page.url:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise DouyinPublishError("已点击发布，但没有确认到抖音发布成功状态，请登录创作中心核实")


def _verification_required(page) -> bool:
    """Return whether a phone/SMS verification layer is currently visible."""
    for selector in (
        'input[placeholder*="验证码"]',
        'input[placeholder*="短信"]',
        'input[placeholder*="手机号"]',
        'input[type="tel"]',
    ):
        try:
            if page.locator(selector).first.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def _select_douyin_page(context):
    """Reuse an existing creator-center tab when CDP exposes several tabs."""
    pages = list(context.pages)
    for candidate in pages:
        try:
            if "creator.douyin.com" in candidate.url:
                return candidate
        except Exception:
            continue
    return pages[0] if pages else context.new_page()


def _login_page_detected(page) -> bool:
    try:
        url = page.url.casefold()
        if any(marker in url for marker in ("login", "passport", "account")):
            return True
    except Exception:
        pass
    for selector in ('text="手机号登录"', 'text="扫码登录"', 'text="登录"'):
        try:
            if page.locator(selector).first.is_visible(timeout=300):
                return True
        except Exception:
            continue
    return False


def _discard_unfinished_draft(page, timeout_ms: int = 3000) -> bool:
    """Discard a previous unfinished draft before uploading the current request."""
    marker = page.get_by_text("你还有上次未发布的视频，是否继续编辑？", exact=False).first
    try:
        if not marker.is_visible(timeout=timeout_ms):
            return False
    except Exception:
        return False

    choices = page.get_by_text("放弃", exact=True)
    discard = None
    for index in range(choices.count() - 1, -1, -1):
        candidate = choices.nth(index)
        try:
            if candidate.is_visible(timeout=200):
                discard = candidate
                break
        except Exception:
            continue
    if discard is None:
        raise DouyinPublishError("检测到上次未发布的视频，但没有找到“放弃”按钮")
    discard.click(timeout=5000)
    page.wait_for_timeout(500)

    for name in ("确定放弃", "确认放弃", "确定"):
        candidate = page.get_by_role("button", name=name, exact=True).last
        try:
            if candidate.is_visible(timeout=300):
                candidate.click(timeout=5000)
                break
        except Exception:
            continue
    try:
        marker.wait_for(state="hidden", timeout=5000)
    except Exception:
        pass
    return True


def publish_to_douyin(request: DouyinPublishRequest, *, timeout_ms: int = 120000) -> None:
    """Upload, fill metadata, and click publish in a visible browser window."""
    request = request.validated()
    sync_playwright = _load_playwright()
    profile = douyin_browser_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        connected_over_cdp = False
        context = None
        try:
            endpoint = _saved_debug_endpoint(profile)
            if endpoint is not None:
                if _wait_for_debug_endpoint(endpoint):
                    browser = playwright.chromium.connect_over_cdp(endpoint, timeout=5000)
                    connected_over_cdp = True
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
        except Exception:
            context = None
        if context is None:
            try:
                executable = next((path for path in _chrome_candidates() if path.is_file()), None)
                launch_options = {"headless": False}
                if executable is not None:
                    launch_options["executable_path"] = str(executable)
                context = playwright.chromium.launch_persistent_context(str(profile), **launch_options)
            except Exception as exc:
                raise DouyinPublishError(f"无法启动专用浏览器：{exc}") from exc
        try:
            page = _select_douyin_page(context)
            page.goto(DOUYIN_UPLOAD_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            if _login_page_detected(page):
                raise DouyinPublishError("当前专用浏览器会话未登录抖音，请先点击“登录/检查抖音”完成登录")
            if _discard_unfinished_draft(page):
                page.wait_for_timeout(1000)
            file_input = _find_video_upload_input(page, timeout_ms=timeout_ms)
            if file_input is None:
                raise DouyinPublishError("抖音页面未进入上传状态，请先在专用浏览器中完成登录")
            _set_file_input(
                page,
                file_input,
                request.video_path,
                selectors=(
                    'input.upload-btn-input',
                    'input[type="file"][accept*="video"]',
                    'input[type="file"]',
                ),
            )
            # New and legacy creator-center versions redirect to different URLs.
            try:
                deadline = time.monotonic() + min(timeout_ms, 30000) / 1000
                while time.monotonic() < deadline and not any(marker in page.url for marker in DOUYIN_PUBLISH_URL_MARKERS):
                    page.wait_for_timeout(300)
            except Exception:
                pass
            _fill_title(page, request.title)
            _fill_description(page, publish_description(request))
            _wait_for_upload_complete(page, timeout_ms)
            _set_ai_declaration(page)
            if request.cover_path is not None:
                _upload_cover(page, request.cover_path)
            _remove_blocking_overlays(page)
            publish_button = _find_publish_button(page, timeout_ms=15000)
            if publish_button is None:
                raise DouyinPublishError("没有找到抖音发布按钮，请检查账号登录状态和页面版本")
            if _verification_required(page):
                raise DouyinPublishError("抖音要求短信验证，请在专用浏览器中完成验证后重新点击发布")
            publish_button.click()
            _wait_for_publish_success(page, timeout_ms)
        except Exception as exc:
            if isinstance(exc, DouyinPublishError):
                raise
            raise DouyinPublishError(str(exc)) from exc
        finally:
            if not connected_over_cdp:
                context.close()
