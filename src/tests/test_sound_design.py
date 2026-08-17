from __future__ import annotations

import unittest

from ..core.models import Box, Canvas, ElementLayout, LayoutResult
from ..visual_direction.sound_design import apply_sound_design, sound_cue_for


class SoundDesignTest(unittest.TestCase):
    def test_nearby_animations_keep_one_high_priority_sound(self):
        image = candidate("image", "image", 0, role="main", cue="swish", priority=30)
        number = candidate("number", "text", 100, role="number", cue="pop", priority=50)
        result = apply_sound_design(LayoutResult("test", Canvas(), [image, number]))

        selected = [element for element in result.elements if element.metadata.get("sound_effect")]
        self.assertEqual([element.element_id for element in selected], ["number"])
        self.assertEqual(selected[0].start_ms, 100)

    def test_dense_animation_sequence_is_throttled(self):
        elements = [
            candidate(f"image_{index}", "image", start_ms, role="main", cue="pop", priority=30)
            for index, start_ms in enumerate((0, 1000, 2000, 3000))
        ]
        result = apply_sound_design(LayoutResult("test", Canvas(), elements))

        selected = [element.start_ms for element in result.elements if element.metadata.get("sound_effect")]
        self.assertEqual(selected, [0, 1000])

    def test_subtitles_never_receive_sound_cues(self):
        subtitle = ElementLayout(
            "subtitle",
            "text",
            "口播字幕",
            Box(72, 1500, 936, 120),
            0,
            1000,
            1000,
            "subtitle",
            56,
        )
        self.assertEqual(sound_cue_for(subtitle, {"text_intro": "渐显"}), "")


def candidate(
    element_id: str,
    element_type: str,
    start_ms: int,
    *,
    role: str,
    cue: str,
    priority: int,
) -> ElementLayout:
    return ElementLayout(
        element_id,
        element_type,
        "关键词" if element_type == "text" else "asset.png",
        Box(72, 400, 400, 300),
        start_ms,
        start_ms + 1600,
        30,
        role,
        82 if element_type == "text" else None,
        metadata={"sound_cue": cue, "sound_priority": priority},
    )


if __name__ == "__main__":
    unittest.main()
