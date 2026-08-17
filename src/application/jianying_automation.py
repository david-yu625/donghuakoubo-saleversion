"""Best-effort Windows UI automation for opening and exporting Jianying drafts.

This module is intentionally separate from the 01-08 production pipeline.  It
only operates on a draft that already exists in Jianying's draft directory.
"""

from __future__ import annotations

import os
import subprocess
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Iterable


class JianyingAutomationError(RuntimeError):
    """Raised when Jianying cannot be reached or a requested UI action fails."""


JIANYING_PROCESS_NAME = "JianyingPro.exe"
EXPORT_BUTTON_NAMES = ("导出", "导出视频")


def validate_draft_path(draft_folder: str | Path, draft_name: str) -> Path:
    folder = Path(draft_folder).expanduser().resolve()
    name = draft_name.strip()
    if not name:
        raise JianyingAutomationError("草稿名不能为空")
    if Path(name).name != name or name in {".", ".."}:
        raise JianyingAutomationError("草稿名不能包含目录路径")
    draft_path = folder / name
    if not draft_path.is_dir():
        raise JianyingAutomationError(f"找不到剪映草稿：{draft_path}")
    return draft_path


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
        raise JianyingAutomationError("剪映桌面自动化仅支持 Windows")
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
            try:
                control_name = control.Name
                if control_name in names or (contains and any(name in control_name for name in names)):
                    return control
            except Exception:
                continue
        time.sleep(0.4)
    return None


def _activate_window(hwnd: int, window_api: _WindowsWindowApi) -> None:
    try:
        window_api.restore_and_focus(hwnd)
    except Exception:
        pass


def open_draft(draft_folder: str | Path, draft_name: str, *, timeout: float = 30.0) -> Path:
    """Open an existing draft card in Jianying and return its validated path."""
    draft_path = validate_draft_path(draft_folder, draft_name)
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

    # Jianying exposes project cards as UIA controls on supported versions.
    # We require an exact name match so a similarly named project is never opened.
    card = _find_named_control(window, (draft_name.strip(),), timeout=timeout)
    if card is None:
        raise JianyingAutomationError(
            f"剪映中没有找到名为“{draft_name.strip()}”的草稿，请先在项目首页刷新列表"
        )
    try:
        card.DoubleClick()
    except Exception as exc:
        raise JianyingAutomationError(f"打开草稿失败：{exc}") from exc
    return draft_path


def click_export(*, timeout: float = 30.0) -> None:
    """Click Jianying's export button, leaving export options for user confirmation."""
    auto, window_api = _windows_helpers()
    hwnd, window = _wait_for_window(auto, window_api, JIANYING_PROCESS_NAME, timeout)
    _activate_window(hwnd, window_api)
    button = _find_named_control(window, EXPORT_BUTTON_NAMES, timeout=timeout, contains=True)
    if button is None:
        raise JianyingAutomationError("没有找到剪映“导出”按钮，请确认草稿已经打开")
    try:
        button.Click()
    except Exception as exc:
        raise JianyingAutomationError(f"点击导出失败：{exc}") from exc


def open_draft_and_click_export(
    draft_folder: str | Path,
    draft_name: str,
    *,
    timeout: float = 30.0,
) -> Path:
    path = open_draft(draft_folder, draft_name, timeout=timeout)
    click_export(timeout=timeout)
    return path
