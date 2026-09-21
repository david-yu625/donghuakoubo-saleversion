"""Cross-platform desktop automation for opening and exporting Jianying drafts.

This module is intentionally separate from the 01-08 production pipeline.  It
only operates on a draft that already exists in Jianying's draft directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import subprocess
import time
import ctypes
import re
from ctypes import wintypes
from pathlib import Path
from typing import Iterable


class JianyingAutomationError(RuntimeError):
    """Raised when Jianying cannot be reached or a requested UI action fails."""


JIANYING_PROCESS_NAME = "JianyingPro.exe"
EXPORT_BUTTON_NAMES = ("MainWindowTitleBarExportBtn", "导出", "导出视频")
MACOS_JIANYING_BUNDLE_ID = "com.lemon.lvpro"
MACOS_JIANYING_APP_NAMES = (
    "VideoFusion-macOS.app",
    "剪映专业版.app",
    "JianyingPro.app",
    "CapCut.app",
)
# Accessibility queries can block while Jianying is loading a large draft or
# rendering its timeline. Short polling intervals must not turn that busy time
# into a hard subprocess timeout.
MACOS_OSASCRIPT_MIN_TIMEOUT = 8.0


class _CGPoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))


def _macos_post_mouse_click(x: float, y: float, *, clicks: int = 1) -> None:
    """Post a real macOS mouse event; Qt does not expose clickable AX controls."""
    if sys.platform != "darwin":
        raise JianyingAutomationError("原生 macOS 鼠标事件仅支持 macOS")
    try:
        graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        create_event = graphics.CGEventCreateMouseEvent
        create_event.argtypes = [ctypes.c_void_p, ctypes.c_uint32, _CGPoint, ctypes.c_uint32]
        create_event.restype = ctypes.c_void_p
        post_event = graphics.CGEventPost
        post_event.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        core_foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        release = core_foundation.CFRelease
        release.argtypes = [ctypes.c_void_p]
    except OSError as exc:
        raise JianyingAutomationError(f"无法加载 macOS 鼠标自动化组件：{exc}") from exc

    point = _CGPoint(float(x), float(y))
    for _ in range(max(1, clicks)):
        down = create_event(None, 1, point, 0)  # kCGEventLeftMouseDown/kCGMouseButtonLeft
        up = create_event(None, 2, point, 0)  # kCGEventLeftMouseUp
        if not down or not up:
            if down:
                release(down)
            if up:
                release(up)
            raise JianyingAutomationError("无法创建 macOS 鼠标事件")
        try:
            post_event(0, down)  # kCGHIDEventTap
            time.sleep(0.08)
            post_event(0, up)
        finally:
            release(down)
            release(up)
        time.sleep(0.18)


def validate_draft_path(draft_folder: str | Path, draft_name: str) -> Path:
    folder = Path(draft_folder).expanduser().resolve()
    name = draft_name.strip()
    if not name:
        raise JianyingAutomationError("草稿名不能为空")
    # Jianying runs on Windows, but this validation also runs on macOS/Linux
    # during setup and tests, where pathlib does not treat ``\\`` as a separator.
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise JianyingAutomationError("草稿名不能包含目录路径")
    draft_path = folder / name
    if draft_path.is_dir():
        return draft_path
    # Jianying may append a numeric suffix when it imports/duplicates a draft.
    suffix_pattern = re.compile(rf"^{re.escape(name)}\((\d+)\)$")
    candidates = (
        [
            child
            for child in folder.iterdir()
            if child.is_dir() and suffix_pattern.match(child.name)
        ]
        if folder.is_dir()
        else []
    )
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)
    raise JianyingAutomationError(f"找不到剪映草稿：{draft_path}")


def find_timestamp_matching_draft(draft_folder: str | Path, requested_name: str) -> Path | None:
    """Recover a renamed draft using its unique creation timestamp and stage suffix."""
    folder = Path(draft_folder).expanduser().resolve()
    name = requested_name.strip()
    timestamp = re.search(r"(?<!\d)(20\d{6}_\d{6})(?!\d)", name)
    if not timestamp or not folder.is_dir():
        return None
    stage_suffix = name[timestamp.end():]
    if not stage_suffix:
        return None
    matches = []
    for child in folder.iterdir():
        if not child.is_dir() or timestamp.group(1) not in child.name:
            continue
        normalized_name = re.sub(r"\(\d+\)$", "", child.name)
        if normalized_name.endswith(stage_suffix):
            matches.append(child.resolve())
    return matches[0] if len(matches) == 1 else None


def find_jianying_executable() -> Path:
    """Find the installed Windows Jianying executable without hardcoding a version."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"))
    roots = (
        local_app_data / "JianyingPro" / "Apps",
        program_files / "JianyingPro" / "Apps",
        program_files_x86 / "JianyingPro" / "Apps",
    )
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("*/JianyingPro.exe"))
        direct = root / "JianyingPro.exe"
        if direct.is_file():
            candidates.append(direct)
    if not candidates:
        raise JianyingAutomationError("没有找到 JianyingPro.exe，请先安装或启动剪映专业版")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _windows_helpers():
    if os.name != "nt":
        raise JianyingAutomationError("当前系统不是 Windows")
    try:
        import uiautomation as auto
    except ImportError as exc:
        raise JianyingAutomationError(
            "缺少 Windows 自动化依赖，请安装 uiautomation"
        ) from exc
    return auto, _WindowsWindowApi()


class _WindowsWindowApi:
    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def is_visible(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindowVisible(hwnd))

    def is_enabled(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindowEnabled(hwnd))

    def process_id(self, hwnd: int) -> int:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return int(process_id.value)

    def process_name(self, pid: int) -> str:
        handle = self.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value).name
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def enumerate_windows(self, callback) -> None:
        def keep_enumerating(hwnd, extra):
            callback(hwnd, extra)
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(keep_enumerating)
        self.user32.EnumWindows(enum_proc, 0)

    def restore_and_focus(self, hwnd: int) -> None:
        self.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        self.user32.SetForegroundWindow(hwnd)

    def close(self, hwnd: int) -> None:
        # Qt-based Jianying builds are not consistent about handling a bare
        # WM_CLOSE.  Send the normal system close command first, then retain
        # WM_CLOSE as a fallback for builds that do not expose a system menu.
        self.user32.PostMessageW(hwnd, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND/SC_CLOSE
        self.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def terminate_process_tree(self, pid: int) -> None:
        """Terminate only Jianying's process tree after export is complete."""
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5.0,
        )


def _window_handles(process_name: str, window_api: _WindowsWindowApi) -> list[int]:
    handles: list[int] = []

    def collect(hwnd: int, _extra) -> None:
        if not window_api.is_visible(hwnd):
            return
        pid = window_api.process_id(hwnd)
        if (
            window_api.process_name(pid).casefold() == process_name.casefold()
            and window_api.is_enabled(hwnd)
        ):
            handles.append(hwnd)

    window_api.enumerate_windows(collect)
    return handles


def _wait_for_window(auto, window_api: _WindowsWindowApi, process_name: str, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd in _window_handles(process_name, window_api):
            control = auto.ControlFromHandle(hwnd)
            if control is not None:
                return hwnd, control
        time.sleep(0.4)
    raise JianyingAutomationError("等待剪映主窗口超时")


def _walk_controls(control, *, max_depth: int = 7) -> Iterable[object]:
    if max_depth < 0:
        return
    yield control
    try:
        children = control.GetChildren()
    except Exception:
        return
    for child in children:
        yield from _walk_controls(child, max_depth=max_depth - 1)


def _find_named_control(
    window,
    names: tuple[str, ...],
    *,
    timeout: float,
    contains: bool = False,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for control in _walk_controls(window):
            control_names: list[str] = []
            try:
                control_names.append(str(control.Name or ""))
            except Exception:
                pass
            try:
                full_description = control.GetPropertyValue(30159)
                if full_description:
                    control_names.append(str(full_description))
            except Exception:
                pass
            # Jianying stores internal Qt identifiers such as ExportOkBtn
            # in UIA_FullDescriptionPropertyId on Windows.
            if any(
                value in names
                or (contains and any(name in value for name in names))
                for value in control_names
            ):
                return control
        time.sleep(0.4)
    return None


def _activate_window(hwnd: int, window_api: _WindowsWindowApi) -> None:
    try:
        window_api.restore_and_focus(hwnd)
    except Exception:
        pass


def _find_windows_control(
    auto,
    window_api: _WindowsWindowApi,
    names: tuple[str, ...],
    *,
    timeout: float,
    contains: bool = False,
    preferred_hwnd: int | None = None,
):
    """Find a control across Jianying's top-level windows.

    Export settings are a separate Qt window in some Windows builds and a
    child of the editor window in others. Searching only the editor root makes
    the final export button appear to be missing on the former builds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        handles = _window_handles(JIANYING_PROCESS_NAME, window_api)
        if preferred_hwnd in handles:
            handles.remove(preferred_hwnd)
            handles.insert(0, preferred_hwnd)
        for hwnd in handles:
            try:
                window = auto.ControlFromHandle(hwnd)
            except Exception:
                continue
            if window is None:
                continue
            control = _find_named_control(
                window,
                names,
                timeout=min(0.5, max(0.05, deadline - time.monotonic())),
                contains=contains,
            )
            if control is not None:
                return hwnd, window, control
        time.sleep(0.2)
    return None, None, None


def _open_draft_windows(draft_path: Path, draft_name: str, *, timeout: float) -> Path:
    auto, window_api = _windows_helpers()
    handles = _window_handles(JIANYING_PROCESS_NAME, window_api)
    if handles:
        hwnd = handles[0]
        window = auto.ControlFromHandle(hwnd)
    else:
        executable = find_jianying_executable()
        subprocess.Popen([str(executable)], close_fds=True)
        hwnd, window = _wait_for_window(auto, window_api, JIANYING_PROCESS_NAME, timeout)
    if window is None:
        raise JianyingAutomationError("无法连接到剪映主窗口")
    _activate_window(hwnd, window_api)

    # Jianying exposes the title through UIA_FullDescriptionPropertyId rather
    # than Name. The title's parent is the clickable project card.
    ui_names = tuple(dict.fromkeys((draft_path.name, draft_name.strip())))
    title_descriptions = tuple(f"HomePageDraftTitle:{name}" for name in ui_names)
    title_control = _find_named_control(window, title_descriptions, timeout=timeout)
    if title_control is None:
        raise JianyingAutomationError(
            f"剪映中没有找到名为“{draft_name.strip()}”的草稿，请先在项目首页刷新列表"
        )
    try:
        card = title_control.GetParentControl()
        if card is None:
            raise JianyingAutomationError("无法定位剪映草稿卡片")
        card.Click(simulateMove=False)
    except JianyingAutomationError:
        raise
    except Exception as exc:
        raise JianyingAutomationError(f"打开草稿失败：{exc}") from exc
    return draft_path


def _find_macos_jianying_app() -> Path | None:
    roots = (Path("/Applications"), Path.home() / "Applications")
    for root in roots:
        for name in MACOS_JIANYING_APP_NAMES:
            candidate = root / name
            if candidate.is_dir():
                return candidate
    return None


def _run_macos_osascript(script: str, *, timeout: float) -> str:
    # Give each AX query enough time to cross a temporarily busy Qt
    # accessibility bridge, even when the caller is polling frequently.
    command_timeout = max(float(timeout), MACOS_OSASCRIPT_MIN_TIMEOUT)
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command_timeout,
            check=True,
        )
    except FileNotFoundError as exc:
        raise JianyingAutomationError("找不到 macOS osascript 工具") from exc
    except subprocess.TimeoutExpired as exc:
        raise JianyingAutomationError(
            f"等待 macOS 剪映界面超时（辅助功能查询超过 {command_timeout:g} 秒）"
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        if (
            "-25211" in message
            or "-1002" in message
            or "不允许发送按键" in message
            or "辅助访问" in message
            or "accessibility" in message.casefold()
        ):
            try:
                subprocess.Popen(
                    [
                        "/usr/bin/open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
            raise JianyingAutomationError(
                "macOS 拒绝了按键自动化（错误码 1002）。"
                "已打开辅助功能设置，请允许“终端/启动器”和 /usr/bin/osascript 控制电脑，"
                "然后重新执行第09步。"
            ) from exc
        raise JianyingAutomationError(f"macOS 剪映自动化失败：{message or exc}") from exc
    return result.stdout.strip()


def _macos_focus_process(*, timeout: float) -> None:
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set frontmost of p to true
    perform action "AXRaise" of front window of p
end tell
'''
    _run_macos_osascript(script, timeout=timeout)


def _macos_home_draft_rect(
    draft_name: str, *, timeout: float
) -> tuple[float, float, float, float] | None:
    escaped_name = draft_name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set e to first static text of front window of p whose name is "HomePageDraftTitle:{escaped_name}"
    set q to position of e
    set s to size of e
    return ((item 1 of q) as text) & "," & ((item 2 of q) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
end tell
'''
    try:
        result = _run_macos_osascript(script, timeout=timeout)
    except JianyingAutomationError as exc:
        if "不能获得" in str(exc) or "无效的索引" in str(exc):
            return None
        raise
    try:
        x, y, width, height = (float(item) for item in result.split(","))
    except (TypeError, ValueError) as exc:
        raise JianyingAutomationError(f"无法读取剪映草稿位置：{result}") from exc
    return x, y, width, height


def _macos_search_home_drafts(query: str, *, timeout: float) -> bool:
    """Filter Jianying's home draft list by its built-in search field."""
    escaped_query = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set fields to text fields of front window of p
    if (count of fields) is 0 then return "missing"
    set value of item 1 of fields to "{escaped_query}"
    keystroke return
    return "ok"
end tell
'''
    try:
        return _run_macos_osascript(script, timeout=timeout) == "ok"
    except JianyingAutomationError:
        return False


def _macos_front_window_rect(*, timeout: float) -> tuple[float, float, float, float]:
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set w to front window of p
    set q to position of w
    set s to size of w
    return ((item 1 of q) as text) & "," & ((item 2 of q) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
end tell
'''
    result = _run_macos_osascript(script, timeout=timeout)
    try:
        x, y, width, height = (float(item) for item in result.split(","))
    except (TypeError, ValueError) as exc:
        raise JianyingAutomationError(f"无法读取剪映窗口位置：{result}") from exc
    return x, y, width, height


def _macos_editor_ready(*, timeout: float) -> bool:
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set readyItem to first static text of front window of p whose name is "VETreeMainCellItem:本地"
    return "ready"
end tell
'''
    try:
        return _run_macos_osascript(script, timeout=timeout) == "ready"
    except JianyingAutomationError as exc:
        if "不能获得" in str(exc) or "无效的索引" in str(exc):
            return False
        raise


def _macos_window_state(*, timeout: float) -> str:
    """Classify the front Jianying window without walking its whole AX tree."""
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set w to front window of p
    if (count of (static texts of w whose name is "正在导出")) > 0 then return "exporting"
    if (count of (static texts of w whose name starts with "ExportProgress:")) > 0 then return "exporting"
    if (count of (static texts of w whose name starts with "MTLSText:")) > 0 then return "editor"
    if (count of (static texts of w whose name starts with "HomePageDraftTitle:")) > 0 then return "home"
    return "unknown"
end tell
'''
    try:
        return _run_macos_osascript(script, timeout=timeout) or "unknown"
    except JianyingAutomationError:
        return "unknown"


def _macos_export_panel_open(*, timeout: float) -> bool:
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    repeat with e in static texts of front window of p
        try
            set n to name of e as text
            if n ends with ".mp4" then return "open"
        end try
    end repeat
    return "closed"
end tell
'''
    return _run_macos_osascript(script, timeout=timeout) == "open"


def _macos_export_state(*, timeout: float) -> str:
    """Return ``settings``, ``progress`` or ``complete`` for the export dialog."""
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set w to front window of p
    if (name of w as text) is not "导出" then return "closed"
    repeat with e in static texts of w
        try
            set n to name of e as text
            set d to description of e as text
            if d is "ExportSucceedCloseBtn" then return "complete"
            if n is "正在导出" or n starts with "ExportProgress:" then return "progress"
        end try
    end repeat
    repeat with e in static texts of w
        try
            set n to name of e as text
            if n ends with ".mp4" then return "settings"
        end try
    end repeat
    return "closed"
end tell
'''
    return _run_macos_osascript(script, timeout=timeout)


def _macos_export_button_rect(*, timeout: float) -> tuple[float, float, float, float] | None:
    """Return the final export button's screen rectangle from the export dialog."""
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    repeat with b in buttons of front window of p
        try
            set n to name of b as text
            set d to description of b as text
            if n is "ExportOkBtn" or d is "ExportOkBtn" or n is "导出" or n is "导出视频" then
                set q to position of b
                set s to size of b
                return ((item 1 of q) as text) & "," & ((item 2 of q) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
            end if
        end try
    end repeat
    return "missing"
end tell
'''
    try:
        result = _run_macos_osascript(script, timeout=timeout)
    except JianyingAutomationError as exc:
        if "不能获得" in str(exc) or "无效的索引" in str(exc):
            return None
        raise
    if result == "missing":
        return None
    try:
        x, y, width, height = (float(item) for item in result.split(","))
    except (TypeError, ValueError) as exc:
        raise JianyingAutomationError(f"无法读取剪映最终导出按钮位置：{result}") from exc
    return x, y, width, height


def _parse_export_path(value: str) -> Path | None:
    raw = value.strip().strip('"')
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.suffix.casefold() not in {".mp4", ".mov", ".m4v"}:
        return None
    if raw.startswith("~"):
        return candidate.resolve()
    # ``Path.is_absolute`` on Windows does not recognize a POSIX-rooted path
    # such as ``/Users/...``. Keep that spelling intact for macOS values read
    # through a Windows test or compatibility layer.
    if candidate.is_absolute() or raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return candidate
    return None


def relocate_exported_video(source: Path, target: Path) -> Path:
    """Place Jianying's completed export at the project's canonical path."""
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    if source == target:
        if not target.is_file():
            raise JianyingAutomationError(f"剪映导出文件不存在：{target}")
        return target
    if not source.is_file():
        raise JianyingAutomationError(f"剪映导出文件不存在：{source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.unlink(missing_ok=True)
        shutil.copy2(source, temporary)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise JianyingAutomationError(f"无法将导出视频保存到项目目录：{target}：{exc}") from exc
    try:
        source.unlink()
    except OSError:
        # The final project copy is complete. A media scanner may briefly keep
        # Jianying's original file open, so cleanup must not invalidate export.
        pass
    return target


def _macos_export_path(*, timeout: float) -> Path | None:
    """Read the exact output file shown in Jianying's export settings."""
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    set w to front window of p
    repeat with e in static texts of w
        try
            set v to value of e as text
            if v starts with "/" and (v ends with ".mp4" or v ends with ".mov" or v ends with ".m4v") then
                return v
            end if
        end try
        try
            set n to name of e as text
            if n starts with "/" and (n ends with ".mp4" or n ends with ".mov" or n ends with ".m4v") then
                return n
            end if
        end try
        try
            set d to description of e as text
            if d starts with "/" and (d ends with ".mp4" or d ends with ".mov" or d ends with ".m4v") then
                return d
            end if
        end try
    end repeat
    return "missing"
end tell
'''
    try:
        result = _run_macos_osascript(script, timeout=timeout)
    except JianyingAutomationError as exc:
        if "不能获得" in str(exc) or "无效的索引" in str(exc):
            return None
        raise
    if result == "missing":
        return None
    return _parse_export_path(result)


def _macos_confirm_exit_button_rect(*, timeout: float) -> tuple[float, float, float, float] | None:
    """Return the confirmation dialog's final exit button rectangle."""
    script = f'''
tell application "System Events"
    set p to first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}"
    repeat with b in buttons of front window of p
        try
            set n to name of b as text
            if n is "automationconfirmBtn" or n is "确认" or n is "确定" or n is "退出" or n is "退出剪映" then
                set q to position of b
                set s to size of b
                return ((item 1 of q) as text) & "," & ((item 2 of q) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
            end if
        end try
    end repeat
    return "missing"
end tell
'''
    try:
        result = _run_macos_osascript(script, timeout=timeout)
    except JianyingAutomationError as exc:
        if "不能获得" in str(exc) or "无效的索引" in str(exc):
            return None
        raise
    if result == "missing":
        return None
    try:
        x, y, width, height = (float(item) for item in result.split(","))
    except (TypeError, ValueError) as exc:
        raise JianyingAutomationError(f"无法读取剪映退出确认按钮位置：{result}") from exc
    return x, y, width, height


def _macos_process_running(*, timeout: float) -> bool:
    script = f'''
tell application "System Events"
    if exists (first application process whose bundle identifier is "{MACOS_JIANYING_BUNDLE_ID}") then
        return "running"
    end if
    return "stopped"
end tell
'''
    return _run_macos_osascript(script, timeout=timeout) == "running"


def _macos_quit_application(*, timeout: float) -> None:
    """Quit Jianying itself and verify that its GUI process has stopped."""
    if not _macos_process_running(timeout=min(timeout, 2.0)):
        return

    quit_error: JianyingAutomationError | None = None
    try:
        # This is the standard macOS Quit application event, equivalent to
        # choosing “退出剪映” from the app menu; it is not a process kill.
        _run_macos_osascript(
            f'''tell application id "{MACOS_JIANYING_BUNDLE_ID}" to quit''',
            timeout=min(timeout, 5.0),
        )
    except JianyingAutomationError as exc:
        # Jianying sometimes returns Apple event -128 (user canceled) even
        # though it has already terminated. The process check below is the
        # source of truth.
        quit_error = exc

    deadline = time.monotonic() + max(3.0, min(timeout, 10.0))
    confirmation_clicked = False
    while time.monotonic() < deadline:
        if not _macos_process_running(timeout=2.0):
            return
        if not confirmation_clicked:
            try:
                confirm_rect = _macos_confirm_exit_button_rect(timeout=1.0)
            except JianyingAutomationError:
                confirm_rect = None
            if confirm_rect is not None:
                _macos_focus_process(timeout=2.0)
                x, y, width, height = confirm_rect
                _macos_post_mouse_click(x + width / 2, y + height / 2)
                confirmation_clicked = True
        time.sleep(0.25)

    detail = f"：{quit_error}" if quit_error is not None else ""
    raise JianyingAutomationError(f"剪映已返回首页，但应用进程未能退出{detail}")


def _macos_app_running(app_path: Path) -> bool:
    executable = app_path / "Contents" / "MacOS"
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", str(executable)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _open_draft_macos(draft_path: Path, requested_name: str, *, timeout: float) -> Path:
    app_path = _find_macos_jianying_app()
    if app_path is None:
        raise JianyingAutomationError(
            "没有找到 macOS 剪映，请安装“剪映专业版”（VideoFusion-macOS）"
        )

    # Always start from the home screen. A previous failed run may have left
    # Jianying in an editor window; waiting for a home card in that state can
    # never succeed. Quit the idle editor through the normal application event
    # and relaunch it. Never interrupt an active export.
    if _macos_app_running(app_path):
        # Accessibility queries over a large editor timeline can take several
        # seconds even though they eventually succeed; do not turn that into
        # an ``unknown`` state and fall back to an impossible home-card wait.
        state = _macos_window_state(timeout=12.0)
        if state == "exporting":
            raise JianyingAutomationError("剪映正在导出，请等待当前导出完成后再操作")
        if state == "editor":
            _macos_quit_application(timeout=min(max(timeout, 10.0), 20.0))
            time.sleep(1.0)

    # Passing --draft_path can make Jianying duplicate the directory with a
    # "(1)" suffix, so open the app normally and select the local card.
    if not _macos_app_running(app_path):
        try:
            subprocess.Popen(
                [
                    "/usr/bin/open",
                    "-a",
                    str(app_path),
                ],
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise JianyingAutomationError(f"启动 macOS 剪映失败：{exc}") from exc

    deadline = time.monotonic() + timeout
    rect = None
    ui_name = draft_path.name
    ui_names = tuple(dict.fromkeys((draft_path.name, requested_name.strip())))
    search_sent = False
    search_started_at: float | None = None
    while time.monotonic() < deadline:
        try:
            _macos_focus_process(timeout=min(3.0, max(0.5, deadline - time.monotonic())))
            for candidate_name in ui_names:
                rect = _macos_home_draft_rect(candidate_name, timeout=3.0)
                if rect is not None:
                    ui_name = candidate_name
                    break
        except JianyingAutomationError:
            rect = None
        if rect is not None:
            break
        if not search_sent:
            search_sent = _macos_search_home_drafts(requested_name.strip(), timeout=5.0)
            if search_sent:
                search_started_at = time.monotonic()
        elif search_started_at is not None and time.monotonic() - search_started_at > 8.0:
            # The search field may retain a previous filter after a failed
            # run. Clear it once before giving up on the exact card.
            _macos_search_home_drafts("", timeout=5.0)
            search_started_at = None
        time.sleep(0.5)
    if rect is None:
        raise JianyingAutomationError(
            f"剪映首页没有找到名为“{requested_name.strip()}”的草稿，请先返回首页并刷新列表"
        )

    x, y, width, height = rect
    _macos_post_mouse_click(x + width / 2, y + height / 2, clicks=2)

    # A successful open replaces the home list with the editor window.  The
    # exact accessibility tree differs between Jianying builds, so the
    # historical ``VETreeMainCellItem:本地`` marker is only the preferred
    # signal.  Keep waiting for it, but accept a stable disappearance of the
    # home-card after a short grace period as a fallback.  Large drafts can
    # take tens of seconds to finish loading before the editor controls appear.
    home_missing_since: float | None = None
    fallback_grace_seconds = min(8.0, max(2.0, timeout * 0.25))
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            home_card = _macos_home_draft_rect(ui_name, timeout=2.0)
            if home_card is not None:
                home_missing_since = None
                continue
            if _macos_editor_ready(timeout=2.0):
                return draft_path
            if home_missing_since is None:
                home_missing_since = time.monotonic()
            if time.monotonic() - home_missing_since >= fallback_grace_seconds:
                # Ensure there is still a real front window before reporting
                # success; this filters out transient AX lookup failures.
                _macos_front_window_rect(timeout=2.0)
                return draft_path
        except JianyingAutomationError:
            pass
    raise JianyingAutomationError(f"打开剪映草稿失败：{draft_path.name}")


def open_draft(draft_folder: str | Path, draft_name: str, *, timeout: float = 30.0) -> Path:
    """Open an existing Jianying draft and return its validated path."""
    draft_path = validate_draft_path(draft_folder, draft_name)
    if os.name == "nt":
        return _open_draft_windows(draft_path, draft_name, timeout=timeout)
    if sys.platform == "darwin":
        return _open_draft_macos(draft_path, draft_name, timeout=timeout)
    raise JianyingAutomationError("剪映桌面自动化仅支持 Windows 和 macOS")


def _click_export_windows(*, timeout: float) -> Path | None:
    auto, window_api = _windows_helpers()
    # Jianying keeps the home page window alive while the editor is open.
    # Select the window that actually exposes the editor export control rather
    # than relying on the first process window returned by EnumWindows.
    deadline = time.monotonic() + timeout
    hwnd = None
    window = None
    button = None
    while time.monotonic() < deadline:
        for candidate_hwnd in _window_handles(JIANYING_PROCESS_NAME, window_api):
            candidate_window = auto.ControlFromHandle(candidate_hwnd)
            if candidate_window is None:
                continue
            remaining = min(0.8, max(0.1, deadline - time.monotonic()))
            candidate_button = _find_named_control(
                candidate_window,
                EXPORT_BUTTON_NAMES,
                timeout=remaining,
                contains=True,
            )
            if candidate_button is not None:
                hwnd = candidate_hwnd
                window = candidate_window
                button = candidate_button
                break
        if button is not None:
            break
        time.sleep(0.25)
    if button is None:
        raise JianyingAutomationError("没有找到剪映“导出”按钮，请确认草稿已经打开")
    _activate_window(hwnd, window_api)
    try:
        button.Click()
    except Exception as exc:
        raise JianyingAutomationError(f"点击导出失败：{exc}") from exc

    export_path_control = _find_named_control(
        window,
        ("ExportPathInput", "ExportPath"),
        timeout=min(timeout, 8.0),
    )
    export_path = None
    if export_path_control is not None:
        try:
            export_path_text = export_path_control.GetSiblingControl(lambda control: True)
            if export_path_text is not None:
                export_path = _parse_export_path(str(export_path_text.GetPropertyValue(30159) or ""))
        except Exception:
            export_path = None

    # The final button has used several internal names across Jianying
    # versions. Prefer internal identifiers, then allow the visible Chinese
    # labels as a compatibility fallback. Search every process window because
    # the export settings dialog may have its own HWND.
    final_button_hwnd, final_button_window, final_button = _find_windows_control(
        auto,
        window_api,
        (
            "ExportOkBtn",
            "ExportConfirmBtn",
            "ExportConfirmButton",
            "StartExportBtn",
            "StartExportButton",
            "ExportButton",
            "ExportBtn",
        ),
        timeout=min(timeout, 12.0),
        contains=True,
        preferred_hwnd=hwnd,
    )
    if final_button is None:
        final_button_hwnd, final_button_window, final_button = _find_windows_control(
            auto,
            window_api,
            ("开始导出", "确认导出", "导出视频"),
            timeout=min(timeout, 4.0),
            contains=True,
            preferred_hwnd=hwnd,
        )
    if final_button is None:
        raise JianyingAutomationError("已打开导出设置，但没有找到最终导出按钮")
    _activate_window(final_button_hwnd, window_api)
    try:
        final_button.Click()
    except Exception as exc:
        raise JianyingAutomationError(f"点击最终导出失败：{exc}") from exc

    success_hwnd, success_window, success_button = _find_windows_control(
        auto,
        window_api,
        ("ExportSucceedCloseBtn", "ExportSuccessCloseBtn", "关闭导出", "完成"),
        timeout=max(timeout, 1200.0),
        contains=True,
        preferred_hwnd=final_button_hwnd,
    )
    if success_button is None:
        raise JianyingAutomationError("导出已开始，但等待导出完成超时")
    _activate_window(success_hwnd, window_api)
    try:
        success_button.Click()
    except Exception as exc:
        raise JianyingAutomationError(f"关闭导出完成窗口失败：{exc}") from exc

    # Closing the editor returns to Jianying's still-running home window. Close
    # both windows so the UI action has the same end state as the macOS path.
    try:
        window_api.restore_and_focus(hwnd)
        window_api.close(hwnd)
    except Exception as exc:
        raise JianyingAutomationError(f"关闭剪映编辑器失败：{exc}") from exc

    close_deadline = time.monotonic() + max(15.0, min(max(timeout, 45.0), 60.0))
    no_window_since = None
    while time.monotonic() < close_deadline:
        handles = _window_handles(JIANYING_PROCESS_NAME, window_api)
        if not handles:
            if no_window_since is None:
                no_window_since = time.monotonic()
            elif time.monotonic() - no_window_since >= 1.0:
                break
            time.sleep(0.2)
            continue
        no_window_since = None
        confirmation_clicked = False
        for remaining_hwnd in handles:
            try:
                remaining_window = auto.ControlFromHandle(remaining_hwnd)
            except Exception:
                # The editor handle can disappear between EnumWindows and the
                # UIA lookup while Jianying restores its home window.
                continue
            if remaining_window is None:
                continue
            confirm_button = _find_named_control(
                remaining_window,
                ("automationconfirmBtn", "确认", "确定", "退出", "退出剪映", "OK", "是"),
                timeout=0.3,
                contains=True,
            )
            if confirm_button is not None:
                try:
                    confirm_button.Click()
                except Exception as exc:
                    raise JianyingAutomationError(f"确认退出剪映失败：{exc}") from exc
                confirmation_clicked = True
                break
        if not confirmation_clicked:
            for remaining_hwnd in handles:
                try:
                    window_api.restore_and_focus(remaining_hwnd)
                    # UIA's WindowControl.Close handles some modal Qt windows
                    # more reliably than posting a Win32 message.  Keep the
                    # Win32 path as the fallback because not every Jianying
                    # top-level window is exposed as a WindowControl.
                    remaining_window = auto.ControlFromHandle(remaining_hwnd)
                    close_method = getattr(remaining_window, "Close", None)
                    if callable(close_method):
                        try:
                            close_method()
                        except Exception:
                            window_api.close(remaining_hwnd)
                    else:
                        window_api.close(remaining_hwnd)
                except Exception as exc:
                    raise JianyingAutomationError(f"关闭剪映首页失败：{exc}") from exc
        time.sleep(0.4)
    else:
        # Export has already completed successfully.  Give Jianying one last
        # graceful close pass before reporting a real failure; a slow home
        # window must not turn a valid exported video into a failed operation.
        remaining_handles = _window_handles(JIANYING_PROCESS_NAME, window_api)
        process_ids = set()
        for remaining_hwnd in remaining_handles:
            try:
                process_ids.add(window_api.process_id(remaining_hwnd))
                window_api.restore_and_focus(remaining_hwnd)
                window_api.close(remaining_hwnd)
            except Exception:
                pass
        time.sleep(1.0)
        if not _window_handles(JIANYING_PROCESS_NAME, window_api):
            return export_path
        # At this point rendering is already confirmed complete. Jianying can
        # occasionally keep a Qt window alive after accepting WM_CLOSE; kill
        # only the captured Jianying process tree so the exported file remains
        # a successful result and no stale editor is left behind.
        terminate = getattr(window_api, "terminate_process_tree", None)
        if callable(terminate):
            for pid in process_ids:
                try:
                    terminate(pid)
                except Exception:
                    pass
            time.sleep(1.0)
            if not _window_handles(JIANYING_PROCESS_NAME, window_api):
                return export_path
        raise JianyingAutomationError("导出已完成，但关闭剪映窗口超时")
    return export_path


def _click_export_macos(*, timeout: float, target_pid: int | None = None) -> Path | None:
    del target_pid  # Kept in the public signature for compatibility.
    _macos_focus_process(timeout=timeout)
    x, y, width, _height = _macos_front_window_rect(timeout=timeout)
    # The Qt editor exposes the export control visually but not through AX.
    # It is anchored in the title bar, so this remains stable across window sizes.
    _macos_post_mouse_click(x + width - 45, y + 20)
    deadline = time.monotonic() + min(timeout, 8.0)
    while time.monotonic() < deadline:
        time.sleep(0.4)
        if _macos_export_panel_open(timeout=2.0):
            break
    else:
        raise JianyingAutomationError("已打开草稿，但剪映导出窗口没有出现")

    export_path = _macos_export_path(timeout=2.0)

    # The first click only opens export settings.  The actual export is
    # started by a second button in the dialog (ExportOkBtn in current builds).
    button_rect = None
    button_deadline = time.monotonic() + min(timeout, 8.0)
    while time.monotonic() < button_deadline:
        button_rect = _macos_export_button_rect(timeout=2.0)
        if button_rect is not None:
            break
        time.sleep(0.25)
    if button_rect is None:
        # Older builds may not expose the button through Accessibility, but
        # retain the same bottom-right layout inside the export dialog.
        panel_x, panel_y, panel_width, panel_height = _macos_front_window_rect(timeout=2.0)
        button_rect = (panel_x + panel_width - 115, panel_y + panel_height - 28, 72, 20)

    # Coordinate clicks go to whichever application is currently active. Raise
    # Jianying again in case another application stole focus while the dialog loaded.
    _macos_focus_process(timeout=2.0)
    button_x, button_y, button_width, button_height = button_rect
    _macos_post_mouse_click(
        button_x + button_width / 2,
        button_y + button_height / 2,
    )

    # Wait for the progress page to turn into the completion page.  Jianying
    # may take several minutes for a long project, so use the same 20-minute
    # upper bound as the vendor controller while keeping short test timeouts.
    completion_deadline = time.monotonic() + max(timeout, 1200.0)
    closed_since = None
    while time.monotonic() < completion_deadline:
        time.sleep(0.4)
        try:
            state = _macos_export_state(timeout=2.0)
        except JianyingAutomationError:
            # Jianying can temporarily stop responding to Accessibility
            # queries while rendering. A single AX timeout is not an export
            # failure; keep polling until the completion deadline.
            state = "unknown"
        if state == "complete":
            break
        if state == "closed":
            if closed_since is None:
                closed_since = time.monotonic()
            elif time.monotonic() - closed_since > 5.0:
                raise JianyingAutomationError("剪映导出窗口意外关闭，无法确认导出是否完成")
        else:
            closed_since = None
    else:
        raise JianyingAutomationError("导出已开始，但等待导出完成超时")

    # The completion page has no reliable AX button name on macOS.  Its close
    # button is consistently anchored at the bottom-right of the 640x428 page.
    _macos_focus_process(timeout=2.0)
    x, y, width, height = _macos_front_window_rect(timeout=2.0)
    _macos_post_mouse_click(x + width - 52, y + height - 27)
    time.sleep(0.5)

    # Close the editor window itself (the red window button), leaving Jianying
    # at its home screen temporarily depending on the installed build.
    _macos_focus_process(timeout=2.0)
    editor_rect = _macos_front_window_rect(timeout=2.0)
    x, y, _width, _height = editor_rect
    _macos_post_mouse_click(x + 16, y + 16)

    # Current Jianying builds keep the home page in a second window. Close it
    # as well so step 09 leaves no Jianying window behind.
    time.sleep(0.5)
    try:
        _macos_focus_process(timeout=2.0)
        home_rect = _macos_front_window_rect(timeout=2.0)
    except JianyingAutomationError:
        home_rect = None
    # Recent Jianying builds reuse the editor window (including its exact
    # geometry) when returning to the home page. The presence of a remaining
    # front window is sufficient; comparing rectangles can incorrectly skip
    # the final close and leave Jianying open on the draft list.
    if home_rect is not None:
        home_x, home_y, _home_width, _home_height = home_rect
        _macos_post_mouse_click(home_x + 16, home_y + 16)

        # If Jianying still has a background task, quitting the home window
        # opens a final "确定要退出吗?" dialog. Confirm it rather than leaving
        # the application running behind the pipeline UI.
        time.sleep(0.5)
        confirm_rect = _macos_confirm_exit_button_rect(timeout=2.0)
        if confirm_rect is not None:
            _macos_focus_process(timeout=2.0)
            confirm_x, confirm_y, confirm_width, confirm_height = confirm_rect
            _macos_post_mouse_click(
                confirm_x + confirm_width / 2,
                confirm_y + confirm_height / 2,
            )

    # Closing the traffic-light button only closes a window in some Jianying
    # versions. Send an application-level quit request and verify the process
    # is actually gone before reporting step 09 as complete.
    _macos_quit_application(timeout=max(timeout, 10.0))
    return export_path


def click_export(*, timeout: float = 30.0, target_pid: int | None = None) -> Path | None:
    """Open Jianying's export settings and start the export."""
    if os.name == "nt":
        return _click_export_windows(timeout=timeout)
    elif sys.platform == "darwin":
        return _click_export_macos(timeout=timeout, target_pid=target_pid)
    else:
        raise JianyingAutomationError("剪映桌面自动化仅支持 Windows 和 macOS")


def open_draft_and_click_export_with_path(
    draft_folder: str | Path,
    draft_name: str,
    *,
    timeout: float = 30.0,
    target_path: Path | None = None,
) -> tuple[Path, Path | None]:
    path = open_draft(draft_folder, draft_name, timeout=timeout)
    export_path = click_export(timeout=timeout)
    if target_path is not None:
        if export_path is None:
            raise JianyingAutomationError("剪映导出完成，但无法读取生成的视频路径")
        export_path = relocate_exported_video(export_path, target_path)
    return path, export_path


def open_draft_and_click_export(
    draft_folder: str | Path,
    draft_name: str,
    *,
    timeout: float = 30.0,
) -> Path:
    path, _export_path = open_draft_and_click_export_with_path(
        draft_folder,
        draft_name,
        timeout=timeout,
    )
    return path
