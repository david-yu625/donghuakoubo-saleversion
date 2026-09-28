"""Small local activation dialog used before opening the main window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .license import LicenseError, current_machine_code, load_license, save_license, verify_license


class ActivationDialog(QDialog):
    """Ask the customer to import the license issued for this device."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("激活动画口播智能体")
        self.setMinimumWidth(560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        title = QLabel("需要激活后才能使用")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel("请把下面的机器码发给软件提供方，收到许可证文件后导入即可。"))

        machine_row = QHBoxLayout()
        self.machine_input = QLineEdit(current_machine_code())
        self.machine_input.setReadOnly(True)
        copy_button = QPushButton("复制机器码")
        copy_button.clicked.connect(self._copy_machine_code)
        machine_row.addWidget(self.machine_input, 1)
        machine_row.addWidget(copy_button)
        layout.addLayout(machine_row)

        self.status = QLabel("未检测到有效许可证")
        self.status.setStyleSheet("color: #aeb6c2;")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        import_button = QPushButton("导入许可证")
        import_button.setObjectName("primary")
        import_button.clicked.connect(self._import_license)
        quit_button = QPushButton("退出")
        quit_button.clicked.connect(self.reject)
        buttons.addWidget(quit_button)
        buttons.addWidget(import_button)
        layout.addLayout(buttons)

    def _copy_machine_code(self) -> None:
        self.machine_input.selectAll()
        self.machine_input.copy()
        self.machine_input.deselect()
        self.status.setText("机器码已复制")

    def _import_license(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "选择许可证文件",
            str(Path.home()),
            "许可证文件 (*.json);;所有文件 (*)",
        )
        if not path_text:
            return
        try:
            document = load_license(Path(path_text))
            info = verify_license(document)
            save_license(document)
        except LicenseError as exc:
            QMessageBox.warning(self, "许可证无效", str(exc))
            return
        self.status.setText(f"已激活：{info.customer or '授权用户'}，有效期至 {info.expires_at.isoformat()}")
        self.accept()


def ensure_license() -> bool:
    """Validate the cached license or show the one-time activation dialog."""
    try:
        verify_license(load_license())
        return True
    except LicenseError:
        dialog = ActivationDialog()
        return dialog.exec() == QDialog.DialogCode.Accepted
