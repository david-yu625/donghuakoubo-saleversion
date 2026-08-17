"""Curated typography and motion languages for knowledge explainers."""

from __future__ import annotations

from .models import MotionPlan, TypographyPlan


TYPOGRAPHY_PRESETS = (
    TypographyPlan(
        title_font="ResourceHanRoundedCN_Bold",
        label_font="ResourceHanRoundedCN_Md",
        number_font="ResourceHanRoundedCN_Md",
        subtitle_font="ResourceHanRoundedCN_Nl",
        preset="knowledge_rounded",
        title_color="#FFD166",
        label_color="#1864AB",
        number_color="#FF6B6B",
    ),
    TypographyPlan(
        title_font="Aa动员宋",
        label_font="ResourceHanRoundedCN_Md",
        number_font="庞门正道标题体",
        subtitle_font="今宋体",
        preset="editorial_finance",
        title_color="#FF6B6B",
        label_color="#C92A2A",
        number_color="#60A5FA",
    ),
    TypographyPlan(
        title_font="Aa水玉圆体",
        label_font="优设标题圆",
        number_font="综艺体",
        subtitle_font="芋圆体",
        preset="colorful_pop",
        title_color="#FF7EB6",
        label_color="#5F3DC4",
        number_color="#FFE45E",
    ),
    TypographyPlan(
        title_font="文轩体",
        label_font="方糖体",
        number_font="得意黑",
        subtitle_font="仓耳舒圆体W02",
        preset="story_sticker",
        title_color="#FF9F1C",
        label_color="#D9480F",
        number_color="#FF5D8F",
    ),
    TypographyPlan(
        title_font="得意黑",
        label_font="综艺字",
        number_font="特黑体",
        subtitle_font="仓耳舒圆体W02",
        preset="bold_variety",
        title_color="#C77DFF",
        label_color="#0B7285",
        number_color="#F9C74F",
    ),
)

MOTION_PRESETS = (
    MotionPlan("渐显", "溶解", "轻微放大", "渐隐", "渐显", "渐隐", "soft"),
    MotionPlan("向上露出", "羽化向右擦开", "向右滑动", "向左滑动", "渐显", "向上溶解", "flow"),
    MotionPlan("逐字显影", "复古打字机", "向右滑动", "渐隐", "渐显", "溶解", "story"),
    MotionPlan("轻微放大", "渐显", "渐显", "轻微放大", "渐显", "渐隐", "soft"),
    MotionPlan("弹性伸缩", "右上弹入", "轻微放大", "渐隐", "渐显", "轻微放大", "focus"),
    MotionPlan("向右露出", "向左露出", "向右滑动", "渐隐", "渐显", "向右滑动", "flow"),
    MotionPlan("居中打字", "波浪弹入", "放大", "缩小", "渐显", "波浪弹出", "story"),
    MotionPlan("溶解", "轻微放大", "放大", "缩小", "渐显", "渐隐", "soft"),
)

BOARD_MOTION_PRESET = MotionPlan(
    "渐显", "渐显", "轻微放大", "渐隐", "渐显", "渐隐", "board", "drift",
)

EFFECT_PROFILES = {
    "board": {
        "title_intros": ("渐显", "轻微放大"),
        "label_intros": ("渐显", "轻微放大"),
        "text_outros": ("渐隐",),
        "video_intros": (
            "渐显", "轻微放大", "放大", "向上滑动", "向左滑动", "向右滑动",
            "弹近", "点开", "模糊聚焦", "展开",
        ),
        "video_outros": (
            "渐隐", "缩小", "轻微放大", "向上滑动", "向左滑动", "向右滑动",
            "弹远", "模糊聚焦",
        ),
    },
    "soft": {
        "title_intros": ("渐显", "溶解", "轻微放大"),
        "label_intros": ("渐显", "溶解", "轻微放大"),
        "text_outros": ("渐隐", "溶解", "轻微放大"),
        "video_intros": ("渐显", "轻微放大", "放大"),
        "video_outros": ("渐隐", "轻微放大", "缩小"),
    },
    "flow": {
        "title_intros": ("向上露出", "向左露出", "向右露出"),
        "label_intros": ("羽化向右擦开", "羽化向左擦开", "向上露出", "向右露出"),
        "text_outros": ("向上溶解", "向左滑动", "向右滑动", "羽化向左擦除"),
        "video_intros": ("渐显", "轻微放大", "向上滑动", "向左滑动", "向右滑动"),
        "video_outros": ("向上滑动", "向左滑动", "向右滑动", "渐隐"),
    },
    "story": {
        "title_intros": ("逐字显影", "居中打字", "复古打字机"),
        "label_intros": ("复古打字机", "波浪弹入", "居中打字"),
        "text_outros": ("渐隐", "溶解", "波浪弹出", "打字机_II"),
        "video_intros": ("渐显", "轻微放大", "放大", "向上滑动", "向右滑动"),
        "video_outros": ("渐隐", "缩小", "轻微放大", "向左滑动", "向右滑动"),
    },
    "focus": {
        "title_intros": ("弹性伸缩", "弹入", "放大"),
        "label_intros": ("右上弹入", "弹性伸缩", "弹簧"),
        "text_outros": ("弹性伸缩", "弹出", "轻微放大", "缩小"),
        "video_intros": ("动感放大", "轻微放大", "放大", "渐显", "向上滑动"),
        "video_outros": ("缩小", "轻微放大", "渐隐", "向左滑动", "向右滑动"),
    },
}


def merge_profile_values(key: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for profile in EFFECT_PROFILES.values() for value in profile[key]))


TITLE_TEXT_INTROS = merge_profile_values("title_intros")
LABEL_TEXT_INTROS = merge_profile_values("label_intros")
TEXT_OUTROS = merge_profile_values("text_outros")
EMPHASIS_TEXT_LOOPS = ("漂浮",)
SCENE_TRANSITION_INTROS: tuple[str, ...] = ("渐显", "轻微放大", "模糊聚焦", "放大")
VIDEO_INTROS = merge_profile_values("video_intros")
VIDEO_OUTROS = merge_profile_values("video_outros")
# Persistent scene effects alter the image itself and easily overwhelm whiteboard visuals.
# Variety belongs in intro/outro motion; overlays receive no mandatory scene effect.
VIDEO_EFFECTS: tuple[str, ...] = ()
