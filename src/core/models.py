"""Neutral layout models independent from the Jianying draft API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ElementType = Literal["text", "image"]


@dataclass(frozen=True)
class Canvas:
    width: int = 1080
    height: int = 1920
    safe_margin: int = 72
    top_reserved: int = 324
    bottom_reserved: int = 368

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Canvas":
        if not isinstance(value, dict):
            raise ValueError("layout canvas 必须是对象")
        return cls(
            width=int(value.get("width", 1080)),
            height=int(value.get("height", 1920)),
            safe_margin=int(value.get("safe_margin", 72)),
            top_reserved=int(value.get("top_reserved", 324)),
            bottom_reserved=int(value.get("bottom_reserved", 368)),
        )

    @property
    def content_left(self) -> int:
        return self.safe_margin

    @property
    def content_right(self) -> int:
        return self.width - self.safe_margin

    @property
    def content_top(self) -> int:
        return self.top_reserved + self.safe_margin

    @property
    def content_bottom(self) -> int:
        return self.height - self.bottom_reserved - self.safe_margin

def normalize_orientation(value: str = "") -> str:
    normalized = value.strip().lower()
    if normalized in {"landscape", "horizontal", "wide", "横屏", "1920x1080", "16:9"}:
        return "landscape"
    return "portrait"


def orientation_key(value: str = "") -> str:
    """Return the stable directory key for one video orientation."""
    return normalize_orientation(value)


def canvas_for_orientation(value: str = "") -> Canvas:
    orientation = normalize_orientation(value)
    if orientation == "landscape":
        return Canvas(width=1920, height=1080, safe_margin=64, top_reserved=190, bottom_reserved=60)
    return Canvas()


@dataclass(frozen=True)
class Theme:
    font_path: str | None = None
    title_font_size: int = 176
    subtitle_font_size: int = 56
    body_font_size: int = 68
    accent_color: str = "#FFD166"
    text_color: str = "#FFFFFF"
    muted_color: str = "#B7BEC9"
    panel_color: str = "#34423D"
    line_height: float = 1.22
    title_max_lines: int = 3
    subtitle_max_lines: int = 2
    subtitle_font: str = "未光体"
    subtitle_color: str = "#FFFFFF"
    subtitle_background_color: str = "#A84663"


@dataclass(frozen=True)
class SceneElement:
    element_id: str
    element_type: ElementType
    content: str
    start_ms: int
    end_ms: int
    source_content: str = ""
    role: str = ""


@dataclass(frozen=True)
class SceneFacts:
    scene_id: str
    scene_index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    title: str
    source_text: str
    elements: tuple[SceneElement, ...]
    semantic_role: str = "explain"

    @property
    def images(self) -> tuple[SceneElement, ...]:
        return tuple(element for element in self.elements if element.element_type == "image")

    @property
    def background_image(self) -> SceneElement | None:
        return next((element for element in self.images if element.role == "background"), None)

    @property
    def overlay_images(self) -> tuple[SceneElement, ...]:
        return tuple(element for element in self.images if element.role != "background")

    @property
    def labels(self) -> tuple[SceneElement, ...]:
        return tuple(element for element in self.elements if element.element_type == "text")


@dataclass(frozen=True)
class SceneContent:
    title: str = ""
    subtitle: str = ""
    images: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    elements: tuple[SceneElement, ...] = ()
    duration_ms: int = 4000
    semantic_role: str = "explain"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SceneContent":
        raw_elements = value.get("elements", ())
        elements = tuple(
            item if isinstance(item, SceneElement) else SceneElement(
                element_id=str(item.get("element_id", "")),
                element_type=str(item.get("element_type", "text")),
                content=str(item.get("content", "")),
                start_ms=int(item.get("start_ms", 0)),
                end_ms=int(item.get("end_ms", value.get("duration_ms", 4000))),
                source_content=str(item.get("source_content", "")),
                role=str(item.get("role", "")),
            )
            for item in raw_elements
        )
        return cls(
            title=str(value.get("title", "")),
            subtitle=str(value.get("subtitle", "")),
            images=tuple(str(item) for item in value.get("images", ())),
            labels=tuple(str(item) for item in value.get("labels", ())),
            elements=elements,
            duration_ms=int(value.get("duration_ms", 4000)),
            semantic_role=str(value.get("semantic_role", "explain")),
        )

    @classmethod
    def from_facts(cls, facts: SceneFacts) -> "SceneContent":
        return cls(
            title=facts.title,
            images=tuple(element.content for element in facts.images),
            labels=tuple(element.content for element in facts.labels),
            elements=facts.elements,
            duration_ms=facts.duration_ms,
            semantic_role=facts.semantic_role,
        )

    @property
    def image_elements(self) -> tuple[SceneElement, ...]:
        if self.elements:
            return tuple(element for element in self.elements if element.element_type == "image")
        return tuple(
            SceneElement(f"image_{index}", "image", path, 0, self.duration_ms, path, "")
            for index, path in enumerate(self.images)
        )

    @property
    def background_element(self) -> SceneElement | None:
        return next((element for element in self.image_elements if element.role == "background"), None)

    @property
    def overlay_image_elements(self) -> tuple[SceneElement, ...]:
        return tuple(element for element in self.image_elements if element.role != "background")

    @property
    def text_elements(self) -> tuple[SceneElement, ...]:
        if self.elements:
            return tuple(element for element in self.elements if element.element_type == "text")
        return tuple(
            SceneElement(f"label_{index}", "text", text, 0, self.duration_ms, text)
            for index, text in enumerate(self.labels)
        )


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Box":
        if not isinstance(value, dict):
            raise ValueError("layout box 必须是对象")
        box = cls(
            x=int(value["x"]),
            y=int(value["y"]),
            width=int(value["width"]),
            height=int(value["height"]),
        )
        if box.width <= 0 or box.height <= 0:
            raise ValueError(f"layout box 尺寸无效：{box.width}x{box.height}")
        return box

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def inset(self, amount: int) -> "Box":
        return Box(self.x + amount, self.y + amount, self.width - amount * 2, self.height - amount * 2)


@dataclass(frozen=True)
class TextMeasure:
    text: str
    lines: tuple[str, ...]
    width: int
    height: int
    font_size: int


@dataclass(frozen=True)
class AnimationSpec:
    enter: str = "fade_scale"
    exit: str = "fade_out"
    enter_after_ms: int = 0
    enter_duration_ms: int = 360
    exit_duration_ms: int = 240

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "AnimationSpec":
        data = value or {}
        if not isinstance(data, dict):
            raise ValueError("layout animation 必须是对象")
        return cls(
            enter=str(data.get("enter", "fade_scale")),
            exit=str(data.get("exit", "fade_out")),
            enter_after_ms=int(data.get("enter_after_ms", 0)),
            enter_duration_ms=int(data.get("enter_duration_ms", 360)),
            exit_duration_ms=int(data.get("exit_duration_ms", 240)),
        )


@dataclass(frozen=True)
class ElementLayout:
    element_id: str
    element_type: ElementType
    content: str
    box: Box
    start_ms: int
    end_ms: int
    z_index: int
    role: str
    font_size: int | None = None
    lines: tuple[str, ...] = ()
    animation: AnimationSpec = field(default_factory=AnimationSpec)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ElementLayout":
        if not isinstance(value, dict):
            raise ValueError("layout element 必须是对象")
        element_type = str(value.get("element_type", ""))
        if element_type not in {"text", "image"}:
            raise ValueError(f"layout element_type 不支持：{element_type}")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("layout element metadata 必须是对象")
        font_size = value.get("font_size")
        return cls(
            element_id=str(value.get("element_id", "")),
            element_type=element_type,
            content=str(value.get("content", "")),
            box=Box.from_dict(value.get("box", {})),
            start_ms=int(value.get("start_ms", 0)),
            end_ms=int(value.get("end_ms", 0)),
            z_index=int(value.get("z_index", 0)),
            role=str(value.get("role", "")),
            font_size=None if font_size is None else int(font_size),
            lines=tuple(str(line) for line in value.get("lines", ())),
            animation=AnimationSpec.from_dict(value.get("animation")),
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayoutResult:
    template: str
    canvas: Canvas
    elements: list[ElementLayout]
    warnings: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LayoutResult":
        if not isinstance(value, dict):
            raise ValueError("layout_result.json 顶层必须是对象")
        raw_elements = value.get("elements", [])
        if not isinstance(raw_elements, list):
            raise ValueError("layout_result.json elements 必须是数组")
        result = cls(
            template=str(value.get("template", "")),
            canvas=Canvas.from_dict(value.get("canvas", {})),
            elements=[ElementLayout.from_dict(item) for item in raw_elements],
            warnings=[str(item) for item in value.get("warnings", [])],
            decisions=[str(item) for item in value.get("decisions", [])],
        )
        if not result.template:
            raise ValueError("layout_result.json 缺少 template")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "canvas": asdict(self.canvas),
            "elements": [element.to_dict() for element in self.elements],
            "warnings": self.warnings,
            "decisions": self.decisions,
        }
