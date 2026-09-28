"""Seller-only desktop dialog for issuing offline licenses."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .issue_license import issue_license


class LicenseIssuerDialog(QDialog):
    """Generate a signed license without using the command line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("许可证签发工具")
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        intro = QLabel("卖家专用工具：私钥只从本机读取，不会上传。请勿把此工具或私钥发给客户。")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #aeb6c2;")
        root.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.private_key_input = QLineEdit(
            str(Path.home() / ".donghuakoubo-release" / "private_key.pem")
        )
        form.addRow(
            "签发私钥",
            self._path_row(self.private_key_input, "选择私钥", "PEM 文件 (*.pem);;所有文件 (*)"),
        )

        self.machine_input = QLineEdit()
        self.machine_input.setPlaceholderText("粘贴客户软件显示的机器码")
        form.addRow("客户机器码", self.machine_input)

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("例如：张三 / XX工作室")
        form.addRow("客户名称", self.customer_input)

        self.days_input = QSpinBox()
        self.days_input.setRange(1, 3650)
        self.days_input.setValue(365)
        self.days_input.setSuffix(" 天")
        self.days_input.valueChanged.connect(self._sync_expiry)
        form.addRow("授权时长", self.days_input)

        self.expiry_input = QDateEdit()
        self.expiry_input.setCalendarPopup(True)
        self.expiry_input.setDisplayFormat("yyyy-MM-dd")
        self.expiry_input.setDate(QDate.currentDate().addDays(self.days_input.value()))
        form.addRow("到期日期", self.expiry_input)

        feature_row = QHBoxLayout()
        self.feature_checks = {
            "image": QCheckBox("图片生成"),
            "voice": QCheckBox("配音"),
            "render": QCheckBox("视频渲染"),
        }
        for checkbox in self.feature_checks.values():
            checkbox.setChecked(True)
            feature_row.addWidget(checkbox)
        feature_row.addStretch(1)
        form.addRow("功能权限", feature_row)

        self.output_input = QLineEdit(
            str(Path.home() / "Desktop" / "customer-license.json")
        )
        form.addRow(
            "保存位置",
            self._path_row(
                self.output_input,
                "选择保存位置",
                "许可证文件 (*.json);;所有文件 (*)",
                save=True,
            ),
        )
        root.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #9ca3af;")
        root.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        issue_button = QPushButton("生成许可证")
        issue_button.setObjectName("primary")
        issue_button.clicked.connect(self._issue)
        actions.addWidget(close_button)
        actions.addWidget(issue_button)
        root.addLayout(actions)

    def _path_row(
        self,
        field: QLineEdit,
        title: str,
        file_filter: str,
        *,
        save: bool = False,
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("浏览")
        button.setToolTip(title)
        if save:
            button.clicked.connect(lambda: self._choose_output(field, file_filter))
        else:
            button.clicked.connect(lambda: self._choose_file(field, title, file_filter))
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return row

    def _choose_file(self, field: QLineEdit, title: str, file_filter: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title, field.text(), file_filter)
        if path:
            field.setText(path)

    def _choose_output(self, field: QLineEdit, file_filter: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择许可证保存位置",
            field.text(),
            file_filter,
        )
        if path:
            field.setText(path)

    def _sync_expiry(self, days: int) -> None:
        self.expiry_input.setDate(QDate.currentDate().addDays(days))

    def _issue(self) -> None:
        private_key = Path(self.private_key_input.text().strip()).expanduser()
        machine_code = self.machine_input.text().strip().upper()
        customer = self.customer_input.text().strip()
        output = Path(self.output_input.text().strip()).expanduser()
        features = [name for name, checkbox in self.feature_checks.items() if checkbox.isChecked()]

        if not private_key.is_file():
            QMessageBox.warning(self, "缺少私钥", f"找不到签发私钥：\n{private_key}")
            return
        if len(machine_code) < 16:
            QMessageBox.warning(self, "机器码无效", "请粘贴客户软件显示的完整机器码。")
            return
        if not customer:
            QMessageBox.warning(self, "缺少客户名称", "请填写客户名称，方便后续管理许可证。")
            return
        if not output.name:
            QMessageBox.warning(self, "保存位置无效", "请选择许可证保存位置。")
            return
        if not features:
            QMessageBox.warning(self, "未选择功能", "至少选择一项功能权限。")
            return
        try:
            document = issue_license(
                private_key_path=private_key,
                machine_code=machine_code,
                customer=customer,
                expires_at=self.expiry_input.date().toPython(),
                features=features,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.name}.tmp")
            temporary.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(output)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "签发失败", str(exc))
            return
        self.status_label.setText(f"已生成许可证：{output}")
        QMessageBox.information(
            self,
            "签发成功",
            f"许可证已生成：\n{output}\n\n现在可以把这个文件发给客户。",
        )


def main() -> int:
    """Launch the seller-only issuer window for local use."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("动画口播许可证签发工具")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    dialog = LicenseIssuerDialog()
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
