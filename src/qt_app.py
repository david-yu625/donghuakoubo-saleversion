"""PySide6 desktop client for the animation narration pipeline."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import uuid
import wave
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QCheckBox,
    QDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_settings import (
    APP_SETTING_KEYS,
    APP_SETTINGS_PATH,
    migrate_legacy_app_settings,
    save_app_settings,
)
from .env import load_env_file
from .core.speech_metrics import (
    count_speech_chars,
    estimate_speech_duration_range,
    estimate_speech_duration_seconds,
)
from .application.image_review import ImageReviewItem, load_image_review_items
from .application.landscape_projects import (
    LandscapeProject,
    PortraitPackageState,
    discover_landscape_projects,
    find_matching_landscape_video,
    load_portrait_package_state,
    save_portrait_package_state,
)
from .application.jianying_automation import (
    JianyingAutomationError,
    find_timestamp_matching_draft,
    open_draft_and_click_export_with_path,
    validate_draft_path,
)
from .application.douyin_publisher import (
    DEFAULT_DOUYIN_COLLECTION,
    DouyinPublishError,
    DouyinPublishRequest,
    discover_publish_assets,
    generate_publish_metadata,
    open_douyin_upload_page,
    prepare_douyin_publish,
    publish_to_douyin,
)
from .paths import portrait_package_dir, resolve_draft_folder, video_export_path
from .pipeline_runtime import (
    API_FIELDS,
    API_DEFAULTS,
    DEFAULT_BGM_PATH,
    DEFAULT_DRAFT_FOLDER,
    DEFAULT_IMAGE_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    ENV_PATH,
    OUTPUT_ROOT,
    draft_name_for_orientation,
    orientation_key,
    PROJECT_ROOT,
    STEP_DEFS,
    STEP_BUTTON_DESCRIPTIONS,
    Options,
    IMAGE_MODEL_CHOICES,
    IMAGE_QUALITY_CHOICES,
    SETTING_FIELDS,
    SUBTITLE_FONT_CHOICES,
    TITLE_FONT_CHOICES,
    TTS_VOICE_DOC_URL,
    VISUAL_THEME_CHOICES,
    VIDEO_ORIENTATION_CHOICES,
    Runner,
    build_batch_options,
    build_cover_command,
    build_image_regeneration_command,
    build_portrait_package_command,
    default_background_image,
    resolve_visual_theme,
    reuse_completed_materials,
    safe_topic,
    parse_batch_topics,
    update_env_file,
    save_copywriting_text,
)
from .prepare.cover import (
    COVER_SIZE_OPTIONS,
    DEFAULT_COVER_SIZE_KEY,
    build_cover_prompt,
    resolve_cover_size,
)
from .prepare.copywriting import revise_copywriting
from .prepare.topic_generation import generate_unique_topics, record_topic


WORKFLOW_LANDSCAPE = "\u6a2a\u7248\u6210\u7247\uff08\u6807\u9898+\u5b57\u5e55\uff09"
WORKFLOW_PORTRAIT_PACKAGE = "\u6a2a\u7248\u6bcd\u7247\u8f6c\u7ad6\u7248"
WORKFLOW_NATIVE_PORTRAIT = "\u539f\u751f\u7ad6\u7248\u6210\u7247"
WORKFLOW_COVER = "\u751f\u6210\u4f5c\u54c1\u5c01\u9762"
WORKFLOW_PUBLISH = "\u53d1\u5e03\u4f5c\u54c1"
UI_STATE_PATH = OUTPUT_ROOT / "ui_state.json"
PROJECT_PANEL_COLLAPSED_HEIGHT = 76


STYLE_SHEET = """
QWidget {
    background: #0f1115;
    color: #e5e7eb;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 13px;
}
QMainWindow { background: #0b0d10; }
QLabel { background: transparent; }
QLabel#formLabel { color: #aeb6c2; background: transparent; }
QWidget#panelBody, QWidget#formField { background: transparent; }
QCheckBox { background: transparent; spacing: 7px; }
QTabWidget::pane { border: 0; background: #0f1115; }
QTabBar::tab {
    min-width: 104px; padding: 12px 18px; margin-right: 2px;
    color: #8b95a5; background: #0b0d10; border: 0;
}
QTabBar::tab:selected { color: #ffffff; background: #171a20; border-bottom: 2px solid #4f8cff; }
QTabBar::tab:hover:!selected { color: #d1d5db; background: #14171c; }
QFrame#panel { background: #15181e; border: 1px solid #252a33; border-radius: 6px; }
QFrame#workflowPanel { background: #15181e; border: 1px solid #252a33; border-radius: 6px; }
QFrame#workflowContent { background: transparent; border: 0; }
QFrame#stepRow { background: transparent; border-bottom: 1px solid #242932; }
QLabel#appTitle { color: #ffffff; font-size: 20px; font-weight: 600; }
QLabel#sectionTitle { color: #f3f4f6; font-size: 14px; font-weight: 600; }
QLabel#muted { color: #778190; font-size: 11px; background: transparent; }
QLabel#stageStatus { color: #687384; font-size: 11px; background: transparent; }
QLabel#stepTitle { color: #f0f2f5; font-weight: 600; }
QLabel#status {
    color: #9ca3af; background: #242932; border: 1px solid #303641;
    border-radius: 9px; padding: 2px 8px; font-size: 11px;
}
QLineEdit, QComboBox {
    min-height: 34px; padding: 0 10px; color: #f3f4f6;
    background: #0e1014; border: 1px solid #303641; border-radius: 4px;
    selection-background-color: #315a9b;
}
QLineEdit:hover, QComboBox:hover { border-color: #46505f; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #4f8cff; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView {
    color: #f3f4f6; background: #171a20; border: 1px solid #303641;
    selection-background-color: #315a9b;
}
QPushButton {
    min-height: 34px; padding: 0 14px; color: #dce1e8;
    background: #252a33; border: 1px solid #343b47; border-radius: 4px;
}
QPushButton:hover { background: #303641; border-color: #46505f; }
QPushButton:pressed { background: #1f242c; }
QPushButton:disabled { color: #5d6571; background: #1b1e24; border-color: #262a31; }
QPushButton#primary { color: #ffffff; background: #3978e6; border-color: #3978e6; font-weight: 600; }
QPushButton#primary:hover { background: #4f8cff; border-color: #4f8cff; }
QPushButton#primary:disabled {
    color: #5d6571; background: #1b1e24; border-color: #262a31;
}
QFrame#stageNavBar { background: transparent; border-bottom: 1px solid #252a33; }
QPushButton#stageNav {
    min-height: 42px; padding: 0 14px; text-align: center;
    color: #aeb6c2; background: transparent; border: 0; border-radius: 4px;
}
QPushButton#stageNav:hover { color: #f3f4f6; background: #171a20; }
QPushButton#stageNav:checked {
    color: #ffffff; background: #1b2535; border-bottom: 3px solid #4f8cff; font-weight: 600;
}
QPushButton#modeSegment {
    min-height: 32px; padding: 0 14px; color: #9ca3af;
    background: #15181e; border: 1px solid #303641; border-radius: 4px;
}
QPushButton#modeSegment:hover { color: #f3f4f6; background: #1c2027; }
QPushButton#modeSegment:checked {
    color: #ffffff; background: #315a9b; border-color: #4f8cff; font-weight: 600;
}
QFrame#workflowActions { background: transparent; border-bottom: 1px solid #252a33; }
QPushButton#describedAction QLabel#describedActionTitle {
    color: #dce1e8; background: transparent; border: none;
}
QPushButton#describedAction QLabel#describedActionDescription {
    color: #9ca3af; background: transparent; border: none;
}
QPushButton#describedAction:disabled QLabel#describedActionTitle {
    color: #5d6571;
}
QPushButton#describedAction:disabled QLabel#describedActionDescription {
    color: #4b5563;
}
QPushButton#danger { color: #ff9b91; background: transparent; border-color: #4b3030; }
QPushButton#danger:hover { color: #ffffff; background: #702c2c; border-color: #8c3b3b; }
QPlainTextEdit {
    padding: 10px; color: #c7d0dc; background: #0b0d10;
    border: 0; selection-background-color: #315a9b;
    font-family: Consolas; font-size: 12px;
}
QPlainTextEdit#batchTopics {
    padding: 8px 10px; color: #f3f4f6; background: #0e1014;
    border: 1px solid #303641; border-radius: 4px;
    font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 13px;
}
QPlainTextEdit#batchTopics:focus { border: 1px solid #4f8cff; }
QPlainTextEdit#contextInput {
    padding: 8px 10px; color: #f3f4f6; background: #0e1014;
    border: 1px solid #303641; border-radius: 4px;
    font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 13px;
}
QPlainTextEdit#contextInput:focus { border: 1px solid #4f8cff; }
QScrollBar:vertical { width: 10px; background: #0b0d10; }
QScrollBar::handle:vertical { min-height: 30px; background: #343a45; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #4a5260; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { width: 8px; height: 8px; background: #0f1115; }
QToolButton {
    width: 28px; height: 28px; background: transparent;
    border: 1px solid transparent; border-radius: 4px;
}
QToolButton:hover { background: #252a33; border-color: #343b47; }
QToolTip { color: #f3f4f6; background: #252a33; border: 1px solid #46505f; padding: 5px; }
"""

RERUN_ACTIONS = {
    "copy": "重新生成文案",
    "voice": "重新生成配音",
    "shots": "重新生成分镜",
    "storyboard_prompts": "重新生成图片内容",
    "prompts": "重新生成生图提示词",
    "images": "重新生成图片",
    "layout": "重新编译布局",
    "draft": "重新生成草稿",
    "infinite_prepare": "重新准备素材",
    "infinite_plan": "重新生成规划",
    "infinite_frames": "重新渲染画面",
    "infinite_encode": "重新编码成片",
}

UI_STEP_DEFS = (*STEP_DEFS, ("automation", "09 剪映导出", "", "执行剪映导出", ""))
INFINITE_STAGE_DEFS = (
    ("infinite_prepare", "07 准备素材", "out/source.json", "整理图片、配音和分镜", ""),
    ("infinite_plan", "08 规划镜头", "public/manifest.json", "决定画面位置和镜头运动", ""),
    ("infinite_frames", "09 生成画面", "out/frames", "按规划渲染动画帧", ""),
    ("infinite_encode", "10 合成视频", "", "把画面帧和配音合成 MP4", ""),
)
INFINITE_STAGE_DESCRIPTIONS = {
    "infinite_prepare": "把共享步骤生成的图片、配音和分镜整理成无限画布能读取的素材。不会生成新图片。",
    "infinite_plan": "决定每张图片放在大画布的什么位置，并规划推近、拉远、移动和字幕时间。",
    "infinite_frames": "按照空间规划逐帧生成动画画面。此时得到的是一组 JPEG 帧，还不是最终视频。",
    "infinite_encode": "把动画帧和旁白编码成最终 MP4，并写入当前主题的 output 目录。",
}
ALL_STEP_DEFS = (*STEP_DEFS, ("automation", "09 剪映导出", "", "执行剪映导出", ""), *INFINITE_STAGE_DEFS)


class PreviewImageLabel(QLabel):
    """Keep the settings guide image contained without distorting its ratio."""

    def __init__(self, pixmap: QPixmap | None = None) -> None:
        super().__init__()
        self._pixmap = pixmap or QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #0b0d10; border: 1px solid #303641; border-radius: 4px;")
        self._refresh_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._pixmap.isNull():
            self.setText("设置预览图不可用")
            return
        margins = self.contentsMargins()
        target = self.size() - QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        target = QSize(max(1, target.width()), max(1, target.height()))
        self.setPixmap(self._pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class DescribedActionButton(QPushButton):
    """Action button whose embedded labels follow the button enabled state."""

    ENABLED_TITLE_COLOR = "#dce1e8"
    ENABLED_DESCRIPTION_COLOR = "#9ca3af"
    DISABLED_TITLE_COLOR = "#5d6571"
    DISABLED_DESCRIPTION_COLOR = "#4b5563"

    def set_action_labels(self, title_label: QLabel, description_label: QLabel) -> None:
        self._title_label = title_label
        self._description_label = description_label
        self._sync_action_label_colors()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._sync_action_label_colors()

    def _sync_action_label_colors(self) -> None:
        title_label = getattr(self, "_title_label", None)
        description_label = getattr(self, "_description_label", None)
        if title_label is None or description_label is None:
            return
        title_color = self.ENABLED_TITLE_COLOR if self.isEnabled() else self.DISABLED_TITLE_COLOR
        description_color = (
            self.ENABLED_DESCRIPTION_COLOR
            if self.isEnabled()
            else self.DISABLED_DESCRIPTION_COLOR
        )
        title_label.setStyleSheet(
            f"color: {title_color}; background: transparent; border: none;"
        )
        description_label.setStyleSheet(
            f"color: {description_color}; font-size: 10px; background: transparent; "
            "border: none; border-left: 1px solid #3a414d; padding-left: 8px;"
        )


class PipelineWindow(QMainWindow):
    preview_succeeded = Signal(str)
    preview_failed = Signal(str)
    jianying_automation_succeeded = Signal(str)
    jianying_automation_failed = Signal(str)
    douyin_publish_succeeded = Signal(str)
    douyin_publish_failed = Signal(str)
    douyin_publish_prepared = Signal(str)
    douyin_metadata_succeeded = Signal(object)
    douyin_metadata_failed = Signal(str)
    batch_topics_generated = Signal(object)
    topic_generation_progress = Signal(str)
    topic_generation_failed = Signal(str)
    copy_revision_succeeded = Signal(str)
    copy_revision_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.app_settings = migrate_legacy_app_settings(ENV_PATH, APP_SETTINGS_PATH)
        load_env_file(ENV_PATH)
        for key in APP_SETTING_KEYS:
            os.environ.pop(key, None)
        self.setWindowTitle("动画口播智能体")
        self.resize(1440, 900)
        self.setMinimumSize(1040, 620)
        self.draft_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.draft_name_is_automatic = True
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.runner = Runner(self.events)
        self.inputs: dict[str, QLineEdit] = {}
        self.project_labels: dict[str, QLabel] = {}
        self.api_inputs: dict[str, QLineEdit] = {}
        self.api_combos: dict[str, QComboBox] = {}
        self.setting_inputs: dict[str, QLineEdit] = {}
        self.setting_combos: dict[str, QComboBox] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.artifact_labels: dict[str, QLabel] = {}
        self.run_buttons: dict[str, QPushButton] = {}
        self.step_rows: dict[str, QFrame] = {}
        self.steps_note: QLabel | None = None
        self.run_button_labels: dict[str, QLabel] = {}
        self.view_buttons: dict[str, QPushButton] = {}
        self.image_missing_button: QPushButton | None = None
        self.preview_button: QPushButton | None = None
        self.automation_step_button: QPushButton | None = None
        self._jianying_automation_thread: threading.Thread | None = None
        self.douyin_video_input: QLineEdit | None = None
        self.douyin_cover_input: QLineEdit | None = None
        self.douyin_title_input: QLineEdit | None = None
        self.douyin_topics_input: QLineEdit | None = None
        self.douyin_collection_input: QLineEdit | None = None
        self.douyin_metadata_button: QPushButton | None = None
        self.douyin_description_input: QPlainTextEdit | None = None
        self.douyin_open_button: QPushButton | None = None
        self.douyin_publish_button: QPushButton | None = None
        self.douyin_auto_publish_checkbox: QCheckBox | None = None
        self._douyin_publish_thread: threading.Thread | None = None
        self._douyin_metadata_thread: threading.Thread | None = None
        self._pending_publish_after_metadata = False
        self._douyin_last_auto_title = ""
        self._douyin_last_auto_cover = ""
        self._douyin_last_auto_video = ""
        self._douyin_last_publish_succeeded = False
        self._douyin_last_publish_prepared = False
        self._auto_run_step09 = False
        self._automation_draft_target: tuple[Path, str] | None = None
        self._automation_export_target: Path | None = None
        self._automation_last_status = "未执行"
        self._chain_portrait_after_export = False
        self._portrait_chain_attempts = 0
        self._last_jianying_export_path: Path | None = None
        self._batch_package_options: list[Options] = []
        self._batch_package_index = -1
        self._batch_package_phase = ""
        self.continue_button: QPushButton | None = None
        self.workflow_group: QComboBox | None = None
        self.workflow_mode: QComboBox | None = None
        self.workflow_tabs: QTabWidget | None = None
        self.workflow_stage_buttons: dict[str, QPushButton] = {}
        self.workflow_stage_status_labels: dict[str, QLabel] = {}
        self.video_mode_buttons: dict[str, QPushButton] = {}
        self.video_mode_bar: QWidget | None = None
        self.video_mode_combo: QComboBox | None = None
        self.render_mode_combo: QComboBox | None = None
        self.workflow_actions: QFrame | None = None
        self.cover_panel: QFrame | None = None
        self.cover_size_combo: QComboBox | None = None
        self.cover_canvas_label: QLabel | None = None
        self.cover_prompt_preview: QPlainTextEdit | None = None
        self.cover_output_label: QLabel | None = None
        self.cover_status_label: QLabel | None = None
        self.cover_view_button: QPushButton | None = None
        self.cover_folder_button: QPushButton | None = None
        self.cover_generate_button: QPushButton | None = None
        self.publish_panel: QFrame | None = None
        self.publish_status_label: QLabel | None = None
        self.project_panel: QFrame | None = None
        self.project_panel_body: QWidget | None = None
        self.project_settings_scroll: QScrollArea | None = None
        self.workflow_splitter: QSplitter | None = None
        self.project_toggle_button: QToolButton | None = None
        self.project_settings_expanded = False
        self.package_source_video: QLineEdit | None = None
        self.package_project_combo: QComboBox | None = None
        self.landscape_projects: list[LandscapeProject] = []
        self.package_state = load_portrait_package_state(UI_STATE_PATH)
        self.package_title_checkbox: QCheckBox | None = None
        self.package_subtitle_checkbox: QCheckBox | None = None
        self.package_black_background_checkbox: QCheckBox | None = None
        self.background_black_checkbox: QCheckBox | None = None
        self.package_project_label: QLabel | None = None
        self.batch_topic_label: QWidget | None = None
        self.topic_catalog_button: QPushButton | None = None
        self.batch_topic_generate_button: QPushButton | None = None
        self.archive_topic_button: QPushButton | None = None
        self.target_duration_label: QLabel | None = None
        self.target_chars_group: QWidget | None = None
        self.context_input: QPlainTextEdit | None = None
        self._topic_generation_thread: threading.Thread | None = None
        self._copy_revision_thread: threading.Thread | None = None
        self._copy_revision_editor: QPlainTextEdit | None = None
        self._copy_revision_button: QPushButton | None = None
        self.preview_succeeded.connect(self._on_preview_succeeded)
        self.preview_failed.connect(self._on_preview_failed)
        self.jianying_automation_succeeded.connect(self._on_jianying_automation_succeeded)
        self.jianying_automation_failed.connect(self._on_jianying_automation_failed)
        self.douyin_publish_succeeded.connect(self._on_douyin_publish_succeeded)
        self.douyin_publish_failed.connect(self._on_douyin_publish_failed)
        self.douyin_publish_prepared.connect(self._on_douyin_publish_prepared)
        self.douyin_metadata_succeeded.connect(self._on_douyin_metadata_succeeded)
        self.douyin_metadata_failed.connect(self._on_douyin_metadata_failed)
        self.batch_topics_generated.connect(self._on_batch_topics_generated)
        self.topic_generation_progress.connect(self._on_topic_generation_progress)
        self.topic_generation_failed.connect(self._on_topic_generation_failed)
        self.copy_revision_succeeded.connect(self._on_copy_revision_succeeded)
        self.copy_revision_failed.connect(self._on_copy_revision_failed)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(150)
        self.refresh_status()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_workflow_tab(), "工作流")
        tabs.addTab(self._build_settings_tab(), "设置")
        self.setCentralWidget(tabs)

    def _build_workflow_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 22)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("动画口播智能体")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()
        outer.addLayout(header)

        self.stop_button = self._button("停止", QStyle.SP_MediaStop, self.runner.stop, "danger")
        self.batch_button = self._button("批量执行", QStyle.SP_MediaPlay, self.run_batch_pipeline)
        self.continue_button = self._button(
            "从文案继续",
            QStyle.SP_ArrowRight,
            self.run_from_copywriting,
        )
        self.continue_button.setToolTip("使用当前 wenan.txt，跳过第 01 步，重跑第 02～08 步（会重生成图片）")
        self.start_button = self._button("开始执行", QStyle.SP_MediaPlay, self.run_pipeline, "primary")

        self.workflow_tabs = QTabWidget()
        steps_scroll = QScrollArea()
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setFrameShape(QFrame.NoFrame)
        steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        steps_scroll.setWidget(self._build_steps_panel())

        portrait_scroll = QScrollArea()
        portrait_scroll.setWidgetResizable(True)
        portrait_scroll.setFrameShape(QFrame.NoFrame)
        portrait_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        portrait_scroll.setWidget(self._build_portrait_package_panel())

        cover_scroll = QScrollArea()
        cover_scroll.setWidgetResizable(True)
        cover_scroll.setFrameShape(QFrame.NoFrame)
        cover_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cover_scroll.setWidget(self._build_cover_panel())

        publish_scroll = QScrollArea()
        publish_scroll.setWidgetResizable(True)
        publish_scroll.setFrameShape(QFrame.NoFrame)
        publish_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        publish_scroll.setWidget(self._build_publish_panel())

        self.workflow_tabs.addTab(steps_scroll, "1 横版母片")
        self.workflow_tabs.addTab(portrait_scroll, "2 竖版包装")
        self.workflow_tabs.addTab(cover_scroll, "作品封面")
        self.workflow_tabs.addTab(publish_scroll, "发布作品")
        self.workflow_tabs.currentChanged.connect(self._change_workflow_stage)
        self.workflow_tabs.setMinimumWidth(560)
        self.workflow_tabs.setMinimumHeight(220)
        self.workflow_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.project_panel = self._build_project_panel()
        self.project_settings_scroll = QScrollArea()
        self.project_settings_scroll.setWidgetResizable(True)
        self.project_settings_scroll.setFrameShape(QFrame.NoFrame)
        self.project_settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.project_settings_scroll.setWidget(self.project_panel)
        self.project_settings_scroll.setMinimumHeight(150)
        self.project_settings_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.workflow_splitter = QSplitter(Qt.Vertical)
        self.workflow_splitter.addWidget(self.project_settings_scroll)
        self.workflow_splitter.addWidget(self._build_stage_workspace())
        self.workflow_splitter.setSizes([PROJECT_PANEL_COLLAPSED_HEIGHT, 686])
        self.workflow_splitter.setStretchFactor(0, 0)
        self.workflow_splitter.setStretchFactor(1, 1)
        self.workflow_splitter.setChildrenCollapsible(False)

        # Keep the log beside the whole workflow so it remains visible while
        # project settings and production steps are being edited or run.
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.addWidget(self.workflow_splitter)
        content_splitter.addWidget(self._build_log_panel())
        content_splitter.setSizes([1120, 240])
        content_splitter.setStretchFactor(0, 5)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setMinimumHeight(0)
        content_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(content_splitter, 1)
        assert self.workflow_mode is not None
        self.workflow_mode.currentIndexChanged.connect(self._change_workflow_mode)
        self._set_project_settings_expanded(False)
        self._change_workflow_mode(self.workflow_mode.currentIndex())
        return page

    def _build_stage_workspace(self) -> QWidget:
        assert self.workflow_tabs is not None
        workspace = QFrame()
        workspace.setObjectName("workflowPanel")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        stage_nav = QFrame()
        stage_nav.setObjectName("stageNavBar")
        stage_layout = QHBoxLayout(stage_nav)
        stage_layout.setContentsMargins(0, 0, 0, 10)
        stage_layout.setSpacing(8)
        stage_layout.addWidget(self._form_label("主题流程", width=68))
        stage_defs = (
            "视频制作",
            "作品资产",
            "作品发布",
        )
        for index, stage in enumerate(stage_defs, start=1):
            stage_item = QWidget()
            stage_item.setObjectName("formField")
            stage_item_layout = QVBoxLayout(stage_item)
            stage_item_layout.setContentsMargins(0, 0, 0, 0)
            stage_item_layout.setSpacing(2)
            button = QPushButton(f"{index}  {stage}")
            button.clicked.connect(
                lambda checked=False, value=stage: self._select_workflow_stage(value)
            )
            button.setObjectName("stageNav")
            button.setCheckable(True)
            self.workflow_stage_buttons[stage] = button
            stage_item_layout.addWidget(button)
            status = QLabel("未开始")
            status.setObjectName("stageStatus")
            status.setAlignment(Qt.AlignCenter)
            self.workflow_stage_status_labels[stage] = status
            stage_item_layout.addWidget(status)
            stage_layout.addWidget(stage_item, 1)
        layout.addWidget(stage_nav)

        self.video_mode_bar = QWidget()
        self.video_mode_bar.setObjectName("formField")
        mode_layout = QHBoxLayout(self.video_mode_bar)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)
        mode_label = self._form_label("视频版本", width=68)
        mode_layout.addWidget(mode_label)
        video_modes = (
            ("横版母片", WORKFLOW_LANDSCAPE),
            ("横版转竖版", WORKFLOW_PORTRAIT_PACKAGE),
            ("原生竖版", WORKFLOW_NATIVE_PORTRAIT),
        )
        self.video_mode_combo = QComboBox()
        for label, mode in video_modes:
            self.video_mode_combo.addItem(label, mode)
        self.video_mode_combo.setFixedWidth(236)
        self.video_mode_combo.currentIndexChanged.connect(self._change_video_mode_from_combo)
        mode_layout.addWidget(self.video_mode_combo)
        render_label = self._form_label("成片方式", width=68)
        mode_layout.addWidget(render_label)
        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItem("剪映草稿（现有流程）", "jianying")
        self.render_mode_combo.addItem("无限画布成片（实验）", "infinite_canvas")
        self.render_mode_combo.setFixedWidth(188)
        self.render_mode_combo.setToolTip("默认使用现有剪映流程；无限画布只替换最终成片步骤，不改变前面的素材生成")
        self.render_mode_combo.currentIndexChanged.connect(self._on_render_mode_changed)
        mode_layout.addWidget(self.render_mode_combo)

        actions = QFrame()
        actions.setObjectName("workflowActions")
        self.workflow_actions = actions
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 10)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.video_mode_bar)
        action_layout.addStretch()
        self.stop_button.setText("停止任务")
        self.stop_button.setToolTip("停止当前任务")
        self.stop_button.setAccessibleName("停止当前任务")
        self.stop_button.setFixedWidth(108)
        self.batch_button.setFixedWidth(110)
        self.continue_button.setFixedWidth(126)
        self.start_button.setFixedWidth(116)
        action_layout.addWidget(self.stop_button)
        action_layout.addWidget(self.batch_button)
        action_layout.addWidget(self.continue_button)
        action_layout.addWidget(self.start_button)
        layout.addWidget(actions)
        layout.addWidget(self.workflow_tabs, 1)
        return workspace

    def _build_project_panel(self) -> QFrame:
        self.project_toggle_button = QToolButton()
        self.project_toggle_button.setArrowType(Qt.DownArrow)
        self.project_toggle_button.setToolTip("展开主题设置")
        self.project_toggle_button.clicked.connect(self.toggle_project_settings)
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        topic_row = QHBoxLayout()
        topic_row.setSpacing(12)
        topic_label = self._form_label("主题")
        self.project_labels["topic"] = topic_label
        topic_row.addWidget(topic_label)
        self.inputs["topic"] = QLineEdit("什么是知识传递")
        self.inputs["topic"].setMinimumWidth(320)
        topic_row.addWidget(self.inputs["topic"], 1)
        self.topic_catalog_button = self._button(
            "查看主题",
            QStyle.SP_FileDialogDetailedView,
            self.view_topic_catalog,
        )
        self.topic_catalog_button.setToolTip("读取并查看 data/主题清单.md 的最新内容")
        self.topic_catalog_button.setFixedWidth(110)
        topic_row.addWidget(self.topic_catalog_button)
        self.archive_topic_button = self._button(
            "归档主题",
            QStyle.SP_DialogSaveButton,
            self.archive_current_topic,
        )
        self.archive_topic_button.setToolTip("将当前主题标记为已制作并放入历史主题")
        self.archive_topic_button.setFixedWidth(150)
        topic_row.addWidget(self.archive_topic_button)
        topic_row.addWidget(self.project_toggle_button)
        layout.addLayout(topic_row)

        # Keep the existing mode value as internal state.  The visible controls
        # are the stage navigation and video-mode segmented buttons below.
        self.workflow_mode = QComboBox(panel)
        self.workflow_mode.addItems(
            (
                WORKFLOW_LANDSCAPE,
                WORKFLOW_PORTRAIT_PACKAGE,
                WORKFLOW_NATIVE_PORTRAIT,
                WORKFLOW_COVER,
                WORKFLOW_PUBLISH,
            )
        )
        self.workflow_mode.hide()

        self.project_panel_body = QWidget()
        self.project_panel_body.setObjectName("panelBody")
        self.project_panel_body.setVisible(self.project_settings_expanded)
        form = QFormLayout(self.project_panel_body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        direction_label = self._form_label("选题方向")
        self.project_labels["topic_direction"] = direction_label
        self.inputs["topic_direction"] = QLineEdit()
        self.inputs["topic_direction"].setPlaceholderText(
            "可选，例如：计算机操作系统、数据库、人工智能、大模型"
        )
        self.batch_topic_generate_button = self._button(
            "批量生成主题",
            QStyle.SP_FileDialogListView,
            self.generate_batch_topics,
        )
        self.batch_topic_generate_button.setToolTip(
            "生成一组互不重复的具体主题；选题方向可留空"
        )
        self.batch_topic_generate_button.setFixedWidth(150)
        direction_row = QWidget()
        direction_row.setObjectName("formField")
        direction_layout = QHBoxLayout(direction_row)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        direction_layout.setSpacing(12)
        direction_layout.addWidget(self.inputs["topic_direction"], 1)
        direction_layout.addWidget(self.batch_topic_generate_button)
        toggle_column_spacer = QWidget()
        toggle_column_spacer.setObjectName("formField")
        toggle_column_spacer.setFixedWidth(self.project_toggle_button.sizeHint().width())
        direction_layout.addWidget(toggle_column_spacer)
        form.addRow(direction_label, direction_row)

        context_label = self._form_label("上下文 / 行文思路", top=True)
        self.project_labels["context"] = context_label
        self.context_input = QPlainTextEdit()
        self.context_input.setObjectName("contextInput")
        self.context_input.setFixedHeight(68)
        self.context_input.setPlaceholderText(
            "例如：‘养龙虾’指用人工智能生成养殖方案，不是现实养殖；重点讲清概念区别。"
        )
        self.context_input.setToolTip("补充主题背景、关键词含义、受众和行文重点，帮助模型避免跑题")
        form.addRow(context_label, self.context_input)

        target_chars_label = self._form_label("最长字数")
        self.project_labels["target_chars"] = target_chars_label
        self.inputs["target_chars"] = QLineEdit("700")
        self.inputs["target_chars"].setFixedWidth(72)
        target_chars_group = QWidget()
        target_chars_group.setObjectName("formField")
        self.target_chars_group = target_chars_group
        target_chars_layout = QHBoxLayout(target_chars_group)
        target_chars_layout.setContentsMargins(0, 0, 0, 0)
        target_chars_layout.setSpacing(10)
        target_chars_layout.addWidget(self.inputs["target_chars"])
        self.target_duration_label = QLabel()
        self.target_duration_label.setObjectName("muted")
        self.target_duration_label.setWordWrap(False)
        self.target_duration_label.setMinimumWidth(180)
        self.target_duration_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        target_chars_layout.addWidget(self.target_duration_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow(target_chars_label, target_chars_group)

        draft_label = self._form_label("草稿名")
        self.project_labels["draft_name"] = draft_label
        self.inputs["draft_name"] = QLineEdit(f"什么是知识传递_{self.draft_timestamp}")
        form.addRow(draft_label, self.inputs["draft_name"])

        self.inputs["target_chars"].textChanged.connect(self._update_duration_estimate)
        self._update_duration_estimate(self.inputs["target_chars"].text())

        self.inputs["topic"].textChanged.connect(self._update_automatic_draft_name)
        self.inputs["topic"].textChanged.connect(self._update_package_project_label)
        self.inputs["topic"].textChanged.connect(self._update_cover_prompt_preview)
        self.inputs["topic"].textChanged.connect(self._update_publish_title)
        self.inputs["topic"].textChanged.connect(self._on_workspace_topic_changed)
        self.context_input.textChanged.connect(self._update_cover_prompt_preview)
        self.inputs["draft_name"].textEdited.connect(self._mark_draft_name_custom)
        batch_label = self._form_label("批量主题", top=True)
        self.batch_topics = QPlainTextEdit()
        self.batch_topics.setObjectName("batchTopics")
        self.batch_topics.setFixedHeight(54)
        self.batch_topics.setPlaceholderText("每行输入一个主题")
        self.batch_topics.setToolTip("批量执行时按行读取主题，空行和重复主题会被忽略")
        self.batch_topics.textChanged.connect(self._update_batch_topic_count)
        self.batch_status_label = QLabel("0 个主题")
        self.batch_status_label.setObjectName("muted")
        self.batch_status_label.setAlignment(Qt.AlignCenter)
        self.batch_status_label.setFixedWidth(110)
        batch_row = QWidget()
        batch_row.setObjectName("formField")
        batch_layout = QHBoxLayout(batch_row)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(8)
        batch_layout.addWidget(self.batch_topics, 1)
        batch_layout.addWidget(self.batch_status_label)
        form.addRow(batch_label, batch_row)
        self.batch_topic_label = batch_label
        layout.addWidget(self.project_panel_body)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return panel

    def _change_workflow_group(self, group: str) -> None:
        """Compatibility wrapper for switching one of the three theme stages."""
        self._select_workflow_stage(group)

    def _select_workflow_stage(self, stage: str) -> None:
        if self.workflow_mode is None:
            return
        video_modes = (WORKFLOW_LANDSCAPE, WORKFLOW_PORTRAIT_PACKAGE, WORKFLOW_NATIVE_PORTRAIT)
        current = self.workflow_mode.currentText()
        if stage == "作品资产":
            mode = WORKFLOW_COVER
        elif stage == "作品发布":
            mode = WORKFLOW_PUBLISH
        else:
            mode = current if current in video_modes else WORKFLOW_LANDSCAPE
        if stage in {"作品资产", "作品发布"} and self.project_settings_expanded:
            self._set_project_settings_expanded(False)
        if current == mode:
            self._change_workflow_mode(self.workflow_mode.currentIndex())
        else:
            self.workflow_mode.setCurrentText(mode)

    def _select_video_mode(self, mode: str) -> None:
        if self.workflow_mode is None:
            return
        if mode not in (WORKFLOW_LANDSCAPE, WORKFLOW_PORTRAIT_PACKAGE, WORKFLOW_NATIVE_PORTRAIT):
            return
        if self.workflow_mode.currentText() == mode:
            self._change_workflow_mode(self.workflow_mode.currentIndex())
        else:
            self.workflow_mode.setCurrentText(mode)

    def _change_video_mode_from_combo(self, index: int) -> None:
        if self.video_mode_combo is None:
            return
        mode = self.video_mode_combo.itemData(index)
        if isinstance(mode, str):
            self._select_video_mode(mode)

    def _sync_workflow_navigation(self, mode: str) -> None:
        video = mode in (WORKFLOW_LANDSCAPE, WORKFLOW_PORTRAIT_PACKAGE, WORKFLOW_NATIVE_PORTRAIT)
        selected_stage = "视频制作" if video else ("作品资产" if mode == WORKFLOW_COVER else "作品发布")
        for stage, button in self.workflow_stage_buttons.items():
            button.setChecked(stage == selected_stage)
        for value, button in self.video_mode_buttons.items():
            button.setChecked(value == mode)
        if self.video_mode_combo is not None:
            combo_index = self.video_mode_combo.findData(mode)
            if combo_index >= 0 and combo_index != self.video_mode_combo.currentIndex():
                self.video_mode_combo.blockSignals(True)
                self.video_mode_combo.setCurrentIndex(combo_index)
                self.video_mode_combo.blockSignals(False)
        if self.video_mode_bar is not None:
            self.video_mode_bar.setVisible(video)

    def view_topic_catalog(self) -> None:
        """Display the latest durable Markdown topic catalog."""
        catalog_path = PROJECT_ROOT / "data" / "主题清单.md"
        try:
            content = catalog_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.warning(self, "读取主题失败", f"无法读取主题清单：\n{catalog_path}\n\n{exc}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("查看主题清单")
        dialog.resize(780, 620)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(content)
        editor.setReadOnly(True)
        editor.setToolTip("此窗口只读，主题分类请直接编辑 data/主题清单.md")
        layout.addWidget(editor)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)
        dialog.exec()

    def generate_batch_topics(self) -> None:
        if not self._can_start_topic_generation():
            return
        direction = self.inputs["topic_direction"].text().strip()
        current_topic = self.inputs["topic"].text().strip()
        context = self.context_input.toPlainText().strip() if self.context_input is not None else ""
        count, accepted = QInputDialog.getInt(
            self,
            "批量生成主题",
            "生成数量",
            10,
            2,
            30,
            1,
        )
        if not accepted:
            return
        self._set_topic_generation_enabled(False)
        self.log.appendPlainText(f"批量生成主题开始：计划生成 {count} 个主题")

        def worker() -> None:
            try:
                self.batch_topics_generated.emit(
                    generate_unique_topics(
                        count,
                        direction=direction,
                        context=context,
                        current_topic=current_topic,
                        progress_callback=self.topic_generation_progress.emit,
                    )
                )
            except Exception as exc:
                self.topic_generation_failed.emit(str(exc))

        self._topic_generation_thread = threading.Thread(target=worker, daemon=True)
        self._topic_generation_thread.start()

    def _can_start_topic_generation(self) -> bool:
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "当前任务尚未完成，请稍后生成主题。")
            return False
        return not (self._topic_generation_thread is not None and self._topic_generation_thread.is_alive())

    def _set_topic_generation_enabled(self, enabled: bool) -> None:
        for button in (
            self.batch_topic_generate_button,
            self.topic_catalog_button,
            self.archive_topic_button,
        ):
            if button is not None:
                button.setEnabled(enabled)

    def archive_current_topic(self) -> None:
        """Mark the current topic as completed in the local history."""
        topic = self.inputs["topic"].text().strip()
        if not topic:
            QMessageBox.information(self, "缺少主题", "请先填写当前主题。")
            return
        try:
            record_topic(topic, status="used")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "归档失败", str(exc))
            return
        self.log.appendPlainText(f"已归档当前主题：{topic}")
        QMessageBox.information(self, "归档成功", "当前主题已放入历史主题，后续生成会避开相似选题。")

    def _on_batch_topics_generated(self, topics: list[str]) -> None:
        self._set_topic_generation_enabled(True)
        self.log.appendPlainText(
            f"批量生成主题完成：新增 {len(topics)} 个主题，已写入主题清单的待评估主题"
        )

    def _on_topic_generation_progress(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _on_topic_generation_failed(self, message: str) -> None:
        self._set_topic_generation_enabled(True)
        self.log.appendPlainText(f"批量生成主题失败：{message}")
        QMessageBox.warning(self, "主题生成失败", message)

    def _update_automatic_draft_name(self, topic: str) -> None:
        if self.draft_name_is_automatic:
            self.inputs["draft_name"].setText(f"{safe_topic(topic)}_{self.draft_timestamp}")

    def _mark_draft_name_custom(self, _text: str) -> None:
        self.draft_name_is_automatic = False

    def _update_batch_topic_count(self) -> None:
        if not self.runner.running:
            count = len(parse_batch_topics(self.batch_topics.toPlainText()))
            self.batch_status_label.setText(f"{count} 个主题")

    def _update_duration_estimate(self, value: str) -> None:
        if self.target_duration_label is None:
            return
        raw = value.strip()
        if not raw:
            self.target_duration_label.setText("最长配音：请输入最长字数")
            return
        try:
            char_count = int(raw)
        except ValueError:
            self.target_duration_label.setText("最长配音：字数需为非负整数")
            return
        if char_count < 0:
            self.target_duration_label.setText("最长配音：字数需为非负整数")
            return
        if char_count == 0:
            self.target_duration_label.setText("最长配音：不限制")
            return
        seconds = estimate_speech_duration_seconds(char_count)
        low, high = estimate_speech_duration_range(char_count)
        self.target_duration_label.setText(
            f"最长配音：{char_count} 字约 {seconds:.0f} 秒（约 {low:.0f}~{high:.0f} 秒）"
        )

    def _path_row(self, grid: QGridLayout, row: int, label: str, key: str, value: str, callback, button_text: str) -> None:
        grid.addWidget(QLabel(label), row, 0)
        edit = QLineEdit(value)
        self.inputs[key] = edit
        grid.addWidget(edit, row, 1, 1, 6)
        grid.addWidget(self._button(button_text, QStyle.SP_DirOpenIcon, callback), row, 7)

    def _build_portrait_package_panel(self) -> QFrame:
        panel, layout = self._panel("\u7ad6\u5c4f\u5305\u88c5")
        panel.setObjectName("workflowContent")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.package_project_combo = QComboBox()
        self.package_project_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.package_project_combo.setMinimumContentsLength(24)
        refresh_button = self._button(
            "\u5237\u65b0",
            QStyle.SP_BrowserReload,
            self.refresh_landscape_projects,
        )
        refresh_button.setToolTip("\u91cd\u65b0\u626b\u63cf output \u4e2d\u53ef\u7528\u7684\u6a2a\u7248\u9879\u76ee")
        refresh_button.setFixedWidth(82)
        project_row = QWidget()
        project_row.setObjectName("formField")
        project_layout = QHBoxLayout(project_row)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.setSpacing(8)
        project_layout.addWidget(self.package_project_combo, 1)
        project_layout.addWidget(refresh_button)
        form.addRow(self._form_label("\u6a2a\u7248\u9879\u76ee", width=92), project_row)

        self.package_source_video = QLineEdit()
        self.package_source_video.setPlaceholderText(
            "\u9009\u62e9\u5df2\u4ece\u526a\u6620\u5bfc\u51fa\u7684 1920 x 1080 MP4"
        )
        source_button = self._button(
            "\u9009\u62e9",
            QStyle.SP_DirOpenIcon,
            self.choose_package_source_video,
        )
        source_button.setFixedWidth(82)
        source_row = QWidget()
        source_row.setObjectName("formField")
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(8)
        source_layout.addWidget(self.package_source_video, 1)
        source_layout.addWidget(source_button)
        form.addRow(self._form_label("\u6a2a\u7248\u6210\u7247", width=92), source_row)

        self.package_project_label = QLabel()
        self.package_project_label.setObjectName("muted")
        self.package_project_label.setWordWrap(True)
        form.addRow(
            self._form_label("\u9879\u76ee\u76ee\u5f55", width=92, top=True),
            self.package_project_label,
        )

        option_widget = QWidget()
        option_widget.setObjectName("formField")
        option_row = QHBoxLayout()
        option_widget.setLayout(option_row)
        option_row.setContentsMargins(0, 0, 0, 0)
        option_row.setSpacing(18)
        self.package_title_checkbox = QCheckBox("\u9876\u90e8\u6807\u9898")
        self.package_title_checkbox.setChecked(True)
        self.package_subtitle_checkbox = QCheckBox("\u5e95\u90e8\u5b57\u5e55")
        self.package_subtitle_checkbox.setChecked(True)
        self.package_black_background_checkbox = QCheckBox("\u65e0\u80cc\u666f\uff08\u9ed1\u8272\uff09")
        self.package_black_background_checkbox.setChecked(True)
        option_row.addWidget(self.package_title_checkbox)
        option_row.addWidget(self.package_subtitle_checkbox)
        option_row.addWidget(self.package_black_background_checkbox)
        option_row.addStretch()
        form.addRow(self._form_label("\u5305\u88c5\u5185\u5bb9", width=92), option_widget)
        self.package_project_combo.currentIndexChanged.connect(self._on_package_project_changed)
        self.package_source_video.editingFinished.connect(self._remember_package_source_video)
        layout.addLayout(form)
        layout.addStretch()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        return panel

    def _build_cover_panel(self) -> QFrame:
        self.cover_generate_button = self._button(
            "生成封面图",
            QStyle.SP_MediaPlay,
            self.run_pipeline,
            "primary",
        )
        self.cover_generate_button.setFixedWidth(132)
        panel, layout = self._panel("作品封面", self.cover_generate_button)
        panel.setObjectName("workflowContent")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.cover_size_combo = QComboBox()
        for key, label, _width, _height, _ratio, _orientation in COVER_SIZE_OPTIONS:
            self.cover_size_combo.addItem(label, key)
        self.cover_size_combo.setCurrentIndex(
            max(0, self.cover_size_combo.findData(DEFAULT_COVER_SIZE_KEY))
        )
        self.cover_size_combo.currentIndexChanged.connect(self._update_cover_prompt_preview)
        self.cover_size_combo.setMaximumWidth(320)
        form.addRow(self._form_label("画布尺寸", width=92), self.cover_size_combo)

        self.cover_canvas_label = QLabel()
        self.cover_canvas_label.setObjectName("muted")
        form.addRow(self._form_label("画布", width=92), self.cover_canvas_label)

        self.cover_prompt_preview = QPlainTextEdit()
        self.cover_prompt_preview.setReadOnly(True)
        self.cover_prompt_preview.setFixedHeight(180)
        self.cover_prompt_preview.setPlaceholderText("填写主题后，这里会显示封面生成提示词。")
        form.addRow(self._form_label("封面提示词", width=92, top=True), self.cover_prompt_preview)

        self.cover_output_label = QLabel()
        self.cover_output_label.setObjectName("muted")
        self.cover_output_label.setWordWrap(True)
        self.cover_status_label = QLabel("未生成")
        self.cover_status_label.setObjectName("status")
        self.cover_status_label.setAlignment(Qt.AlignCenter)
        self.cover_status_label.setFixedWidth(132)
        output_row = QWidget()
        output_row.setObjectName("formField")
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(12)
        output_layout.addWidget(self.cover_output_label, 1)
        output_layout.addWidget(self.cover_status_label)
        form.addRow(self._form_label("输出文件", width=92, top=True), output_row)

        self.cover_folder_button = self._button(
            "打开文件夹",
            QStyle.SP_DirOpenIcon,
            self.open_cover_folder,
        )
        self.cover_folder_button.setFixedWidth(132)
        self.cover_view_button = self._button(
            "查看封面",
            QStyle.SP_FileDialogDetailedView,
            self.show_cover_artifact,
        )
        self.cover_view_button.setEnabled(False)
        self.cover_view_button.setFixedWidth(132)
        cover_actions = QWidget()
        cover_actions.setObjectName("formField")
        cover_actions_layout = QHBoxLayout(cover_actions)
        cover_actions_layout.setContentsMargins(0, 0, 0, 0)
        cover_actions_layout.setSpacing(8)
        cover_actions_layout.addStretch()
        cover_actions_layout.addWidget(self.cover_folder_button)
        cover_actions_layout.addWidget(self.cover_view_button)
        form.addRow(self._form_label("", width=92), cover_actions)

        layout.addLayout(form)
        layout.addStretch()
        self._update_cover_prompt_preview()
        self.cover_panel = panel
        return panel

    def _build_publish_panel(self) -> QFrame:
        panel, layout = self._panel("发布作品")
        panel.setObjectName("workflowContent")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.douyin_video_input = QLineEdit()
        self.douyin_video_input.setPlaceholderText("自动读取当前主题最新导出视频，也可以手动选择")
        video_button = self._button("选择", QStyle.SP_DirOpenIcon, self.choose_douyin_video)
        video_button.setFixedWidth(82)
        video_row = QWidget()
        video_row.setObjectName("formField")
        video_layout = QHBoxLayout(video_row)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(8)
        video_layout.addWidget(self.douyin_video_input, 1)
        video_layout.addWidget(video_button)
        form.addRow(self._form_label("视频文件", width=92), video_row)

        self.douyin_cover_input = QLineEdit()
        self.douyin_cover_input.setPlaceholderText("自动读取当前主题生成的封面图片")
        cover_button = self._button("选择", QStyle.SP_DirOpenIcon, self.choose_douyin_cover)
        cover_button.setFixedWidth(82)
        cover_row = QWidget()
        cover_row.setObjectName("formField")
        cover_layout = QHBoxLayout(cover_row)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(8)
        cover_layout.addWidget(self.douyin_cover_input, 1)
        cover_layout.addWidget(cover_button)
        form.addRow(self._form_label("封面图片", width=92), cover_row)

        self.douyin_title_input = QLineEdit()
        self.douyin_title_input.setPlaceholderText("抖音作品标题，最多 55 个字符")
        form.addRow(self._form_label("作品标题", width=92), self.douyin_title_input)

        self.douyin_topics_input = QLineEdit()
        self.douyin_topics_input.setPlaceholderText("多个话题用空格或逗号分隔，例如：人工智能 计算机知识")
        self.douyin_topics_input.setToolTip("桌面端会将这些 #话题写入抖音作品描述框，并按空格让抖音识别为话题标签")
        form.addRow(self._form_label("话题标签", width=92), self.douyin_topics_input)

        self.douyin_collection_input = QLineEdit(DEFAULT_DOUYIN_COLLECTION)
        self.douyin_collection_input.setPlaceholderText("发布时加入的合集名称")
        self.douyin_collection_input.setToolTip("发布时会自动选择这个合集；默认：计算机小常识")
        form.addRow(self._form_label("合集", width=92), self.douyin_collection_input)

        self.douyin_description_input = QPlainTextEdit()
        self.douyin_description_input.setObjectName("contextInput")
        self.douyin_description_input.setFixedHeight(72)
        self.douyin_description_input.setPlaceholderText("可选：作品简介。桌面端会将上方话题追加到这个描述框")
        form.addRow(self._form_label("作品描述", width=92, top=True), self.douyin_description_input)

        metadata_row = QWidget()
        metadata_row.setObjectName("formField")
        metadata_layout = QHBoxLayout(metadata_row)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(8)
        self.douyin_metadata_button = self._button(
            "AI生成标题/话题", QStyle.SP_FileDialogContentsView, self.generate_douyin_metadata
        )
        self.douyin_metadata_button.setFixedWidth(156)
        metadata_hint = QLabel("根据当前主题和文案生成相关话题")
        metadata_hint.setObjectName("muted")
        metadata_layout.addWidget(self.douyin_metadata_button)
        metadata_layout.addWidget(metadata_hint)
        metadata_layout.addStretch()
        form.addRow(self._form_label("发布信息", width=92), metadata_row)

        self.publish_status_label = QLabel("未扫描")
        self.publish_status_label.setObjectName("muted")
        form.addRow(self._form_label("素材状态", width=92), self.publish_status_label)

        actions_widget = QWidget()
        actions_widget.setObjectName("formField")
        actions = QHBoxLayout(actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.douyin_open_button = self._button("登录/检查抖音", QStyle.SP_DirOpenIcon, self.open_douyin_page)
        self.douyin_open_button.setFixedWidth(136)
        self.douyin_open_button.setToolTip("首次使用时打开专用浏览器并登录；登录后发布按钮会复用此会话")
        scan_button = self._button("扫描当前主题素材", QStyle.SP_BrowserReload, self.scan_publish_assets)
        scan_button.setFixedWidth(166)
        self.douyin_publish_button = self._button(
            "发布到抖音", QStyle.SP_ArrowForward, self.publish_current_video_to_douyin, "primary"
        )
        self.douyin_publish_button.setFixedWidth(126)
        self.douyin_publish_button.setToolTip(
            "复用已登录的专用浏览器，自动上传视频和封面并填写作品信息；是否点击发布由旁边复选框决定"
        )
        self.douyin_auto_publish_checkbox = QCheckBox("自动点击发布")
        self.douyin_auto_publish_checkbox.setChecked(True)
        self.douyin_auto_publish_checkbox.setToolTip(
            "勾选：程序完成设置后自动点击抖音发布；取消勾选：停在发布页，由你检查后点击发布"
        )
        actions.addStretch()
        actions.addWidget(self.douyin_open_button)
        actions.addWidget(scan_button)
        actions.addWidget(self.douyin_auto_publish_checkbox)
        actions.addWidget(self.douyin_publish_button)
        form.addRow(self._form_label("发布操作", width=92), actions_widget)
        layout.addLayout(form)
        layout.addStretch()
        self.publish_panel = panel
        QTimer.singleShot(0, self.scan_publish_assets)
        return panel

    def _build_steps_panel(self) -> QFrame:
        panel, layout = self._panel("生产流程")
        panel.setObjectName("workflowContent")
        panel.setMinimumHeight(500)
        layout.setSpacing(0)
        for key, title, _, action, view_action in ALL_STEP_DEFS:
            row = QFrame()
            row.setObjectName("stepRow")
            self.step_rows[key] = row
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 8, 2, 8)
            row_layout.setSpacing(12)
            title_label = QLabel(title)
            title_label.setObjectName("stepTitle")
            title_label.setFixedWidth(110)
            status = QLabel("未运行")
            status.setObjectName("status")
            status.setAlignment(Qt.AlignCenter)
            status.setFixedWidth(68)
            artifact = QLabel("未生成")
            artifact.setObjectName("muted")
            artifact.setFixedWidth(120 if key == "voice" else 58)
            row_layout.addWidget(title_label)
            row_layout.addWidget(status)
            row_layout.addWidget(artifact)
            row_layout.addStretch(1)
            if key == "automation":
                run = self._button(
                    action,
                    QStyle.SP_ArrowForward,
                    self.run_automation_step,
                )
                run.setToolTip("打开当前剪映草稿并点击导出（支持 Windows 和 macOS）")
                self.automation_step_button = run
            elif key.startswith("infinite_"):
                run, _ = self._described_button(
                    action,
                    INFINITE_STAGE_DESCRIPTIONS[key],
                    lambda checked=False, k=key: self.run_single_step(k),
                )
                run.setToolTip(
                    f"只执行当前步骤：{title}。完成后可在右侧查看产物状态，再继续下一步。"
                )
            elif key in STEP_BUTTON_DESCRIPTIONS:
                run, action_label = self._described_button(
                    action,
                    STEP_BUTTON_DESCRIPTIONS[key],
                    lambda checked=False, k=key: self.run_single_step(k),
                )
                self.run_button_labels[key] = action_label
            else:
                run = self._button(
                    action,
                    QStyle.SP_ArrowForward,
                    lambda checked=False, k=key: self.run_single_step(
                        k,
                        overwrite_images=k == "images",
                    ),
                )
            if key == "automation":
                run.setFixedWidth(420)
            else:
                run.setFixedWidth(148 if key == "images" else (420 if not view_action else 204))
            if key in STEP_BUTTON_DESCRIPTIONS:
                run.setFixedHeight(50)
            row_layout.addWidget(run)
            self.status_labels[key] = status
            self.artifact_labels[key] = artifact
            self.run_buttons[key] = run
            if key == "images":
                self.image_missing_button = self._button(
                    "生成缺失图片",
                    QStyle.SP_ArrowForward,
                    lambda checked=False: self.run_single_step("images", overwrite_images=False),
                )
                self.image_missing_button.setFixedWidth(148)
                row_layout.addWidget(self.image_missing_button)
            if view_action:
                view = self._button(view_action, QStyle.SP_FileDialogDetailedView, lambda checked=False, k=key: self.show_artifact(k))
                view.setFixedWidth(148 if key == "images" else 204)
                row_layout.addWidget(view)
                self.view_buttons[key] = view
            layout.addWidget(row)
        note = QLabel("图片素材会直接用于布局编译和剪映草稿生成。")
        note.setObjectName("muted")
        layout.addWidget(note)
        self.steps_note = note
        layout.addStretch()
        return panel

    def _build_log_panel(self) -> QFrame:
        panel, layout = self._panel("运行日志")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("执行任务后，运行信息会显示在这里。")
        layout.addWidget(self.log, 1)
        return panel

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 20, 22, 22)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        api_panel, api_layout = self._panel("接口配置")
        api_grid = QGridLayout()
        api_grid.setHorizontalSpacing(14)
        api_grid.setVerticalSpacing(8)
        for index, (label, key, secret) in enumerate(API_FIELDS):
            row, side = divmod(index, 2)
            label_column = side * 2
            value_column = label_column + 1
            api_grid.addWidget(QLabel(label), row, label_column)
            default = API_DEFAULTS.get(key, "")
            if key in {"IMAGE_MODEL", "IMAGE_QUALITY"}:
                combo = QComboBox()
                combo.addItems(IMAGE_MODEL_CHOICES if key == "IMAGE_MODEL" else IMAGE_QUALITY_CHOICES)
                combo.setCurrentText(os.getenv(key, default) or default)
                self.api_combos[key] = combo
                if key == "IMAGE_MODEL":
                    self.image_model_setting = combo
                api_grid.addWidget(combo, row, value_column)
                api_grid.setColumnStretch(value_column, 1)
                continue
            edit = QLineEdit(os.getenv(key, default) or default)
            if secret:
                edit.setEchoMode(QLineEdit.Password)
            self.api_inputs[key] = edit
            if key == "DOUBAO_TTS_SPEAKER":
                speaker_widget = QWidget()
                speaker_row = QHBoxLayout(speaker_widget)
                speaker_row.setContentsMargins(0, 0, 0, 0)
                speaker_row.addWidget(edit, 1)
                voice_link = QLabel(f'<a href="{TTS_VOICE_DOC_URL}">音色列表</a>')
                voice_link.setOpenExternalLinks(True)
                voice_link.setToolTip("打开豆包音色列表")
                speaker_row.addWidget(voice_link)
                self.preview_button = self._button("试听", QStyle.SP_MediaPlay, self.preview_voice)
                self.preview_button.setFixedWidth(72)
                speaker_row.addWidget(self.preview_button)
                api_grid.addWidget(speaker_widget, row, value_column)
            else:
                api_grid.addWidget(edit, row, value_column)
            api_grid.setColumnStretch(value_column, 1)
        api_layout.addLayout(api_grid)
        content_layout.addWidget(api_panel)

        render_panel, render_layout = self._panel("生成与导出")
        render_grid = QGridLayout()
        render_grid.setHorizontalSpacing(14)
        render_grid.setVerticalSpacing(8)
        theme_combo = QComboBox()
        theme_combo.addItems(VISUAL_THEME_CHOICES)
        selected_theme = resolve_visual_theme(
            self.app_settings.get("VISUAL_THEME", ""),
            settings_path=APP_SETTINGS_PATH,
        )
        theme_combo.setCurrentText(selected_theme.label)
        self.setting_combos["VISUAL_THEME"] = theme_combo
        render_grid.addWidget(QLabel("视觉主题"), 0, 0)
        render_grid.addWidget(theme_combo, 0, 1)

        orientation_combo = QComboBox()
        orientation_combo.addItems(VIDEO_ORIENTATION_CHOICES)
        orientation_combo.setCurrentText(self._workflow_orientation())
        orientation_combo.setEnabled(False)
        orientation_combo.setToolTip("\u89c6\u9891\u6bd4\u4f8b\u7531\u5de5\u4f5c\u6d41\u6a21\u5f0f\u81ea\u52a8\u51b3\u5b9a")
        self.setting_combos["VIDEO_ORIENTATION"] = orientation_combo
        render_grid.addWidget(QLabel("视频比例"), 0, 2)
        render_grid.addWidget(orientation_combo, 0, 3)
        orientation_label = render_grid.itemAtPosition(0, 2).widget()
        if isinstance(orientation_label, QLabel):
            orientation_label.setText("\u539f\u751f\u751f\u6210\u753b\u5e03")

        title_heading = QLabel("标题设置")
        title_heading.setObjectName("sectionTitle")
        render_grid.addWidget(title_heading, 1, 0, 1, 4)
        subtitle_heading = QLabel("字幕设置")
        subtitle_heading.setObjectName("sectionTitle")
        render_grid.addWidget(subtitle_heading, 4, 0, 1, 4)

        for row, (label, key, choices) in (
            (2, ("标题字体", "TITLE_FONT", TITLE_FONT_CHOICES)),
            (5, ("字幕字体", "SUBTITLE_FONT", SUBTITLE_FONT_CHOICES)),
        ):
            default = next(field[2] for field in SETTING_FIELDS if field[1] == key)
            value = self.app_settings.get(key, "") or default
            combo = QComboBox()
            combo.addItems(choices)
            combo.setCurrentText(value)
            self.setting_combos[key] = combo
            render_grid.addWidget(QLabel(label), row, 0)
            render_grid.addWidget(combo, row, 1)

        color_defaults = {
            "TITLE_COLOR": selected_theme.title_color,
            "TITLE_BACKGROUND_COLOR": selected_theme.title_background_color,
            "SUBTITLE_COLOR": selected_theme.subtitle_color,
            "SUBTITLE_BACKGROUND_COLOR": selected_theme.subtitle_background_color,
        }
        for row, controls in (
            (2, ((2, "标题颜色", "TITLE_COLOR"),)),
            (3, ((0, "标题背景颜色", "TITLE_BACKGROUND_COLOR"),)),
            (5, ((2, "字幕颜色", "SUBTITLE_COLOR"),)),
            (6, ((0, "字幕背景颜色", "SUBTITLE_BACKGROUND_COLOR"),)),
        ):
            for column, label, key in controls:
                edit = QLineEdit(self.app_settings.get(key, "") or color_defaults[key])
                self.setting_inputs[key] = edit
                color_button = self._button(
                    "选择颜色",
                    QStyle.SP_DialogOpenButton,
                    lambda checked=False, k=key: self.choose_setting_color(k),
                )
                color_widget = QWidget()
                color_row = QHBoxLayout(color_widget)
                color_row.setContentsMargins(0, 0, 0, 0)
                color_row.addWidget(edit, 1)
                color_row.addWidget(color_button)
                render_grid.addWidget(QLabel(label), row, column)
                render_grid.addWidget(
                    color_widget,
                    row,
                    column + 1,
                    1,
                    3 if column == 0 and row in {3, 6} else 1,
                )

        for row, (label, key) in enumerate((
            ("背景图片", "BACKGROUND_IMAGE"),
            ("背景音乐", "BACKGROUND_MUSIC"),
            ("草稿目录", "DRAFT_FOLDER"),
        ), start=7):
            default = next(field[2] for field in SETTING_FIELDS if field[1] == key)
            value = self.app_settings.get(key, "") or default
            if key == "DRAFT_FOLDER":
                value = str(resolve_draft_folder(value))
            edit = QLineEdit(value)
            self.setting_inputs[key] = edit
            path_widget = QWidget()
            path_row = QHBoxLayout(path_widget)
            path_row.setContentsMargins(0, 0, 0, 0)
            path_row.addWidget(edit, 1)
            if key == "BACKGROUND_IMAGE":
                self.background_black_checkbox = QCheckBox("无背景（黑色）")
                self.background_black_checkbox.setChecked(False)
                path_row.addWidget(self.background_black_checkbox)
            path_row.addWidget(self._button("选择", QStyle.SP_DirOpenIcon, lambda checked=False, k=key: self.choose_setting_path(k)))
            render_grid.addWidget(QLabel(label), row, 0)
            render_grid.addWidget(path_widget, row, 1, 1, 3)
        render_grid.setColumnStretch(1, 1)
        render_grid.setColumnStretch(3, 1)
        theme_combo.currentTextChanged.connect(self._apply_theme_colors)
        render_body = QHBoxLayout()
        render_body.setSpacing(18)

        settings_column = QWidget()
        settings_layout = QVBoxLayout(settings_column)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.addLayout(render_grid)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self._button("保存设置", QStyle.SP_DialogSaveButton, self.save_settings, "primary"))
        settings_layout.addLayout(actions)

        render_body.addWidget(settings_column, 3)

        preview_column = QVBoxLayout()
        preview_heading = QLabel("设置预览")
        preview_heading.setObjectName("sectionTitle")
        preview_column.addWidget(preview_heading)
        preview_path = PROJECT_ROOT / "picturies" / "settings_preview.png"
        preview_pixmap = QPixmap(str(preview_path)) if preview_path.is_file() else QPixmap()
        preview = PreviewImageLabel(preview_pixmap)
        preview.setToolTip("标题、展示区域和字幕设置示意")
        preview_column.addWidget(preview, 1)
        render_body.addLayout(preview_column, 2)

        render_layout.addLayout(render_body, 1)
        content_layout.addWidget(render_panel)
        content_layout.addStretch()
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return page

    def _panel(self, title: str, header_action: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        header.addWidget(heading)
        header.addStretch()
        if header_action is not None:
            header.addWidget(header_action)
        layout.addLayout(header)
        return panel, layout

    def toggle_project_settings(self) -> None:
        self._set_project_settings_expanded(not self.project_settings_expanded)

    def _set_project_settings_expanded(self, expanded: bool) -> None:
        self.project_settings_expanded = expanded
        if self.project_panel_body is not None:
            self.project_panel_body.setVisible(expanded)
        if self.project_toggle_button is not None:
            self.project_toggle_button.setArrowType(Qt.UpArrow if expanded else Qt.DownArrow)
            self.project_toggle_button.setToolTip("收起主题设置" if expanded else "展开主题设置")
        if self.project_settings_scroll is None or self.workflow_splitter is None:
            return
        self.project_settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if expanded else Qt.ScrollBarAlwaysOff
        )
        self.project_settings_scroll.setMaximumHeight(
            16777215 if expanded else PROJECT_PANEL_COLLAPSED_HEIGHT
        )
        self.project_settings_scroll.updateGeometry()
        self.project_settings_scroll.setMinimumHeight(
            150 if expanded else PROJECT_PANEL_COLLAPSED_HEIGHT
        )
        QTimer.singleShot(0, self._rebalance_workflow_splitter)

    def _rebalance_workflow_splitter(self) -> None:
        if self.workflow_splitter is None or self.project_settings_scroll is None:
            return
        total = max(320, self.workflow_splitter.height())
        if self.project_settings_expanded:
            natural_height = self.project_panel.sizeHint().height() if self.project_panel is not None else 300
            settings_height = min(390, max(150, min(natural_height, total // 2)))
        else:
            settings_height = PROJECT_PANEL_COLLAPSED_HEIGHT
        self.workflow_splitter.setSizes([settings_height, max(240, total - settings_height)])

    def _focus_workflow_view(self) -> None:
        if self.project_settings_expanded:
            self._set_project_settings_expanded(False)

    def _button(self, text: str, icon, callback, name: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setIcon(self.style().standardIcon(icon))
        button.clicked.connect(callback)
        if name:
            button.setObjectName(name)
        return button

    def _form_label(self, text: str, *, width: int = 116, top: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("formLabel")
        label.setFixedWidth(width)
        alignment = Qt.AlignRight | (Qt.AlignTop if top else Qt.AlignVCenter)
        label.setAlignment(alignment)
        if top:
            label.setContentsMargins(0, 7, 0, 0)
        return label

    def _described_button(self, title: str, description: str, callback) -> tuple[QPushButton, QLabel]:
        button = DescribedActionButton()
        button.setObjectName("describedAction")
        button.clicked.connect(callback)
        layout = QHBoxLayout(button)
        layout.setContentsMargins(10, 2, 8, 2)
        layout.setSpacing(8)

        arrow_label = QLabel()
        arrow_label.setObjectName("describedActionArrow")
        arrow_label.setPixmap(
            self.style().standardIcon(QStyle.SP_ArrowForward).pixmap(QSize(18, 18), QIcon.Normal)
        )
        arrow_label.setFixedSize(18, 18)
        arrow_label.setAlignment(Qt.AlignCenter)
        arrow_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        title_label = QLabel(title)
        title_label.setObjectName("describedActionTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFixedWidth(140)
        title_label.setStyleSheet("background: transparent; border: none;")
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        description_label = QLabel(description)
        description_label.setObjectName("describedActionDescription")
        description_label.setAlignment(Qt.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            "font-size: 10px; background: transparent; border: none; "
            "border-left: 1px solid #3a414d; padding-left: 8px;"
        )
        description_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(arrow_label)
        layout.addWidget(title_label)
        layout.addWidget(description_label, 1)
        button.set_action_labels(title_label, description_label)
        return button, title_label

    def choose_setting_path(self, key: str) -> None:
        current = Path(self.setting_inputs[key].text()).expanduser()
        if key == "DRAFT_FOLDER":
            selected = QFileDialog.getExistingDirectory(self, "选择剪映草稿目录", str(current))
        else:
            file_filter = "图片文件 (*.png *.jpg *.jpeg *.webp)" if key == "BACKGROUND_IMAGE" else "音乐文件 (*.mp3 *.mp4)"
            selected, _ = QFileDialog.getOpenFileName(self, "选择文件", str(current.parent), file_filter)
        if selected:
            self.setting_inputs[key].setText(selected)

    def choose_setting_color(self, key: str) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self.setting_inputs[key].text()), self, "选择颜色")
        if color.isValid():
            self.setting_inputs[key].setText(color.name().upper())

    def _apply_theme_colors(self, value: str) -> None:
        theme = resolve_visual_theme(value)
        values = {
            "TITLE_COLOR": theme.title_color,
            "TITLE_BACKGROUND_COLOR": theme.title_background_color,
            "SUBTITLE_COLOR": theme.subtitle_color,
            "SUBTITLE_BACKGROUND_COLOR": theme.subtitle_background_color,
        }
        for key, color in values.items():
            self.setting_inputs[key].setText(color)
        self.setting_inputs["BACKGROUND_IMAGE"].setText(
            str(default_background_image(PROJECT_ROOT, theme.key))
        )

    def preview_voice(self) -> None:
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "请等待当前流程完成后再试听音色。")
            return
        speaker = self.api_inputs["DOUBAO_TTS_SPEAKER"].text().strip()
        if not speaker:
            QMessageBox.warning(self, "缺少音色 ID", "请先输入豆包 TTS 音色 ID。")
            return
        output = Path(tempfile.gettempdir()) / f"animation_voice_preview_{uuid.uuid4().hex}.wav"
        if self.preview_button is not None:
            self.preview_button.setEnabled(False)
        self.log.appendPlainText(f"试听音色：{speaker}")
        threading.Thread(
            target=self._preview_voice_worker,
            args=(speaker, output),
            daemon=True,
        ).start()

    def _preview_voice_worker(self, speaker: str, output: Path) -> None:
        command = [
            sys.executable,
            "-m",
            "src.commands.preview_voice",
            "--speaker",
            speaker,
            "--output",
            str(output),
        ]
        try:
            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                env=os.environ.copy(),
            )
            self.preview_succeeded.emit(str(output))
        except Exception as exc:
            self.preview_failed.emit(str(exc))

    def _on_preview_succeeded(self, value: str) -> None:
        if self.preview_button is not None:
            self.preview_button.setEnabled(True)
        path = Path(value)
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self.log.appendPlainText(f"试听音频已生成：{path}")
        elif value.strip():
            self.log.appendPlainText(value.strip())

    def _on_preview_failed(self, message: str) -> None:
        if self.preview_button is not None:
            self.preview_button.setEnabled(True)
        self.log.appendPlainText(f"试听失败：{message}")
        QMessageBox.warning(self, "试听失败", message)

    def _current_jianying_draft(self) -> tuple[Path, str]:
        """Resolve the draft selected by the UI without touching pipeline options."""
        draft_folder = resolve_draft_folder(self.setting_inputs["DRAFT_FOLDER"].text())
        package_mode = (
            self.workflow_mode is not None
            and self.workflow_mode.currentText() == WORKFLOW_PORTRAIT_PACKAGE
        )
        package_stage = package_mode and self.workflow_tabs is not None and self.workflow_tabs.currentIndex() == 1
        landscape_master = package_mode and not package_stage
        requested_base_name = self.inputs["draft_name"].text().strip() or safe_topic(self.inputs["topic"].text())
        base_name = requested_base_name
        if package_stage:
            draft_name = base_name if base_name.endswith("_portrait_package") else f"{base_name}_portrait_package"
        elif landscape_master:
            base_name = base_name if base_name.endswith("_landscape_master") else f"{base_name}_landscape_master"
            orientation = self.setting_combos["VIDEO_ORIENTATION"].currentText()
            draft_name = draft_name_for_orientation(base_name, orientation)
            # Older single-step runs created the landscape draft without the
            # workflow marker. Keep those drafts exportable after upgrading.
            if not (draft_folder / draft_name).is_dir():
                legacy_name = draft_name_for_orientation(requested_base_name, orientation)
                try:
                    validate_draft_path(draft_folder, legacy_name)
                except JianyingAutomationError:
                    pass
                else:
                    draft_name = legacy_name
        else:
            orientation = self.setting_combos["VIDEO_ORIENTATION"].currentText()
            draft_name = draft_name_for_orientation(base_name, orientation)
        return draft_folder, draft_name

    def _remember_draft_target_for_options(self, options: Options) -> None:
        base_name = options.draft_name.strip() or f"{safe_topic(options.topic)}_src"
        draft_name = draft_name_for_orientation(base_name, options.orientation)
        self._automation_draft_target = (
            resolve_draft_folder(options.draft_folder),
            draft_name,
        )
        self._automation_export_target = video_export_path(
            OUTPUT_ROOT,
            options.topic,
            orientation_key(options.orientation),
        )

    def _automation_target(self) -> tuple[Path, str]:
        return self._automation_draft_target or self._current_jianying_draft()

    def _export_target_for_draft(self, draft_name: str) -> Path:
        name = draft_name.casefold()
        if "_portrait_package" in name:
            variant = "portrait_package"
        elif "_portrait" in name:
            variant = "portrait"
        else:
            variant = "landscape"
        return video_export_path(OUTPUT_ROOT, self.inputs["topic"].text(), variant)

    def _start_jianying_automation(self) -> None:
        if self._jianying_automation_thread is not None and self._jianying_automation_thread.is_alive():
            QMessageBox.information(self, "正在操作剪映", "上一次剪映操作尚未完成，请稍候。")
            return
        if os.name != "nt" and sys.platform != "darwin":
            self._automation_last_status = "不可用"
            self.refresh_status()
            QMessageBox.information(self, "剪映操作不可用", "第09步的剪映桌面自动化仅支持 Windows 和 macOS。")
            return
        try:
            draft_folder, draft_name = self._automation_target()
            try:
                draft_path = validate_draft_path(draft_folder, draft_name)
            except JianyingAutomationError:
                recovered = find_timestamp_matching_draft(draft_folder, draft_name)
                if recovered is None:
                    raise
                draft_path = recovered
                draft_name = recovered.name
                self._automation_draft_target = (draft_folder, draft_name)
                self.log.appendPlainText(f"草稿名已按时间戳修正为：{draft_name}")
            if draft_path.name != draft_name:
                draft_name = draft_path.name
                self._automation_draft_target = (draft_folder, draft_name)
                self.log.appendPlainText(f"使用剪映实际草稿名：{draft_name}")
        except (KeyError, OSError, JianyingAutomationError) as exc:
            self._automation_last_status = "未就绪"
            self.refresh_status()
            QMessageBox.warning(self, "找不到剪映草稿", str(exc))
            return

        self._automation_last_status = "运行中"
        if self._chain_portrait_after_export:
            self._last_jianying_export_path = None
        export_target = self._automation_export_target or self._export_target_for_draft(draft_name)
        self.log.appendPlainText(f"剪映操作：打开草稿并开始导出 -> {draft_path}")
        self.log.appendPlainText(f"成片将保存到：{export_target}")
        self._set_jianying_automation_enabled(False)

        def worker() -> None:
            try:
                # macOS Jianying may spend over 30 seconds loading a draft
                # with many generated assets.  Keep Windows' normal timeout,
                # but give the macOS open phase enough time to settle.
                automation_timeout = 120.0 if sys.platform == "darwin" else 30.0
                result, export_path = open_draft_and_click_export_with_path(
                    draft_folder,
                    draft_name,
                    timeout=automation_timeout,
                    target_path=export_target,
                )
                self._last_jianying_export_path = export_path
                detail = f"，导出路径：{export_path}" if export_path is not None else ""
                message = f"已打开草稿并完成导出：{result}{detail}"
                self.jianying_automation_succeeded.emit(message)
            except Exception as exc:
                self.jianying_automation_failed.emit(str(exc))

        self._jianying_automation_thread = threading.Thread(target=worker, daemon=True)
        self._jianying_automation_thread.start()

    def run_automation_step(self) -> None:
        """Run step 09 independently once a Jianying draft exists."""

        if self.runner.running:
            QMessageBox.information(self, "正在运行", "请等待第 01～08 步完成后再执行第 09 步。")
            return
        if self.render_mode_combo is not None and self.render_mode_combo.currentData() == "infinite_canvas":
            QMessageBox.information(self, "无限画布无需剪映导出", "当前成片已由 Remotion 直接生成 MP4，不需要打开剪映导出。")
            return
        self._start_jianying_automation()
        self.refresh_status()

    def _set_jianying_automation_enabled(self, enabled: bool) -> None:
        if self.automation_step_button is not None:
            self.automation_step_button.setEnabled(enabled)

    def _on_jianying_automation_succeeded(self, message: str) -> None:
        self._automation_last_status = "完成"
        self._set_jianying_automation_enabled(True)
        self.log.appendPlainText(message)
        if self._chain_portrait_after_export:
            QTimer.singleShot(0, self._continue_portrait_package_after_export)
        elif self._batch_package_phase == "portrait":
            QTimer.singleShot(0, self._wait_for_portrait_batch_export)
        self.refresh_status()

    def _continue_portrait_package_after_export(self) -> None:
        """Find the fresh landscape MP4 and start the portrait wrapper stage."""
        if not self._chain_portrait_after_export:
            return
        if self.runner.running or (
            self._jianying_automation_thread is not None
            and self._jianying_automation_thread.is_alive()
        ):
            QTimer.singleShot(250, self._continue_portrait_package_after_export)
            return

        self._portrait_chain_attempts += 1
        topic = self.inputs["topic"].text().strip()
        projects = discover_landscape_projects(OUTPUT_ROOT)
        project = next((item for item in projects if item.topic == topic), None)
        if project is None:
            if self._portrait_chain_attempts == 1 or self._portrait_chain_attempts % 30 == 0:
                self.log.appendPlainText("等待横版项目写入完成，准备查找导出视频…")
            QTimer.singleShot(1000, self._continue_portrait_package_after_export)
            return

        source = self._last_jianying_export_path
        if source is None:
            self._chain_portrait_after_export = False
            message = "剪映导出已完成，但没有读取到导出设置中的 MP4 路径，竖版包装未启动。"
            self.log.appendPlainText(message)
            QMessageBox.warning(self, "未读取到导出路径", message)
            return
        try:
            source_is_fresh = source.is_file()
        except OSError:
            source_is_fresh = False
        if not source_is_fresh:
            if self._portrait_chain_attempts == 1 or self._portrait_chain_attempts % 30 == 0:
                self.log.appendPlainText("横版导出已完成，等待指定 MP4 文件落盘…")
            QTimer.singleShot(1000, self._continue_portrait_package_after_export)
            return

        self.package_state.selected_project = str(project.project_dir)
        self.refresh_landscape_projects()
        selected_index = next(
            (
                index
                for index, item in enumerate(self.landscape_projects)
                if item.project_dir == project.project_dir
            ),
            -1,
        )
        if self.package_project_combo is None or selected_index < 0:
            QTimer.singleShot(1000, self._continue_portrait_package_after_export)
            return
        self.package_project_combo.setCurrentIndex(selected_index)
        assert self.package_source_video is not None
        self.package_source_video.setText(str(source))
        self._remember_package_source_video()
        self._chain_portrait_after_export = False
        self._portrait_chain_attempts = 0
        if self._batch_package_options:
            current = self._batch_package_options[self._batch_package_index]
            self.draft_name_is_automatic = False
            self.inputs["draft_name"].setText(current.draft_name)
            self._batch_package_phase = "portrait"
            self._last_jianying_export_path = None
            self._portrait_chain_attempts = 0
            self.batch_status_label.setText(
                f"{self._batch_package_index + 1}/{len(self._batch_package_options)} 竖版包装"
            )
        if self.workflow_tabs is not None:
            self.workflow_tabs.setCurrentIndex(1)
        self.log.appendPlainText(f"已找到横版 MP4：{source}")
        self.log.appendPlainText("开始串联竖版包装…")
        self.run_portrait_package(clear_log=False)

    def _start_portrait_batch_item(self) -> None:
        if not self._batch_package_options:
            return
        if self._batch_package_index < 0 or self._batch_package_index >= len(self._batch_package_options):
            self._clear_portrait_batch()
            return
        options = self._batch_package_options[self._batch_package_index]
        self.draft_name_is_automatic = False
        self.inputs["topic"].setText(options.topic)
        self.inputs["draft_name"].setText(options.draft_name)
        self._remember_draft_target_for_options(options)
        self._automation_last_status = "未执行"
        self._chain_portrait_after_export = options.render_mode == "jianying"
        self._portrait_chain_attempts = 0
        self._batch_package_phase = "landscape"
        self._auto_run_step09 = options.render_mode == "jianying"
        if self.workflow_tabs is not None:
            self.workflow_tabs.setCurrentIndex(0)
        self.batch_status_label.setText(
            f"{self._batch_package_index + 1}/{len(self._batch_package_options)} 横版母片"
        )
        self.runner.start(options)

    def _wait_for_portrait_batch_export(self) -> None:
        """Advance only after the final portrait MP4 is present on disk."""
        if not self._batch_package_options or self._batch_package_phase != "portrait":
            return
        if self.runner.running or (
            self._jianying_automation_thread is not None
            and self._jianying_automation_thread.is_alive()
        ):
            QTimer.singleShot(250, self._wait_for_portrait_batch_export)
            return

        self._portrait_chain_attempts += 1
        export_path = self._last_jianying_export_path
        if export_path is None:
            message = "竖版包装已完成，但剪映没有返回最终 MP4 的导出路径，批量任务已停止。"
            self._clear_portrait_batch()
            self.log.appendPlainText(message)
            QMessageBox.warning(self, "未读取到竖版导出路径", message)
            return

        if export_path.suffix.lower() != ".mp4":
            message = f"竖版包装导出路径不是 MP4：{export_path}，批量任务已停止。"
            self._clear_portrait_batch()
            self.log.appendPlainText(message)
            QMessageBox.warning(self, "导出格式不正确", message)
            return

        try:
            export_ready = export_path.is_file()
        except OSError:
            export_ready = False
        if export_ready:
            self.log.appendPlainText(f"竖版最终 MP4 已导出：{export_path}")
            self._advance_portrait_batch()
            return

        if self._portrait_chain_attempts == 1 or self._portrait_chain_attempts % 30 == 0:
            self.log.appendPlainText(f"等待竖版最终 MP4 落盘：{export_path}")
        QTimer.singleShot(1000, self._wait_for_portrait_batch_export)

    def _advance_portrait_batch(self) -> None:
        if not self._batch_package_options:
            return
        if self.runner.running or (
            self._jianying_automation_thread is not None
            and self._jianying_automation_thread.is_alive()
        ):
            QTimer.singleShot(100, self._advance_portrait_batch)
            return
        completed_topic = self._batch_package_options[self._batch_package_index].topic
        self._batch_package_index += 1
        if self._batch_package_index >= len(self._batch_package_options):
            total = len(self._batch_package_options)
            self.batch_status_label.setText(f"成功 {total}/{total}")
            self.log.appendPlainText(f"横版母片转竖版批量任务完成：成功 {total}/{total}")
            self._clear_portrait_batch()
            self.refresh_status()
            return
        self.log.appendPlainText(f"主题完成：{completed_topic}，开始下一个主题。")
        self._start_portrait_batch_item()
        self.refresh_status()

    def _clear_portrait_batch(self) -> None:
        self._batch_package_options = []
        self._batch_package_index = -1
        self._batch_package_phase = ""

    def _on_jianying_automation_failed(self, message: str) -> None:
        self._automation_last_status = "失败"
        self._chain_portrait_after_export = False
        self._clear_portrait_batch()
        self._set_jianying_automation_enabled(True)
        self.log.appendPlainText(f"剪映操作失败：{message}")
        QMessageBox.warning(self, "剪映操作失败", message)
        self.refresh_status()

    def choose_douyin_video(self) -> None:
        assert self.douyin_video_input is not None
        current = Path(self.douyin_video_input.text()).expanduser()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择抖音视频",
            str(current.parent),
            "视频文件 (*.mp4 *.mov *.m4v *.avi)",
        )
        if selected:
            self.douyin_video_input.setText(selected)
            self.refresh_status()

    def choose_douyin_cover(self) -> None:
        assert self.douyin_cover_input is not None
        current = Path(self.douyin_cover_input.text()).expanduser()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择作品封面",
            str(current.parent),
            "图片文件 (*.png *.jpg *.jpeg *.webp)",
        )
        if selected:
            self.douyin_cover_input.setText(selected)
            self.refresh_status()

    def _update_publish_title(self, value: str) -> None:
        if self.douyin_title_input is not None and (
            not self.douyin_title_input.text().strip()
            or self.douyin_title_input.text().strip() == self._douyin_last_auto_title
        ):
            self.douyin_title_input.setText(value.strip())

    def _publish_metadata_context(self, topic: str) -> str:
        parts = []
        if self.context_input is not None:
            parts.append(self.context_input.toPlainText().strip())
        copy_path = OUTPUT_ROOT / safe_topic(topic) / "wenan.txt"
        try:
            if copy_path.is_file():
                parts.append(copy_path.read_text(encoding="utf-8-sig")[:6000])
        except OSError:
            pass
        return "\n\n".join(part for part in parts if part)

    def generate_douyin_metadata(self) -> None:
        if self._douyin_metadata_thread is not None and self._douyin_metadata_thread.is_alive():
            QMessageBox.information(self, "正在生成", "标题和话题正在生成，请稍候。")
            return
        topic = self.inputs["topic"].text().strip()
        if not topic:
            QMessageBox.information(self, "缺少主题", "请先填写当前主题。")
            return
        context = self._publish_metadata_context(topic)
        self.log.appendPlainText("正在生成抖音标题和相关话题...")
        self._set_douyin_metadata_enabled(False)

        def worker() -> None:
            try:
                title, topics = generate_publish_metadata(topic, context=context)
                self.douyin_metadata_succeeded.emit((title, topics))
            except Exception as exc:
                self.douyin_metadata_failed.emit(str(exc))

        self._douyin_metadata_thread = threading.Thread(target=worker, daemon=True)
        self._douyin_metadata_thread.start()

    def _set_douyin_metadata_enabled(self, enabled: bool) -> None:
        if hasattr(self, "douyin_metadata_button") and self.douyin_metadata_button is not None:
            self.douyin_metadata_button.setEnabled(enabled)

    def _on_douyin_metadata_succeeded(self, metadata: object) -> None:
        self._set_douyin_metadata_enabled(True)
        title, topics = metadata
        if self.douyin_title_input is not None:
            self.douyin_title_input.setText(str(title))
            self._douyin_last_auto_title = str(title)
        if self.douyin_topics_input is not None:
            topic_text = " ".join(str(item) for item in topics)
            self.douyin_topics_input.setText(topic_text)
        self.log.appendPlainText(f"已生成发布标题和话题：{title} / {' '.join(topics)}")
        self.refresh_status()
        if self._pending_publish_after_metadata:
            self._pending_publish_after_metadata = False
            QTimer.singleShot(0, self.publish_current_video_to_douyin)

    def _on_douyin_metadata_failed(self, message: str) -> None:
        self._pending_publish_after_metadata = False
        self._set_douyin_metadata_enabled(True)
        self.log.appendPlainText(f"标题和话题生成失败：{message}")
        QMessageBox.warning(self, "生成发布信息失败", message)

    def scan_publish_assets(self, *, preserve_manual: bool = False) -> None:
        if self.douyin_video_input is None or self.douyin_cover_input is None:
            return
        topic = self.inputs["topic"].text().strip()
        video, cover = discover_publish_assets(
            topic,
            output_root=OUTPUT_ROOT,
            preferred_video=self._last_jianying_export_path,
            preferred_cover=self.cover_artifact_path() if topic else None,
            home=Path.home(),
        )
        current_video = self.douyin_video_input.text().strip()
        current_cover = self.douyin_cover_input.text().strip()
        can_replace_video = not preserve_manual or not current_video or current_video == self._douyin_last_auto_video
        can_replace_cover = not preserve_manual or not current_cover or current_cover == self._douyin_last_auto_cover
        if video is not None and can_replace_video:
            self.douyin_video_input.setText(str(video))
            self._douyin_last_auto_video = str(video)
        if cover is not None and can_replace_cover:
            self.douyin_cover_input.setText(str(cover))
            self._douyin_last_auto_cover = str(cover)
        if self.douyin_title_input is not None and not self.douyin_title_input.text().strip():
            self.douyin_title_input.setText(topic)
            self._douyin_last_auto_title = topic
        found = []
        if video is not None:
            found.append("视频")
        if cover is not None:
            found.append("封面")
        if self.publish_status_label is not None:
            self.publish_status_label.setText("已找到：" + "、".join(found) if found else "未找到素材")
        self.refresh_status()

    def open_douyin_page(self) -> None:
        try:
            profile = open_douyin_upload_page()
        except DouyinPublishError as exc:
            QMessageBox.warning(self, "打开抖音失败", str(exc))
            return
        self.log.appendPlainText(f"已打开抖音创作中心，专用浏览器配置：{profile}")

    def _douyin_publish_request_or_start_metadata(self) -> DouyinPublishRequest | None:
        assert self.douyin_video_input is not None
        assert self.douyin_cover_input is not None
        assert self.douyin_title_input is not None
        assert self.douyin_topics_input is not None
        assert self.douyin_collection_input is not None
        assert self.douyin_description_input is not None
        self.scan_publish_assets(preserve_manual=True)
        topic = self.inputs["topic"].text().strip()
        title = self.douyin_title_input.text().strip()
        topics = self.douyin_topics_input.text().strip()
        if topic and (not topics or not title):
            self._pending_publish_after_metadata = True
            self.generate_douyin_metadata()
            self.log.appendPlainText("发布前先生成标题和话题，生成完成后将继续发布")
            return None
        request = DouyinPublishRequest(
            video_path=Path(self.douyin_video_input.text().strip()),
            cover_path=Path(self.douyin_cover_input.text().strip()) if self.douyin_cover_input.text().strip() else None,
            title=self.douyin_title_input.text(),
            description=self.douyin_description_input.toPlainText(),
            topics=self.douyin_topics_input.text(),
            collection=self.douyin_collection_input.text(),
        )
        try:
            return request.validated()
        except DouyinPublishError as exc:
            QMessageBox.warning(self, "发布参数不完整", str(exc))
            return None

    def _start_douyin_publish(self, request: DouyinPublishRequest, *, auto_click: bool) -> None:
        self.log.appendPlainText(
            ("抖音发布开始：" if auto_click else "抖音发布准备开始：")
            + str(request.video_path)
        )
        self._douyin_last_publish_succeeded = False
        self._douyin_last_publish_prepared = False
        self._set_douyin_publish_enabled(False)

        def worker() -> None:
            try:
                if auto_click:
                    publish_to_douyin(request)
                    self.douyin_publish_succeeded.emit(f"抖音发布完成：{request.video_path.name}")
                else:
                    prepare_douyin_publish(request)
                    self.douyin_publish_prepared.emit(
                        f"抖音发布页已准备好：{request.video_path.name}，请在浏览器中检查后点击“发布”"
                    )
            except Exception as exc:
                self.douyin_publish_failed.emit(str(exc))

        self._douyin_publish_thread = threading.Thread(target=worker, daemon=True)
        self._douyin_publish_thread.start()

    def publish_current_video_to_douyin(self) -> None:
        if self._douyin_publish_thread is not None and self._douyin_publish_thread.is_alive():
            QMessageBox.information(self, "正在发布", "抖音发布任务正在执行，请稍候。")
            return
        auto_click = bool(self.douyin_auto_publish_checkbox and self.douyin_auto_publish_checkbox.isChecked())
        request = self._douyin_publish_request_or_start_metadata()
        if request is None:
            return
        self._start_douyin_publish(request, auto_click=auto_click)

    def _set_douyin_publish_enabled(self, enabled: bool) -> None:
        if self.douyin_open_button is not None:
            self.douyin_open_button.setEnabled(enabled)
        if self.douyin_publish_button is not None:
            video_ready = bool(self.douyin_video_input and Path(self.douyin_video_input.text().strip()).is_file())
            self.douyin_publish_button.setEnabled(enabled and video_ready)
        if self.douyin_auto_publish_checkbox is not None:
            self.douyin_auto_publish_checkbox.setEnabled(enabled)

    def _on_douyin_publish_succeeded(self, message: str) -> None:
        self._douyin_last_publish_succeeded = True
        self._douyin_last_publish_prepared = False
        self._set_douyin_publish_enabled(True)
        self.log.appendPlainText(message)
        self.refresh_status()
        QMessageBox.information(self, "抖音发布完成", message)

    def _on_douyin_publish_prepared(self, message: str) -> None:
        self._douyin_last_publish_succeeded = False
        self._douyin_last_publish_prepared = True
        self._set_douyin_publish_enabled(True)
        self.log.appendPlainText(message)
        self.refresh_status()
        QMessageBox.information(self, "抖音发布页已准备好", message)

    def _on_douyin_publish_failed(self, message: str) -> None:
        self._douyin_last_publish_prepared = False
        self._set_douyin_publish_enabled(True)
        self.log.appendPlainText(f"抖音发布失败：{message}")
        self.refresh_status()
        QMessageBox.warning(self, "抖音发布失败", message)

    def save_settings(self) -> None:
        if not self._persist_settings():
            return
        QMessageBox.information(self, "保存成功", "接口配置和应用设置已保存。")

    def _persist_settings(self) -> bool:
        api_values = {key: edit.text().strip() for key, edit in self.api_inputs.items()}
        api_values.update({key: combo.currentText().strip() for key, combo in self.api_combos.items()})
        app_values = {key: edit.text().strip() for key, edit in self.setting_inputs.items()}
        app_values.update({key: combo.currentText().strip() for key, combo in self.setting_combos.items()})
        app_values["VISUAL_THEME"] = resolve_visual_theme(
            app_values["VISUAL_THEME"],
            settings_path=APP_SETTINGS_PATH,
        ).key
        app_values["DRAFT_FOLDER"] = str(resolve_draft_folder(app_values["DRAFT_FOLDER"]))
        try:
            save_app_settings(app_values, APP_SETTINGS_PATH)
            update_env_file(ENV_PATH, api_values)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入本地配置：\n{exc}")
            return False
        self.app_settings = app_values
        os.environ.update(api_values)
        return True

    def _workflow_orientation(self) -> str:
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        return "\u7ad6\u5c4f" if mode == WORKFLOW_NATIVE_PORTRAIT else "\u6a2a\u5c4f"

    def _read_options(self) -> Options:
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        clean_landscape_master = mode == WORKFLOW_PORTRAIT_PACKAGE
        return Options(
            topic=self.inputs["topic"].text().strip(),
            story_world="",
            target_chars=self.inputs["target_chars"].text().strip(),
            context=self.context_input.toPlainText().strip() if self.context_input is not None else "",
            image_model=self.image_model_setting.currentText().strip(),
            visual_theme=self.setting_combos["VISUAL_THEME"].currentText().strip(),
            orientation=self._workflow_orientation(),
            run_images=True,
            draft_name=self.inputs["draft_name"].text().strip(),
            draft_folder=self.setting_inputs["DRAFT_FOLDER"].text().strip(),
            include_background_music=True,
            background_music=self.setting_inputs["BACKGROUND_MUSIC"].text().strip(),
            background_image=self.setting_inputs["BACKGROUND_IMAGE"].text().strip(),
            include_background=not (self.background_black_checkbox is not None and self.background_black_checkbox.isChecked()),
            include_title=self._workflow_orientation() != "\u6a2a\u5c4f",
            include_subtitles=not clean_landscape_master,
            render_mode=(
                self.render_mode_combo.currentData()
                if self.render_mode_combo is not None
                else "jianying"
            ),
        )

    def _on_render_mode_changed(self, _index: int = 0) -> None:
        mode = self.render_mode_combo.currentData() if self.render_mode_combo is not None else "jianying"
        landscape = self._workflow_orientation() == "横屏"
        if self.render_mode_combo is not None and mode == "infinite_canvas" and not landscape:
            self.render_mode_combo.setCurrentIndex(0)
            QMessageBox.information(self, "无限画布仅支持横版", "这套实验效果目前输出 16:9 横版成片，已切回剪映流程。")
            return
        if mode == "infinite_canvas":
            self._auto_run_step09 = False
            self._chain_portrait_after_export = False
        self._update_render_mode_steps()
        self._update_primary_action()
        self.refresh_status()

    def _update_render_mode_steps(self) -> None:
        """Show shared production steps plus the selected renderer's own stages."""
        infinite = self.render_mode_combo is not None and self.render_mode_combo.currentData() == "infinite_canvas"
        shared_keys = {"copy", "voice", "shots", "storyboard_prompts", "prompts", "images"}
        for key, row in self.step_rows.items():
            visible = key.startswith("infinite_") if infinite else not key.startswith("infinite_")
            if infinite and key in shared_keys:
                visible = True
            if infinite and key in {"layout", "draft", "automation"}:
                visible = False
            row.setVisible(visible)
        if self.steps_note is not None:
            self.steps_note.setText(
                "共享 01～06 先准备文案、配音、分镜和图片；然后 07～10 依次准备素材、规划镜头、生成画面并合成视频。"
                if infinite
                else "图片素材会直接用于布局编译和剪映草稿生成。"
            )

    def _change_workflow_mode(self, index: int) -> None:
        del index
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        packaging = mode == WORKFLOW_PORTRAIT_PACKAGE
        cover = mode == WORKFLOW_COVER
        publish = mode == WORKFLOW_PUBLISH
        self._sync_workflow_navigation(mode)
        if self.workflow_tabs is not None:
            self.workflow_tabs.setTabVisible(0, not cover)
            self.workflow_tabs.setTabVisible(1, packaging)
            self.workflow_tabs.setTabVisible(2, cover)
            self.workflow_tabs.setTabVisible(3, publish)
            self.workflow_tabs.tabBar().setVisible(packaging and not cover and not publish)
            self.workflow_tabs.setCurrentIndex(3 if publish else (2 if cover else 0))
        orientation_combo = self.setting_combos.get("VIDEO_ORIENTATION")
        if orientation_combo is not None:
            orientation_combo.setCurrentText(self._workflow_orientation())
        if self.render_mode_combo is not None:
            self.render_mode_combo.setEnabled(
                not cover
                and not publish
                and mode != WORKFLOW_PORTRAIT_PACKAGE
                and self._workflow_orientation() == "横屏"
            )
            if self._workflow_orientation() != "横屏" and self.render_mode_combo.currentData() == "infinite_canvas":
                self.render_mode_combo.setCurrentIndex(0)
        self._update_render_mode_steps()
        self._update_primary_action()
        if publish:
            self.scan_publish_assets(preserve_manual=True)
        if self.batch_topic_label is not None:
            self.batch_topic_label.setVisible(True)
        if self.batch_topic_generate_button is not None:
            self.batch_topic_generate_button.setVisible(True)
        if self.topic_catalog_button is not None:
            self.topic_catalog_button.setVisible(True)
        self.batch_topics.setVisible(True)
        self.batch_status_label.setVisible(True)
        self._update_project_fields_for_stage()
        self._update_cover_prompt_preview()
        if not packaging:
            self._update_package_project_label()

    def _change_workflow_stage(self, index: int) -> None:
        self._update_primary_action(index)
        self._update_project_fields_for_stage()
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        if mode == WORKFLOW_PORTRAIT_PACKAGE and index == 1:
            self.refresh_landscape_projects()

    def _update_project_fields_for_stage(self) -> None:
        # Theme context remains visible and editable across all three stages.
        if self.project_panel is not None:
            project_layout = self.project_panel.layout()
            if project_layout is not None:
                project_layout.activate()
            self.project_panel.updateGeometry()
            parent = self.project_panel.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.layout().activate()
        if self.project_settings_scroll is not None:
            self.project_settings_scroll.updateGeometry()
            QTimer.singleShot(0, self._rebalance_workflow_splitter)

    def _update_primary_action(self, _index: int = 0) -> None:
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        packaging = mode == WORKFLOW_PORTRAIT_PACKAGE
        cover = mode == WORKFLOW_COVER
        publish = mode == WORKFLOW_PUBLISH
        package_stage = packaging and self.workflow_tabs is not None and self.workflow_tabs.currentIndex() == 1
        if self.workflow_actions is not None:
            self.workflow_actions.setVisible(not publish)
        if publish:
            self.start_button.setText("发布作品")
            self.start_button.setFixedWidth(116)
            self.start_button.setToolTip("上传视频、封面、标题和话题到抖音")
        elif cover:
            self.start_button.setText("生成封面图")
            self.start_button.setFixedWidth(124)
            size = self._current_cover_size()
            self.start_button.setToolTip(f"生成当前主题的 {size[2]}×{size[3]} {size[5]}作品封面")
        elif package_stage:
            self.start_button.setText("生成竖版包装草稿")
            self.start_button.setFixedWidth(164)
            self.start_button.setToolTip("使用已导出的横版 MP4 生成竖版包装草稿")
        elif packaging:
            self.start_button.setText("生成母片并转竖版")
            self.start_button.setFixedWidth(154)
            self.start_button.setToolTip("生成横版母片、自动导出 MP4，并将导出视频串联到竖版包装")
        else:
            self.start_button.setText("开始执行")
            self.start_button.setFixedWidth(116)
            self.start_button.setToolTip("")
        if self.continue_button is not None:
            can_start_from_copy = not package_stage and not cover and not publish
            self.continue_button.setVisible(can_start_from_copy)
            if packaging:
                self.continue_button.setText("从文案生成母片")
                self.continue_button.setFixedWidth(138)
                self.continue_button.setToolTip("使用当前 wenan.txt，跳过第 01 步，生成横版母片；完成后再进行竖版包装")
            else:
                self.continue_button.setText("从文案继续")
                self.continue_button.setFixedWidth(126)
                self.continue_button.setToolTip("使用当前 wenan.txt，跳过第 01 步，重跑第 02～08 步（会重生成图片）")
        self._update_workflow_action_visibility()

    def _update_workflow_action_visibility(self) -> None:
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        cover = mode == WORKFLOW_COVER
        publish = mode == WORKFLOW_PUBLISH
        package_stage = (
            mode == WORKFLOW_PORTRAIT_PACKAGE
            and self.workflow_tabs is not None
            and self.workflow_tabs.currentIndex() == 1
        )
        running = self.runner.running
        if self.workflow_actions is not None:
            self.workflow_actions.setVisible(not publish and (not cover or running))
        if self.video_mode_combo is not None:
            self.video_mode_combo.setEnabled(not running)
        self.stop_button.setVisible(running and not publish)
        self.start_button.setVisible(not running and not cover and not publish)
        self.batch_button.setVisible(not running and not cover and not publish)
        if self.cover_generate_button is not None:
            self.cover_generate_button.setVisible(not running)
        if self.continue_button is not None:
            self.continue_button.setVisible(
                not running and not package_stage and not cover and not publish
            )

    def _selected_landscape_project(self) -> LandscapeProject | None:
        if self.package_project_combo is None:
            return None
        index = self.package_project_combo.currentIndex()
        if 0 <= index < len(self.landscape_projects):
            return self.landscape_projects[index]
        return None

    def _landscape_project_dir(self) -> Path | None:
        project = self._selected_landscape_project()
        return project.project_dir if project is not None else None

    def refresh_landscape_projects(self) -> None:
        if self.package_project_combo is None:
            return
        current = self._landscape_project_dir()
        preferred = str(current) if current is not None else self.package_state.selected_project
        self.landscape_projects = discover_landscape_projects(OUTPUT_ROOT)
        self.package_project_combo.blockSignals(True)
        self.package_project_combo.clear()
        selected_index = 0
        if self.landscape_projects:
            for index, project in enumerate(self.landscape_projects):
                self.package_project_combo.addItem(project.topic, str(project.project_dir))
                self.package_project_combo.setItemData(index, str(project.project_dir), Qt.ToolTipRole)
                if preferred and str(project.project_dir) == preferred:
                    selected_index = index
            self.package_project_combo.setEnabled(True)
            self.package_project_combo.setCurrentIndex(selected_index)
        else:
            self.package_project_combo.addItem("\u672a\u53d1\u73b0\u53ef\u7528\u7684\u6a2a\u7248\u9879\u76ee")
            self.package_project_combo.setEnabled(False)
        self.package_project_combo.blockSignals(False)
        self._on_package_project_changed(self.package_project_combo.currentIndex())

    def _on_package_project_changed(self, _index: int) -> None:
        project = self._selected_landscape_project()
        if project is None:
            if self.package_project_label is not None:
                self.package_project_label.setText("\u8bf7\u5148\u751f\u6210\u4e00\u4e2a\u6a2a\u7248\u9879\u76ee")
            if self.package_source_video is not None:
                self.package_source_video.clear()
            return

        self.package_state.selected_project = str(project.project_dir)
        self.inputs["topic"].setText(project.topic)
        self.draft_name_is_automatic = True
        self.inputs["draft_name"].setText(f"{safe_topic(project.topic)}_{self.draft_timestamp}")
        self._update_package_project_label()

        remembered = self.package_state.source_videos.get(str(project.project_dir), "")
        source = Path(remembered).expanduser() if remembered else None
        if source is None or not source.is_file():
            source = find_matching_landscape_video(project, project_root=PROJECT_ROOT)
        if self.package_source_video is not None:
            self.package_source_video.setText(str(source) if source is not None else "")
        if source is not None:
            self.package_state.source_videos[str(project.project_dir)] = str(source)
        else:
            self.package_state.source_videos.pop(str(project.project_dir), None)
        self._save_package_state()
        self.refresh_status()

    def _update_package_project_label(self, _value: str = "") -> None:
        if self.package_project_label is not None:
            project_dir = self._landscape_project_dir()
            self.package_project_label.setText(
                str(project_dir) if project_dir is not None else "\u672a\u9009\u62e9\u6a2a\u7248\u9879\u76ee"
            )

    def _remember_package_source_video(self) -> None:
        project = self._selected_landscape_project()
        if project is None or self.package_source_video is None:
            return
        source = self.package_source_video.text().strip()
        if source:
            self.package_state.source_videos[str(project.project_dir)] = str(Path(source).expanduser().resolve())
        else:
            self.package_state.source_videos.pop(str(project.project_dir), None)
        self._save_package_state()

    def _save_package_state(self) -> None:
        try:
            save_portrait_package_state(UI_STATE_PATH, self.package_state)
        except OSError as exc:
            self.log.appendPlainText(f"\u65e0\u6cd5\u4fdd\u5b58\u7ad6\u7248\u5305\u88c5\u9009\u62e9: {exc}")

    def choose_package_source_video(self) -> None:
        assert self.package_source_video is not None
        current = Path(self.package_source_video.text()).expanduser()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "\u9009\u62e9\u6a2a\u5c4f\u6210\u7247",
            str(current.parent),
            "Video files (*.mp4 *.mov *.m4v)",
        )
        if selected:
            self.package_source_video.setText(selected)
            self._remember_package_source_video()

    def run_landscape_master(self) -> None:
        if self.runner.running:
            QMessageBox.information(self, "\u6b63\u5728\u8fd0\u884c", "\u5f53\u524d\u4efb\u52a1\u5c1a\u672a\u5b8c\u6210\u3002")
            return
        if not self._persist_settings():
            return
        options = reuse_completed_materials(self._read_options())
        base_name = options.draft_name.strip() or safe_topic(options.topic)
        landscape_name = base_name if base_name.endswith("_landscape_master") else f"{base_name}_landscape_master"
        options = replace(options, draft_name=landscape_name)
        self._remember_draft_target_for_options(options)
        self.log.clear()
        self._automation_last_status = "未执行"
        self._chain_portrait_after_export = options.render_mode == "jianying"
        self._portrait_chain_attempts = 0
        self._auto_run_step09 = False
        self._focus_workflow_view()
        self.runner.start(options)
        self.refresh_status()

    def run_portrait_package(self, *, clear_log: bool = True) -> None:
        if self.runner.running:
            QMessageBox.information(self, "\u6b63\u5728\u8fd0\u884c", "\u5f53\u524d\u4efb\u52a1\u5c1a\u672a\u5b8c\u6210\u3002")
            return
        assert self.package_source_video is not None
        assert self.package_title_checkbox is not None
        assert self.package_subtitle_checkbox is not None
        assert self.package_black_background_checkbox is not None
        project = self._selected_landscape_project()
        if project is None:
            QMessageBox.warning(self, "\u7f3a\u5c11\u6a2a\u7248\u9879\u76ee", "\u8bf7\u5148\u4ece\u5217\u8868\u4e2d\u9009\u62e9\u4e00\u4e2a\u6a2a\u7248\u9879\u76ee\u3002")
            return
        source_video = Path(self.package_source_video.text().strip()).expanduser()
        if not source_video.is_file():
            QMessageBox.warning(self, "\u7f3a\u5c11\u6a2a\u5c4f\u6210\u7247", "\u8bf7\u5148\u9009\u62e9\u5df2\u5bfc\u51fa\u7684\u6a2a\u5c4f MP4\u3002")
            return
        project_dir = project.project_dir
        if self.package_subtitle_checkbox.isChecked() and not (project_dir / "timeline.csv").is_file():
            QMessageBox.warning(
                self,
                "\u7f3a\u5c11\u65f6\u95f4\u7ebf",
                f"\u6ca1\u6709\u627e\u5230\u5173\u8054\u6a2a\u5c4f\u9879\u76ee\u7684 timeline.csv\uff1a{project_dir}",
            )
            return
        if not self._persist_settings():
            return
        self._remember_package_source_video()
        base_name = self.inputs["draft_name"].text().strip() or safe_topic(project.topic)
        draft_name = base_name if base_name.endswith("_portrait_package") else f"{base_name}_portrait_package"
        self._automation_draft_target = (
            resolve_draft_folder(self.setting_inputs["DRAFT_FOLDER"].text()),
            draft_name,
        )
        self._automation_export_target = video_export_path(
            OUTPUT_ROOT,
            project.topic,
            "portrait_package",
        )
        title = project.topic if self.package_title_checkbox.isChecked() else ""
        command = build_portrait_package_command(
            project_dir,
            source_video,
            draft_folder=self.setting_inputs["DRAFT_FOLDER"].text(),
            draft_name=draft_name,
            project_title=title,
            visual_theme=self.setting_combos["VISUAL_THEME"].currentText(),
            include_subtitles=self.package_subtitle_checkbox.isChecked(),
            include_background=not self.package_black_background_checkbox.isChecked(),
        )
        if clear_log:
            self.log.clear()
        self._automation_last_status = "未执行"
        self._chain_portrait_after_export = False
        self._auto_run_step09 = False
        self._focus_workflow_view()
        self.runner.start_commands(
            [("\u7ad6\u5c4f\u5305\u88c5", command)],
            portrait_package_dir(project_dir),
        )
        self.refresh_status()

    def run_pipeline(self) -> None:
        if self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_PUBLISH:
            self.publish_current_video_to_douyin()
            return
        if self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_COVER:
            self.run_cover_pipeline()
            return
        if self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_PORTRAIT_PACKAGE:
            package_stage = self.workflow_tabs is not None and self.workflow_tabs.currentIndex() == 1
            if package_stage:
                self.run_portrait_package()
            else:
                self.run_landscape_master()
            return
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "流程正在执行中。")
            return
        if not self._persist_settings():
            return
        self.log.clear()
        options = reuse_completed_materials(self._read_options())
        if options.run_draft:
            self._remember_draft_target_for_options(options)
        self._automation_last_status = "未执行" if options.run_draft else self._automation_last_status
        self._chain_portrait_after_export = False
        self._auto_run_step09 = options.run_draft and options.render_mode == "jianying"
        self._focus_workflow_view()
        self.runner.start(options)
        self.refresh_status()

    def run_cover_pipeline(self) -> None:
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "当前任务尚未完成，请稍后生成封面。")
            return
        if not self._persist_settings():
            return
        topic = self.inputs["topic"].text().strip()
        if not topic:
            QMessageBox.information(self, "缺少主题", "请先填写主题。")
            return
        try:
            command, output = build_cover_command(
                topic,
                context=self.context_input.toPlainText().strip() if self.context_input is not None else "",
                image_model=self.image_model_setting.currentText(),
                image_quality=self.api_combos.get("IMAGE_QUALITY").currentText()
                if self.api_combos.get("IMAGE_QUALITY") is not None else "",
                visual_theme=self.setting_combos["VISUAL_THEME"].currentText(),
                cover_size=self._current_cover_size()[0],
                overwrite=True,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "封面生成失败", str(exc))
            return
        self.log.clear()
        self._focus_workflow_view()
        self.log.setFocus(Qt.OtherFocusReason)
        self.runner.start_commands([("作品封面", command)], output.parent)
        self.refresh_status()

    def run_from_copywriting(self) -> None:
        """Run every downstream step using the current manually edited copy."""
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "流程正在执行中。")
            return
        packaging = self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_PORTRAIT_PACKAGE
        package_stage = packaging and self.workflow_tabs is not None and self.workflow_tabs.currentIndex() == 1
        if package_stage:
            QMessageBox.information(self, "请先生成横版母片", "竖版包装需要一个已经导出的横版视频，请先回到“横版母片”页生成并导出视频。")
            return
        if not self._persist_settings():
            return
        options = self._read_options()
        copy_path = self.output_dir() / "wenan.txt"
        try:
            if not copy_path.is_file() or not copy_path.read_text(encoding="utf-8-sig").strip():
                raise ValueError("当前主题还没有可用的 wenan.txt")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "缺少文案", f"请先生成或编辑文案：\n{copy_path}\n\n{exc}")
            return
        options = replace(
            options,
            run_copy=False,
            run_voice=True,
            run_shots=True,
            run_storyboard_prompts=True,
            run_prompts=True,
            run_images=True,
            overwrite_images=True,
            run_layout=True,
            run_draft=True,
        )
        if packaging:
            base_name = options.draft_name.strip() or safe_topic(options.topic)
            if not base_name.endswith("_landscape_master"):
                options = replace(options, draft_name=f"{base_name}_landscape_master")
        self._remember_draft_target_for_options(options)
        self.log.clear()
        self._automation_last_status = "未执行"
        self._chain_portrait_after_export = packaging and not package_stage
        self._portrait_chain_attempts = 0
        self._auto_run_step09 = options.render_mode == "jianying"
        self._focus_workflow_view()
        self.runner.start(options)
        self.refresh_status()

    def run_batch_pipeline(self) -> None:
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "流程正在执行中。")
            return
        topics = parse_batch_topics(self.batch_topics.toPlainText())
        if not topics:
            QMessageBox.information(self, "没有主题", "请先录入批量主题。")
            return
        if not self._persist_settings():
            return
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        options = [
            reuse_completed_materials(item)
            for item in build_batch_options(self._read_options(), topics, batch_id=batch_id)
        ]
        self.log.clear()
        self._auto_run_step09 = False
        self._chain_portrait_after_export = False
        self._focus_workflow_view()
        packaging = (
            self.workflow_mode is not None
            and self.workflow_mode.currentText() == WORKFLOW_PORTRAIT_PACKAGE
        )
        if packaging:
            if os.name != "nt" and sys.platform != "darwin":
                QMessageBox.warning(
                    self,
                    "批量串联不可用",
                    "横版母片转竖版的批量串联需要 Windows 或 macOS 上的剪映桌面自动化。",
                )
                return
            self._batch_package_options = [
                replace(
                    item,
                    draft_name=(
                        item.draft_name
                        if item.draft_name.endswith("_landscape_master")
                        else f"{item.draft_name}_landscape_master"
                    ),
                )
                for item in options
            ]
            self._batch_package_index = 0
            self._batch_package_phase = "landscape"
            self.log.appendPlainText(f"横版母片转竖版批量任务开始，共 {len(options)} 个主题")
            self._start_portrait_batch_item()
        else:
            self._clear_portrait_batch()
            self.batch_status_label.setText(f"0/{len(options)} 准备")
            self.runner.start_batch(options)
        self.refresh_status()

    def run_single_step(self, key: str, *, overwrite_images: bool = False) -> None:
        if self.runner.running:
            QMessageBox.information(self, "正在运行", "当前有任务在执行。")
            return
        if not self._persist_settings():
            return
        options = self._read_options()
        infinite_stage_keys = {
            "infinite_prepare": "prepare",
            "infinite_plan": "plan",
            "infinite_frames": "frames",
            "infinite_encode": "encode",
        }
        if key in infinite_stage_keys:
            if options.render_mode != "infinite_canvas":
                QMessageBox.information(self, "当前不是无限画布", "请先在“成片方式”中选择“无限画布成片（实验）”。")
                return
            options = replace(
                options,
                run_copy=False,
                run_voice=False,
                run_shots=False,
                run_storyboard_prompts=False,
                run_prompts=False,
                run_images=False,
                run_layout=False,
                run_draft=True,
                render_stage=infinite_stage_keys[key],
            )
        options = replace(
            options,
            run_copy=key == "copy", run_voice=key == "voice", run_shots=key == "shots",
            run_storyboard_prompts=key == "storyboard_prompts",
            run_prompts=key == "prompts", run_images=key == "images", run_layout=key == "layout",
            run_draft=key == "draft", overwrite_images=key == "images" and overwrite_images,
        )
        if key in infinite_stage_keys:
            options = replace(
                options,
                run_copy=False,
                run_voice=False,
                run_shots=False,
                run_storyboard_prompts=False,
                run_prompts=False,
                run_images=False,
                run_layout=False,
                run_draft=True,
                render_stage=infinite_stage_keys[key],
            )
        if key == "draft":
            package_mode = (
                self.workflow_mode is not None
                and self.workflow_mode.currentText() == WORKFLOW_PORTRAIT_PACKAGE
            )
            package_stage = package_mode and self.workflow_tabs is not None and self.workflow_tabs.currentIndex() == 1
            if package_mode and not package_stage:
                base_name = options.draft_name.strip() or safe_topic(options.topic)
                landscape_name = (
                    base_name
                    if base_name.endswith("_landscape_master")
                    else f"{base_name}_landscape_master"
                )
                options = replace(options, draft_name=landscape_name)
            self._automation_last_status = "未执行"
            self._remember_draft_target_for_options(options)
        # Running an individual step must remain isolated.  In particular,
        # regenerating the draft should not launch Jianying automatically;
        # step 09 has its own explicit button in the workflow list.
        self._auto_run_step09 = False
        self._chain_portrait_after_export = False
        self._focus_workflow_view()
        # The clicked workflow button is disabled when the runner starts. Move
        # focus to the log panel first so Qt does not scroll to the next
        # enabled button at the bottom of the production list.
        self.log.setFocus(Qt.OtherFocusReason)
        self.runner.start(options)
        self.refresh_status()

    def _poll(self) -> None:
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log.appendPlainText(text)
            elif kind == "batch_progress":
                self.batch_status_label.setText(text)
            elif kind == "status":
                if text == "完成" and self._auto_run_step09:
                    QTimer.singleShot(0, self._run_automation_when_idle)
                elif text in {"失败", "已停止", "部分失败"}:
                    self._auto_run_step09 = False
                    self._chain_portrait_after_export = False
                    if self._batch_package_options:
                        self.log.appendPlainText(f"批量串联已停止：{text}")
                        self._clear_portrait_batch()
        self.refresh_status()

    def _run_automation_when_idle(self) -> None:
        """Wait for the runner thread to exit before starting desktop automation."""
        if not self._auto_run_step09:
            return
        if self.runner.running:
            QTimer.singleShot(100, self._run_automation_when_idle)
            return
        self._auto_run_step09 = False
        self.run_automation_step()

    def output_dir(self) -> Path:
        if self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_COVER:
            return OUTPUT_ROOT / safe_topic(self.inputs["topic"].text()) / "cover"
        return OUTPUT_ROOT / safe_topic(self.inputs["topic"].text()) / orientation_key(
            self.setting_combos["VIDEO_ORIENTATION"].currentText()
        )

    def cover_artifact_path(self) -> Path:
        topic = self.inputs["topic"].text().strip()
        _key, _label, width, height, _ratio, _orientation = self._current_cover_size()
        return OUTPUT_ROOT / safe_topic(topic) / "cover" / f"{safe_topic(topic)}_cover_{width}x{height}.png"

    def _current_cover_size(self) -> tuple[str, str, int, int, str, str]:
        if self.cover_size_combo is None:
            return resolve_cover_size(DEFAULT_COVER_SIZE_KEY)
        value = self.cover_size_combo.currentData()
        try:
            return resolve_cover_size(str(value or ""))
        except ValueError:
            return resolve_cover_size(DEFAULT_COVER_SIZE_KEY)

    def _update_cover_prompt_preview(self, _value: str = "") -> None:
        if self.cover_prompt_preview is None:
            return
        topic = self.inputs["topic"].text().strip() if "topic" in self.inputs else ""
        context = self.context_input.toPlainText().strip() if self.context_input is not None else ""
        size = self._current_cover_size()
        if self.cover_canvas_label is not None:
            self.cover_canvas_label.setText(f"{size[2]} × {size[3]}（{size[4]} {size[5]}）")
        if self.cover_generate_button is not None:
            self.cover_generate_button.setToolTip(
                f"生成当前主题的 {size[2]}×{size[3]} {size[5]}作品封面；"
                "只生成 PNG，不执行视频制作流程"
            )
        if not topic:
            self.cover_prompt_preview.clear()
            if self.cover_output_label is not None:
                self.cover_output_label.clear()
            return
        try:
            self.cover_prompt_preview.setPlainText(build_cover_prompt(topic, context, size[0]))
        except ValueError:
            self.cover_prompt_preview.clear()
        if self.cover_output_label is not None:
            self.cover_output_label.setText(str(self.cover_artifact_path()))

    def show_cover_artifact(self) -> None:
        artifact = self.cover_artifact_path()
        if not artifact.is_file():
            QMessageBox.information(self, "未找到封面", f"没有找到封面文件：{artifact}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(artifact)))

    def open_cover_folder(self) -> None:
        folder = self.cover_artifact_path().parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开文件夹失败", f"无法创建封面目录：\n{folder}\n\n{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def artifact_path(self, key: str) -> Path:
        output = self.output_dir()
        draft_folder, draft_name = self._current_jianying_draft()
        render_mode = self.render_mode_combo.currentData() if self.render_mode_combo is not None else "jianying"
        experiment = PROJECT_ROOT / "experiments" / "remotion_infinite_canvas"
        return {
            "copy": output / "wenan.txt",
            "voice": output / "narration.wav",
            "shots": output / "shot_timeline_source_time.csv",
            "storyboard_prompts": output / "storyboard_prompts.csv",
            "prompts": output / "image_prompts_plus.csv",
            "images": output / "generated_assets_plus",
            "layout": output / "layout_result.json",
            "draft": (
                video_export_path(OUTPUT_ROOT, self.inputs["topic"].text(), "landscape")
                if key == "draft" and render_mode == "infinite_canvas"
                else draft_folder / draft_name
            ),
            "infinite_prepare": experiment / "out" / "source.json",
            "infinite_plan": experiment / "public" / "manifest.json",
            "infinite_frames": experiment / "out" / "frames",
            "infinite_encode": video_export_path(OUTPUT_ROOT, self.inputs["topic"].text(), "landscape"),
        }[key]

    def artifact_exists(self, key: str) -> bool:
        artifact = self.artifact_path(key)
        return artifact.is_dir() and any(artifact.iterdir()) if artifact.is_dir() else artifact.exists()

    def image_artifact_progress(self) -> tuple[int, int]:
        prompt_csv = self.output_dir() / "image_prompts_plus.csv"
        if not prompt_csv.is_file():
            return 0, 0
        try:
            items = load_image_review_items(prompt_csv, PROJECT_ROOT)
        except (OSError, ValueError):
            return 0, 0
        generated = 0
        for item in items:
            try:
                if item.asset_path.is_file() and item.asset_path.stat().st_size > 0:
                    generated += 1
            except OSError:
                continue
        return generated, len(items)

    def _on_workspace_topic_changed(self, _value: str = "") -> None:
        self._douyin_last_publish_succeeded = False
        self._automation_draft_target = None
        self._automation_export_target = None
        self._last_jianying_export_path = None
        if self.douyin_video_input is not None:
            self.douyin_video_input.clear()
        if self.douyin_cover_input is not None:
            self.douyin_cover_input.clear()
        if self.douyin_topics_input is not None:
            self.douyin_topics_input.clear()
        self._douyin_last_auto_video = ""
        self._douyin_last_auto_cover = ""
        self._pending_publish_after_metadata = False
        self._douyin_last_publish_prepared = False
        self._update_stage_statuses()

    def _update_stage_statuses(self) -> None:
        if not self.workflow_stage_status_labels or "topic" not in self.inputs:
            return
        topic = safe_topic(self.inputs["topic"].text())
        topic_root = OUTPUT_ROOT / topic
        video_exists = any(
            path.is_file()
            for path in (
                topic_root / "landscape" / "wenan.txt",
                topic_root / "portrait" / "wenan.txt",
            )
        )
        cover_exists = self.cover_artifact_path().is_file() if self.cover_size_combo is not None else False
        mode = self.workflow_mode.currentText() if self.workflow_mode is not None else WORKFLOW_LANDSCAPE
        douyin_running = self._douyin_publish_thread is not None and self._douyin_publish_thread.is_alive()

        video_status = "制作中" if self.runner.running and mode not in {WORKFLOW_COVER, WORKFLOW_PUBLISH} else (
            "已有产物" if video_exists else "未开始"
        )
        asset_status = "生成中" if self.runner.running and mode == WORKFLOW_COVER else (
            "封面已生成" if cover_exists else "未生成"
        )
        publish_status = "发布中" if douyin_running else (
            "已发布" if self._douyin_last_publish_succeeded else (
                "发布页已准备好" if self._douyin_last_publish_prepared else "待发布"
            )
        )
        self.workflow_stage_status_labels["视频制作"].setText(video_status)
        self.workflow_stage_status_labels["作品资产"].setText(asset_status)
        self.workflow_stage_status_labels["作品发布"].setText(publish_status)

    def refresh_status(self) -> None:
        running = self.runner.running
        jianying_running = self._jianying_automation_thread is not None and self._jianying_automation_thread.is_alive()
        jianying_supported = os.name == "nt" or sys.platform == "darwin"
        douyin_running = self._douyin_publish_thread is not None and self._douyin_publish_thread.is_alive()
        topic_generation_running = self._topic_generation_thread is not None and self._topic_generation_thread.is_alive()
        self._update_stage_statuses()
        self._update_workflow_action_visibility()
        self.start_button.setEnabled(not running)
        self.batch_button.setEnabled(not running)
        if self.continue_button is not None:
            self.continue_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.batch_topics.setEnabled(not running)
        self._set_topic_generation_enabled(not running and not topic_generation_running)
        cover_mode = self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_COVER
        publish_mode = self.workflow_mode is not None and self.workflow_mode.currentText() == WORKFLOW_PUBLISH
        if cover_mode:
            artifact = self.cover_artifact_path()
            exists = artifact.is_file()
            if self.cover_output_label is not None:
                self.cover_output_label.setText(str(artifact))
            if self.cover_status_label is not None:
                self.cover_status_label.setText("运行中" if running else ("完成" if exists else "未生成"))
            if self.cover_view_button is not None:
                self.cover_view_button.setEnabled(exists and not running)
            if self.cover_folder_button is not None:
                self.cover_folder_button.setEnabled(not running)
            if self.cover_generate_button is not None:
                self.cover_generate_button.setEnabled(not running)
            self.stop_button.setEnabled(running)
            return
        if publish_mode:
            self.start_button.setEnabled(not douyin_running)
            self.stop_button.setEnabled(False)
            self._set_douyin_publish_enabled(not douyin_running)
            return
        infinite_mode = self.render_mode_combo is not None and self.render_mode_combo.currentData() == "infinite_canvas"
        if infinite_mode:
            for key, _, _, action, _ in INFINITE_STAGE_DEFS:
                exists = self.artifact_exists(key)
                artifact = self.artifact_path(key)
                if artifact.is_dir():
                    try:
                        exists = exists and any(artifact.iterdir())
                    except OSError:
                        exists = False
                self.status_labels[key].setText("运行中" if running else ("完成" if exists else "未运行"))
                self.artifact_labels[key].setText("已生成" if exists else "未生成")
                self.run_buttons[key].setText(RERUN_ACTIONS[key] if exists else action)
                self.run_buttons[key].setEnabled(not running)
        draft_ready = self.artifact_exists("draft")
        self._set_jianying_automation_enabled(
            jianying_supported and not infinite_mode and draft_ready and not running and not jianying_running
        )
        if self.douyin_open_button is not None or self.douyin_publish_button is not None:
            self._set_douyin_publish_enabled(not douyin_running)
        for key, _, _, action, _ in UI_STEP_DEFS:
            if key == "automation":
                if infinite_mode:
                    status_text = "跳过"
                    artifact_text = "无限画布已直接生成 MP4"
                elif not jianying_supported:
                    status_text = "不可用"
                    artifact_text = "仅支持 Windows/macOS"
                elif not draft_ready:
                    status_text = "未就绪"
                    artifact_text = "请先生成草稿"
                elif jianying_running or self._automation_last_status == "运行中":
                    status_text = "运行中"
                    artifact_text = "草稿已生成"
                elif self._automation_last_status in {"完成", "失败"}:
                    status_text = self._automation_last_status
                    artifact_text = "草稿已生成"
                else:
                    status_text = "待执行"
                    artifact_text = "草稿已生成"
                self.status_labels[key].setText(status_text)
                self.artifact_labels[key].setText(artifact_text)
                self.run_buttons[key].setText(action)
                self.run_buttons[key].setEnabled(
                    jianying_supported and not infinite_mode and draft_ready and not running and not jianying_running
                )
                continue
            if key == "images":
                generated, total = self.image_artifact_progress()
                exists = generated > 0
                complete = total > 0 and generated == total
                missing = max(0, total - generated)
                status_text = "运行中" if running else (
                    "完成" if complete else (f"缺失 {missing}" if total else "未运行")
                )
                artifact_text = f"{generated}/{total} 张" if total else "未生成"
                can_view = total > 0
            else:
                exists = self.artifact_exists(key)
                status_text = "运行中" if running else ("完成" if exists else "未运行")
                artifact_text = "已生成" if exists else "未生成"
                if key == "voice" and exists:
                    artifact_text = self.voice_artifact_summary()
                can_view = exists
            self.status_labels[key].setText(status_text)
            self.artifact_labels[key].setText(artifact_text)
            button_action = RERUN_ACTIONS[key] if exists else action
            if key in self.run_button_labels:
                self.run_button_labels[key].setText(button_action)
            else:
                self.run_buttons[key].setText(button_action)
            self.run_buttons[key].setEnabled(not running)
            if key == "images" and self.image_missing_button is not None:
                self.image_missing_button.setEnabled(not running)
            if key in self.view_buttons:
                self.view_buttons[key].setEnabled(can_view and not running)

    def voice_artifact_summary(self) -> str:
        audio = self.artifact_path("voice")
        copy = self.artifact_path("copy")
        if not audio.exists():
            return "未生成"
        try:
            with wave.open(str(audio), "rb") as source:
                duration = source.getnframes() / max(source.getframerate(), 1)
        except (OSError, EOFError, wave.Error):
            return "已生成"
        try:
            char_count = count_speech_chars(copy.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError):
            return f"{duration:.1f} 秒"
        return f"{char_count} 字 / {duration:.1f} 秒"

    def show_artifact(self, key: str) -> None:
        artifact = self.artifact_path(key)
        if key == "images":
            self._review_images()
            return
        if not artifact.exists():
            QMessageBox.information(self, "未找到文件", f"没有找到对应产物：{artifact}")
            return
        if artifact.is_dir() or artifact.suffix.lower() not in {".txt", ".csv", ".md", ".json"}:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(artifact)))
            return
        if key == "copy":
            self._edit_copywriting(artifact)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(artifact.name)
        dialog.resize(960, 680)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(artifact.read_text(encoding="utf-8", errors="ignore"))
        editor.setReadOnly(True)
        layout.addWidget(editor)
        dialog.exec()

    def _edit_copywriting(self, artifact: Path) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("查看并修改文案")
        dialog.resize(960, 760)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(artifact.read_text(encoding="utf-8", errors="ignore"))
        layout.addWidget(editor, 1)

        feedback_label = QLabel("修改意见")
        feedback_label.setObjectName("sectionTitle")
        layout.addWidget(feedback_label)
        feedback = QPlainTextEdit()
        feedback.setPlaceholderText("例如：只调整开头，让问题更直接；保留后面的事实、结构和结论。")
        feedback.setFixedHeight(88)
        layout.addWidget(feedback)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = self._button("取消", QStyle.SP_DialogCancelButton, dialog.reject)
        revise = self._button(
            "按意见微调",
            QStyle.SP_BrowserReload,
            lambda: self._request_copy_revision(dialog, editor, feedback, revise, artifact),
        )
        save = self._button("保存", QStyle.SP_DialogSaveButton, lambda: self._save_copywriting(dialog, editor, artifact), "primary")
        actions.addWidget(cancel)
        actions.addWidget(revise)
        actions.addWidget(save)
        layout.addLayout(actions)
        self._copy_revision_editor = editor
        self._copy_revision_button = revise
        editor.setFocus()
        dialog.exec()
        self._copy_revision_editor = None
        self._copy_revision_button = None

    def _request_copy_revision(
        self,
        dialog: QDialog,
        editor: QPlainTextEdit,
        feedback: QPlainTextEdit,
        button: QPushButton,
        _artifact: Path,
    ) -> None:
        if self._copy_revision_thread is not None and self._copy_revision_thread.is_alive():
            return
        original = editor.toPlainText().strip()
        instruction = feedback.toPlainText().strip()
        topic = self.inputs["topic"].text().strip()
        api_key = self.api_inputs.get("DEEPSEEK_API_KEY")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if api_key is not None:
            api_key_value = api_key.text().strip()
        else:
            api_key_value = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not original:
            QMessageBox.information(dialog, "缺少文案", "当前文案为空，无法进行微调。")
            return
        if not instruction:
            QMessageBox.information(dialog, "缺少修改意见", "请先填写希望大模型调整的内容。")
            return
        button.setEnabled(False)
        button.setText("正在微调…")

        def worker() -> None:
            try:
                revised = revise_copywriting(
                    original=original,
                    feedback=instruction,
                    topic=topic,
                    api_key=api_key_value,
                    model=model,
                    base_url=base_url,
                )
                self.copy_revision_succeeded.emit(revised)
            except Exception as exc:
                self.copy_revision_failed.emit(str(exc))

        self._copy_revision_thread = threading.Thread(target=worker, daemon=True)
        self._copy_revision_thread.start()

    def _on_copy_revision_succeeded(self, revised: str) -> None:
        if self._copy_revision_editor is not None:
            self._copy_revision_editor.setPlainText(revised)
        if self._copy_revision_button is not None:
            self._copy_revision_button.setEnabled(True)
            self._copy_revision_button.setText("按意见微调")
        self.log.appendPlainText("文案已按修改意见生成新版本，请检查后点击“保存”。")

    def _on_copy_revision_failed(self, message: str) -> None:
        if self._copy_revision_button is not None:
            self._copy_revision_button.setEnabled(True)
            self._copy_revision_button.setText("按意见微调")
        QMessageBox.warning(self, "文案微调失败", message)

    def _save_copywriting(self, dialog: QDialog, editor: QPlainTextEdit, artifact: Path) -> None:
        try:
            save_copywriting_text(artifact, editor.toPlainText())
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog, "保存失败", str(exc))
            return
        QMessageBox.information(
            dialog,
            "保存成功",
            "文案已保存。请从配音步骤开始重新生成后续内容。",
        )
        dialog.accept()
        self.refresh_status()

    def _review_images(self) -> None:
        prompt_csv = self.output_dir() / "image_prompts_plus.csv"
        if not prompt_csv.exists():
            QMessageBox.information(self, "未找到文件", f"没有找到生图提示词：{prompt_csv}")
            return
        try:
            items = load_image_review_items(prompt_csv, PROJECT_ROOT)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "读取失败", str(exc))
            return
        if not items:
            QMessageBox.information(self, "没有图片", "当前项目没有可重新生成的图片。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("查看并修改图片")
        dialog.resize(1040, 760)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(0)
        selections: dict[str, QCheckBox] = {}
        for item in items:
            row = self._image_review_row(item, selections)
            content_layout.addWidget(row)
        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        actions = QHBoxLayout()
        select_all = self._button(
            "全选",
            QStyle.SP_DialogYesButton,
            lambda: [checkbox.setChecked(True) for checkbox in selections.values()],
        )
        clear = self._button(
            "清除选择",
            QStyle.SP_DialogResetButton,
            lambda: [checkbox.setChecked(False) for checkbox in selections.values()],
        )
        actions.addWidget(select_all)
        actions.addWidget(clear)
        actions.addStretch()
        actions.addWidget(self._button("关闭", QStyle.SP_DialogCloseButton, dialog.reject))
        actions.addWidget(self._button(
            "重试失败图片",
            QStyle.SP_BrowserReload,
            lambda: self._retry_failed_images(dialog, prompt_csv, items),
        ))
        actions.addWidget(self._button(
            "重新生成选中图片",
            QStyle.SP_BrowserReload,
            lambda: self._regenerate_selected_images(dialog, prompt_csv, selections),
            "primary",
        ))
        outer.addLayout(actions)
        dialog.exec()

    def _retry_failed_images(
        self,
        dialog: QDialog,
        prompt_csv: Path,
        items: list[ImageReviewItem],
    ) -> None:
        failed = [item.element_id for item in items if item.is_failed]
        if not failed:
            QMessageBox.information(dialog, "没有失败图片", "当前图片都已生成完成。")
            return
        if self.runner.running:
            QMessageBox.information(dialog, "正在运行", "当前有任务正在执行。")
            return
        if not self._persist_settings():
            return

        theme = resolve_visual_theme(self.setting_combos["VISUAL_THEME"].currentText())
        command = build_image_regeneration_command(
            prompt_csv,
            failed,
            image_model=self.image_model_setting.currentText(),
            image_quality=self.api_combos["IMAGE_QUALITY"].currentText(),
            visual_theme=theme.key,
            overwrite=False,
        )
        self.log.appendPlainText(f"重试失败图片：{len(failed)} 张（已生成图片会跳过）")
        self.runner.start_commands(
            [(f"06 图片（重试失败 {len(failed)} 张）", command)],
            self.output_dir(),
        )
        dialog.accept()
        self.refresh_status()

    def _image_review_row(
        self,
        item: ImageReviewItem,
        selections: dict[str, QCheckBox],
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("stepRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(14)
        checkbox = QCheckBox("选择")
        checkbox.setFixedWidth(64)
        selections[item.element_id] = checkbox
        layout.addWidget(checkbox)

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedSize(180, 180)
        preview.setStyleSheet("background: #0b0d10; border: 1px solid #303641;")
        if item.original_path.exists():
            pixmap = QPixmap(str(item.original_path))
            if not pixmap.isNull():
                preview.setPixmap(pixmap.scaled(
                    preview.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                ))
        else:
            preview.setText("原图尚未保留")
        layout.addWidget(preview)

        details = QVBoxLayout()
        name = QLabel(item.content or item.element_id)
        name.setObjectName("stepTitle")
        name.setWordWrap(True)
        identifier = QLabel(item.element_id)
        identifier.setObjectName("muted")
        details.addWidget(name)
        details.addWidget(identifier)
        state = QLabel("待重试" if item.is_failed else "已生成")
        state.setObjectName("muted")
        details.addWidget(state)
        details.addStretch()
        layout.addLayout(details, 1)
        return row

    def _regenerate_selected_images(
        self,
        dialog: QDialog,
        prompt_csv: Path,
        selections: dict[str, QCheckBox],
    ) -> None:
        selected = [element_id for element_id, checkbox in selections.items() if checkbox.isChecked()]
        if not selected:
            QMessageBox.information(dialog, "未选择图片", "请先选择需要重新生成的图片。")
            return
        if self.runner.running:
            QMessageBox.information(dialog, "正在运行", "当前有任务正在执行。")
            return
        if not self._persist_settings():
            return

        theme = resolve_visual_theme(self.setting_combos["VISUAL_THEME"].currentText())
        command = build_image_regeneration_command(
            prompt_csv,
            selected,
            image_model=self.image_model_setting.currentText(),
            image_quality=self.api_combos["IMAGE_QUALITY"].currentText(),
            visual_theme=theme.key,
        )
        self.log.appendPlainText(f"重新生成选中图片：{len(selected)} 张")
        self.runner.start_commands(
            [(f"05 图片（重生成 {len(selected)} 张）", command)],
            self.output_dir(),
        )
        dialog.accept()
        self.refresh_status()

    def closeEvent(self, event) -> None:
        self._remember_package_source_video()
        if self.runner.running:
            self.runner.stop()
        event.accept()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("动画口播智能体")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_SHEET)
    app.setFont(QFont("Segoe UI", 9))
    window = PipelineWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
