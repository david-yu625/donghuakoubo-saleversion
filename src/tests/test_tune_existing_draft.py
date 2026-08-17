from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ..commands.tune_existing_draft import (
    enlarge_layout_images,
    fit_title_bar_to_text,
    replace_green_keyword_colors,
)
from ..commands.remove_text_effect_from_draft import remove_text_animation
from ..commands.fix_existing_draft_title import fix_title_presentation
from ..commands.replace_existing_draft_bgm import attach_background_music
from ..commands.replace_existing_draft_fonts import replace_selected_fonts
from ..renderers.jianying_renderer import draft


class TuneExistingDraftTest(unittest.TestCase):
    def test_only_green_layout_keywords_are_recolored(self):
        content = draft_fixture()
        changes = replace_green_keyword_colors(content)
        text_materials = content["materials"]["texts"]
        green_style = json.loads(text_materials[0]["content"])["styles"][0]
        title_style = json.loads(text_materials[1]["content"])["styles"][0]

        self.assertEqual(len(changes), 1)
        self.assertEqual(green_style["fill"]["content"]["solid"]["color"], [95 / 255, 61 / 255, 196 / 255])
        self.assertEqual(title_style["fill"]["content"]["solid"]["color"], [0.0, 0.0, 0.0])

    def test_only_layout_video_scales_and_scale_keyframes_are_enlarged(self):
        content = draft_fixture()
        count = enlarge_layout_images(content, 1.12)
        image = content["tracks"][2]["segments"][0]
        background = content["tracks"][3]["segments"][0]

        self.assertEqual(count, 1)
        self.assertAlmostEqual(image["clip"]["scale"]["x"], 0.56)
        self.assertAlmostEqual(image["common_keyframes"][0]["keyframe_list"][0]["values"][0], 0.56)
        self.assertEqual(background["clip"]["scale"]["x"], 1.0)

    def test_title_bar_width_is_derived_from_title(self):
        content = draft_fixture()
        title, scale = fit_title_bar_to_text(content)
        bar = content["tracks"][1]["segments"][0]

        self.assertEqual(title, "什么云计算")
        self.assertLess(scale, 1.0)
        self.assertEqual(bar["clip"]["scale"]["x"], scale)

    def test_specific_text_effect_is_removed_without_touching_other_animations(self):
        content = draft_fixture()
        content["materials"]["material_animations"] = [{
            "id": "animation",
            "animations": [
                {"name": "波浪弹入", "resource_id": "intro"},
                {"name": "描边粉笔", "resource_id": "chalk"},
                {"name": "波浪弹出", "resource_id": "outro"},
            ],
        }]
        content["tracks"][4]["segments"][0]["extra_material_refs"] = ["animation"]

        texts = remove_text_animation(content, "chalk")
        remaining = content["materials"]["material_animations"][0]["animations"]

        self.assertEqual(texts, ["云计算"])
        self.assertEqual([animation["resource_id"] for animation in remaining], ["intro", "outro"])

    def test_existing_title_uses_larger_text_and_embedded_adaptive_bar(self):
        content = draft_fixture()
        with tempfile.TemporaryDirectory() as directory:
            asset_path = Path(directory) / "Resources" / "title_bar.png"
            title, previous_size, bar_width = fix_title_presentation(content, asset_path)

            self.assertTrue(asset_path.exists())
            with Image.open(asset_path) as image:
                self.assertEqual(image.size, (1080, 180))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getpixel((540, 76)), (255, 222, 0, 255))

        title_material = json.loads(content["materials"]["texts"][1]["content"])
        bar_segment = content["tracks"][1]["segments"][0]
        self.assertEqual(title, "什么云计算")
        self.assertEqual(previous_size, 14.0)
        self.assertGreater(bar_width, 0)
        self.assertEqual(title_material["styles"][0]["size"], 17.0)
        self.assertEqual(bar_segment["clip"]["scale"], {"x": 1.0, "y": 1.0})

    def test_existing_draft_can_receive_background_music_from_template_track(self):
        content = draft_fixture()
        template = draft_fixture()
        template["materials"]["audios"] = [{"id": "audio", "path": "old.mp4", "media_path": "old.mp4", "duration": 10}]
        template["tracks"].insert(0, {
            "name": "background_music",
            "type": "audio",
            "segments": [{"material_id": "audio", "target_timerange": {"start": 0, "duration": 10}}],
        })

        attached = attach_background_music(content, Path("audio/bgm/bgm1.mp4"), template_content=template)
        music_track = next(track for track in content["tracks"] if track["name"] == "background_music")
        music_material = next(material for material in content["materials"]["audios"] if material["id"] == "audio")

        self.assertTrue(attached)
        self.assertEqual(music_material["path"], str(Path("audio/bgm/bgm1.mp4").resolve()))
        self.assertEqual(music_material["material_name"], "bgm1.mp4")
        self.assertEqual(len(music_track["segments"]), 1)

    def test_all_banned_fonts_and_global_title_are_replaced(self):
        content = draft_fixture()
        content["tracks"].append({
            "name": "layout_public_service",
            "type": "text",
            "segments": [{"material_id": "public_service"}],
        })
        content["materials"]["texts"].append(
            _text_material("public_service", "公共\n服务", [0.0, 0.0, 0.0])
        )
        content["materials"]["texts"][-1]["content"] = _with_font(
            content["materials"]["texts"][-1]["content"],
            "7265609486646121018",
        )
        content["tracks"].append({
            "name": "layout_everyone",
            "type": "text",
            "segments": [{"material_id": "everyone"}],
        })
        everyone = _text_material("everyone", "人人\n可用", [0.0, 0.0, 0.0])
        everyone["content"] = _with_font(everyone["content"], "7265609486646121018")
        content["materials"]["texts"].append(everyone)
        content["tracks"].append({
            "name": "layout_dotted_keyword",
            "type": "text",
            "segments": [{"material_id": "dotted_keyword"}],
        })
        dotted_keyword = _text_material("dotted_keyword", "重点关键词", [0.0, 0.0, 0.0])
        dotted_keyword["content"] = _with_font(
            dotted_keyword["content"],
            draft.FontType.古印宋简.value.resource_id,
        )
        content["materials"]["texts"].append(dotted_keyword)

        with patch(
            "src.commands.replace_existing_draft_fonts.font_style",
            side_effect=lambda font_type: {
                "id": font_type.value.resource_id,
                "path": "cached-font.ttf",
            },
        ):
            changed = replace_selected_fonts(content)
        materials = {item["id"]: json.loads(item["content"]) for item in content["materials"]["texts"]}

        self.assertEqual(len(changed), 4)
        self.assertEqual(materials["title"]["styles"][0]["font"]["id"], "7130640934366089758")
        self.assertEqual(materials["public_service"]["styles"][0]["font"]["id"], "7265596408491676197")
        self.assertEqual(materials["everyone"]["styles"][0]["font"]["id"], "7265596408491676197")
        self.assertEqual(materials["dotted_keyword"]["styles"][0]["font"]["id"], "7265596408491676197")


def _text_material(material_id, text, color):
    return {
        "id": material_id,
        "content": json.dumps({
            "text": text,
            "styles": [{
                "fill": {"content": {"solid": {"color": color}}},
                "strokes": [],
                "size": 14.0 if text == "什么云计算" else 10.0,
            }],
        }),
    }


def _with_font(content: str, font_id: str) -> str:
    value = json.loads(content)
    value["styles"][0]["font"] = {"id": font_id, "path": "old.ttf"}
    return json.dumps(value)


def draft_fixture():
    return {
        "canvas_config": {"width": 1080},
        "materials": {
            "texts": [
                _text_material("green", "云计算", [184 / 255, 242 / 255, 61 / 255]),
                _text_material("title", "什么云计算", [0.0, 0.0, 0.0]),
            ],
            "videos": [{"id": "bar", "path": "missing.png", "media_path": "missing.png", "width": 1080, "height": 132}],
        },
        "tracks": [
            {"name": "global_title", "type": "text", "segments": [{"material_id": "title"}]},
            {"name": "global_title_bar", "type": "video", "segments": [{"material_id": "bar", "clip": {"scale": {"x": 0.4, "y": 1.0}}}]},
            {
                "name": "layout_01_scene_img01",
                "type": "video",
                "segments": [{
                    "clip": {"scale": {"x": 0.5, "y": 0.5}},
                    "common_keyframes": [{
                        "property_type": "KFTypeScaleX",
                        "keyframe_list": [{"values": [0.5]}],
                    }],
                }],
            },
            {"name": "background", "type": "video", "segments": [{"clip": {"scale": {"x": 1.0, "y": 1.0}}}]},
            {"name": "layout_02_scene_txt01", "type": "text", "segments": [{"material_id": "green"}]},
        ],
    }


if __name__ == "__main__":
    unittest.main()
