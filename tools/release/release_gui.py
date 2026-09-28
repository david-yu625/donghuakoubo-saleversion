"""Graphical launcher for the customer release builder."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = Path(__file__).resolve().with_name("build_release.py")
DEFAULT_OUTPUT = ROOT / "release"
DEFAULT_NAME = "DonghuaKoubo"
CURRENT_PLATFORM = {
    "win32": "windows",
    "darwin": "macos",
}.get(sys.platform, "linux")


class ReleaseWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("动画口播智能体 · 发版工具")
        self.setMinimumSize(720, 520)
        self.process: QProcess | None = None

        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(14)

        title = QLabel("客户版发包")
        title.setObjectName("title")
        layout.addWidget(title)
        intro = QLabel(
            "在当前电脑生成客户版程序。Windows 和 macOS 需要分别在对应系统上构建，"
            "客户包不会直接包含项目 .py 源文件。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        platform_value = QLabel({"windows": "Windows", "macos": "macOS", "linux": "Linux"}[CURRENT_PLATFORM])
        platform_value.setObjectName("value")
        form.addRow("构建平台", platform_value)

        self.name_input = QLineEdit(DEFAULT_NAME)
        self.name_input.setPlaceholderText("例如：DonghuaKoubo")
        self.name_input.setToolTip("只能使用字母、数字、下划线和短横线")
        form.addRow("版本名称", self.name_input)

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self.output_input = QLineEdit(str(DEFAULT_OUTPUT))
        browse = QPushButton("选择目录")
        browse.clicked.connect(self.choose_output)
        output_layout.addWidget(self.output_input, 1)
        output_layout.addWidget(browse)
        form.addRow("输出目录", output_row)
        layout.addLayout(form)

        self.clean_checkbox = QCheckBox("清理旧构建并覆盖同名客户包")
        self.clean_checkbox.setChecked(True)
        layout.addWidget(self.clean_checkbox)

        self.keep_work_checkbox = QCheckBox("保留构建中间文件（仅排查问题时使用）")
        self.keep_work_checkbox.setChecked(False)
        layout.addWidget(self.keep_work_checkbox)

        actions = QHBoxLayout()
        actions.addStretch()
        self.build_button = QPushButton("开始发包")
        self.build_button.setObjectName("primary")
        self.build_button.setMinimumWidth(132)
        self.build_button.clicked.connect(self.start_build)
        actions.addWidget(self.build_button)
        layout.addLayout(actions)

        log_label = QLabel("构建日志")
        log_label.setObjectName("section")
        layout.addWidget(log_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("点击“开始发包”后，构建进度会显示在这里。")
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log, 1)

        self.status = QLabel("就绪")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.setCentralWidget(page)
        self.setStyleSheet(
            """
            QWidget#page { background: #11141a; color: #e5e7eb; }
            QLabel#title { color: #ffffff; font-size: 21px; font-weight: 600; }
            QLabel#section { color: #f3f4f6; font-size: 14px; font-weight: 600; }
            QLabel#muted { color: #98a2b3; }
            QLabel#value { color: #dce1e8; }
            QLineEdit, QPlainTextEdit {
                color: #f3f4f6; background: #0b0d10;
                border: 1px solid #303641; border-radius: 4px;
                padding: 7px;
            }
            QLineEdit:focus { border-color: #4f8cff; }
            QPlainTextEdit { font-family: Consolas, monospace; }
            QPushButton {
                min-height: 34px; padding: 0 14px; color: #dce1e8;
                background: #252a33; border: 1px solid #343b47; border-radius: 4px;
            }
            QPushButton:hover { background: #303641; border-color: #46505f; }
            QPushButton#primary { color: #ffffff; background: #3978e6; border-color: #3978e6; font-weight: 600; }
            QPushButton#primary:hover { background: #4f8cff; border-color: #4f8cff; }
            QPushButton:disabled { color: #687384; background: #1b1e24; border-color: #262a31; }
            QCheckBox { spacing: 7px; }
            """
        )

    def choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择发版输出目录", self.output_input.text())
        if selected:
            self.output_input.setText(selected)

    def _append_output(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.insertPlainText(data)
            self.log.ensureCursorVisible()

    def start_build(self) -> None:
        name = self.name_input.text().strip()
        output_text = self.output_input.text().strip()
        output = Path(output_text).expanduser()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            QMessageBox.warning(self, "版本名称无效", "版本名称只能包含字母、数字、下划线和短横线。")
            self.name_input.setFocus()
            return
        if not output_text:
            QMessageBox.warning(self, "输出目录为空", "请选择发版输出目录。")
            return

        command = [
            sys.executable,
            str(BUILD_SCRIPT),
            "--platform",
            CURRENT_PLATFORM,
            "--name",
            name,
            "--output",
            str(output),
        ]
        if self.clean_checkbox.isChecked():
            command.append("--clean")
        if self.keep_work_checkbox.isChecked():
            command.append("--keep-work")

        self.log.clear()
        self.log.appendPlainText("开始构建客户版……\n")
        self.status.setText("构建中，请不要关闭窗口")
        self.build_button.setEnabled(False)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._append_output)
        self.process.finished.connect(self.build_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start(command[0], command[1:])

    def process_error(self, _error: QProcess.ProcessError) -> None:
        if self.process is not None and self.process.state() == QProcess.ProcessState.NotRunning:
            self.status.setText("启动构建失败")

    def build_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self._append_output()
        success = exit_code == 0
        self.status.setText("发版完成" if success else f"发版失败（退出码 {exit_code}）")
        self.build_button.setEnabled(True)
        self.process = None
        if success:
            QMessageBox.information(self, "发版完成", "客户版已经生成，请到输出目录查看。")
        else:
            QMessageBox.warning(self, "发版失败", "构建没有完成，请查看下方日志。")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("动画口播智能体发版工具")
    window = ReleaseWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
