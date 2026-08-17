"""Coordinate-free contracts for visual direction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutChoice:
    family: str
    variant: str
    template: str


@dataclass(frozen=True)
class TypographyPlan:
    title_font: str
    label_font: str
    number_font: str
    subtitle_font: str
    preset: str
    title_color: str = "#FFD166"
    label_color: str = "#FFFFFF"
    number_color: str = "#FFD166"
    subtitle_color: str = "#FFFFFF"


@dataclass(frozen=True)
class MotionPlan:
    title_enter: str
    label_enter: str
    image_enter: str
    image_exit: str
    subtitle_enter: str
    text_exit: str
    intensity: str
    hold_motion: str = "drift"


@dataclass(frozen=True)
class VisualPlan:
    scene_id: str
    layout: LayoutChoice
    typography: TypographyPlan
    motion: MotionPlan
    enter_order: tuple[str, ...]
