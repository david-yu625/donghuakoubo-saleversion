"""Generate text-free MG graphic assets that should not depend on image models."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


INK = "#1B1B1F"
PAPER = "#A5D8FF"
PAPER_LIGHT = "#E7F5FF"
ACCENT = "#FF6B6B"
MUTED = "#868E96"


def native_graphic_kind(content: str) -> str | None:
    value = content.strip()
    if value == "下降箭头符号":
        return "down_arrow"
    if value == "上涨箭头警示符号":
        return "up_arrow"
    if "下降的价格曲线" in value:
        return "down_chart"
    if "上涨的价格曲线" in value:
        return "up_chart"
    if "价格标签牌" in value or "利润标签" in value:
        return "blank_tag"
    if "日期牌" in value:
        return "calendar"
    if "价差箭头" in value:
        return "spread_arrow"
    return None


def generate_native_graphic(content: str, output_path: Path, width: int, height: int) -> bool:
    kind = native_graphic_kind(content)
    if kind is None:
        return False
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    getattr(_Drawings(draw, width, height), kind)()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return True


class _Drawings:
    def __init__(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        self.draw = draw
        self.width = width
        self.height = height
        self.scale = min(width / 1024, height / 1536)

    def point(self, x: int, y: int) -> tuple[int, int]:
        return round(x * self.width / 1024), round(y * self.height / 1536)

    def stroke(self, value: int) -> int:
        return max(2, round(value * self.scale))

    def blank_tag(self) -> None:
        box = (*self.point(190, 350), *self.point(834, 1186))
        radius = self.stroke(56)
        self.draw.rounded_rectangle(box, radius=radius, fill=PAPER_LIGHT, outline=INK, width=self.stroke(24))
        hole_center = self.point(512, 430)
        hole_radius = self.stroke(42)
        self.draw.ellipse(
            (hole_center[0] - hole_radius, hole_center[1] - hole_radius, hole_center[0] + hole_radius, hole_center[1] + hole_radius),
            fill=(0, 0, 0, 0), outline=INK, width=self.stroke(18),
        )
        self.draw.line((*self.point(290, 1020), *self.point(734, 1020)), fill=MUTED, width=self.stroke(12))

    def calendar(self) -> None:
        box = (*self.point(160, 330), *self.point(864, 1170))
        self.draw.rounded_rectangle(box, radius=self.stroke(48), fill=PAPER_LIGHT, outline=INK, width=self.stroke(24))
        self.draw.rounded_rectangle(
            (*self.point(160, 330), *self.point(864, 560)),
            radius=self.stroke(48), fill=ACCENT, outline=INK, width=self.stroke(24),
        )
        for x in (330, 694):
            self.draw.rounded_rectangle(
                (*self.point(x - 34, 260), *self.point(x + 34, 430)),
                radius=self.stroke(22), fill=PAPER, outline=INK, width=self.stroke(16),
            )
        for x in (390, 620):
            self.draw.line((*self.point(x, 650), *self.point(x, 1050)), fill=MUTED, width=self.stroke(10))
        for y in (780, 920):
            self.draw.line((*self.point(260, y), *self.point(764, y)), fill=MUTED, width=self.stroke(10))

    def down_arrow(self) -> None:
        self._arrow("down")

    def up_arrow(self) -> None:
        self._arrow("up")

    def _arrow(self, direction: str) -> None:
        points = [(430, 360), (594, 360), (594, 850), (760, 850), (512, 1176), (264, 850), (430, 850)]
        if direction == "up":
            points = [(x, 1536 - y) for x, y in points]
        scaled = [self.point(x, y) for x, y in points]
        self.draw.polygon(scaled, fill=PAPER, outline=INK)
        self.draw.line(scaled + [scaled[0]], fill=INK, width=self.stroke(28), joint="curve")
        accent_start = self.point(430, 500 if direction == "down" else 1036)
        accent_end = self.point(594, 500 if direction == "down" else 1036)
        self.draw.line((*accent_start, *accent_end), fill=ACCENT, width=self.stroke(20))

    def down_chart(self) -> None:
        self._chart("down")

    def up_chart(self) -> None:
        self._chart("up")

    def _chart(self, direction: str) -> None:
        origin = self.point(220, 1110)
        self.draw.line((*origin, *self.point(220, 390)), fill=INK, width=self.stroke(22))
        self.draw.line((*origin, *self.point(830, 1110)), fill=INK, width=self.stroke(22))
        points = [(270, 520), (400, 650), (520, 610), (650, 820), (790, 990)]
        if direction == "up":
            points = [(x, 1500 - y) for x, y in points]
        scaled = [self.point(x, y) for x, y in points]
        self.draw.line(scaled, fill=ACCENT, width=self.stroke(34), joint="curve")
        end_x, end_y = scaled[-1]
        previous_x, previous_y = scaled[-2]
        sign_x = 1 if end_x >= previous_x else -1
        sign_y = 1 if end_y >= previous_y else -1
        head = [(end_x, end_y), (end_x - sign_x * self.stroke(100), end_y), (end_x, end_y - sign_y * self.stroke(100))]
        self.draw.polygon(head, fill=ACCENT)
        for x, y in scaled[:-1]:
            radius = self.stroke(16)
            self.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=PAPER_LIGHT, outline=INK, width=self.stroke(8))

    def spread_arrow(self) -> None:
        center_x = self.width // 2
        self.draw.line((*self.point(512, 380), *self.point(512, 1150)), fill=INK, width=self.stroke(30))
        top = self.point(512, 300)
        bottom = self.point(512, 1230)
        self.draw.polygon([top, self.point(405, 470), self.point(619, 470)], fill=ACCENT, outline=INK)
        self.draw.polygon([bottom, self.point(405, 1060), self.point(619, 1060)], fill=PAPER, outline=INK)
        for y in (520, 990):
            box = (*self.point(610, y - 90), *self.point(860, y + 90))
            self.draw.rounded_rectangle(box, radius=self.stroke(28), fill=PAPER_LIGHT, outline=INK, width=self.stroke(16))
        self.draw.ellipse(
            (center_x - self.stroke(38), self.point(0, 765)[1] - self.stroke(38), center_x + self.stroke(38), self.point(0, 765)[1] + self.stroke(38)),
            fill=ACCENT, outline=INK, width=self.stroke(10),
        )
