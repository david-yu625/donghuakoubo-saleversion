from __future__ import annotations

import unittest
import queue
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ..pipeline_runtime import (
    Options,
    Runner,
    STEP_DEFS,
    STEP_BUTTON_DESCRIPTIONS,
    build_batch_options,
    build_commands,
    build_image_regeneration_command,
    build_portrait_package_command,
    parse_batch_topics,
    reuse_completed_materials,
    save_copywriting_text,
    update_env_file,
)
from ..paths import default_draft_folder


class GuiPipelineTest(unittest.TestCase):
    def _complete_material_project(self, root: Path, topic: str = "复用主题") -> tuple[Options, dict[str, Path]]:
        project = root / topic / "landscape"
        project.mkdir(parents=True)
        paths = {
            "wenan": project / "wenan.txt",
            "narration": project / "narration.wav",
            "timeline": project / "timeline.csv",
            "shots": project / "shot_timeline_source_time.csv",
            "storyboard": project / "storyboard_prompts.csv",
            "prompts": project / "image_prompts_plus.csv",
            "elements": project / "element_timeline_with_assets.csv",
            "asset": project / "generated_assets_plus" / "s1_bg01.png",
        }
        paths["asset"].parent.mkdir()
        ordered = ("wenan", "narration", "timeline", "shots", "storyboard", "prompts", "elements", "asset")
        base_ns = 1_800_000_000_000_000_000
        for index, key in enumerate(ordered):
            path = paths[key]
            if key == "prompts":
                content = f"element_id,shot_id,role,content,width,height,asset_path,prompt\ns1_bg01,1,background,x,1920,1080,{path.parent / 'generated_assets_plus' / 's1_bg01.png'},x\n"
                path.write_text(content, encoding="utf-8")
            elif path.suffix == ".png" or path.suffix == ".wav":
                path.write_bytes(b"asset")
            else:
                path.write_text("content\n", encoding="utf-8")
            stamp = base_ns + index * 1_000_000
            os.utime(path, ns=(stamp, stamp))
        return Options(topic=topic, story_world="", target_chars="250", orientation="横屏"), paths

    def test_complete_materials_reuse_only_layout_and_draft(self):
        with TemporaryDirectory() as directory:
            options, _ = self._complete_material_project(Path(directory))
            planned = reuse_completed_materials(options, output_root=Path(directory))

        self.assertFalse(planned.run_copy)
        self.assertFalse(planned.run_voice)
        self.assertFalse(planned.run_shots)
        self.assertFalse(planned.run_storyboard_prompts)
        self.assertFalse(planned.run_prompts)
        self.assertFalse(planned.run_images)
        self.assertTrue(planned.run_layout)
        self.assertTrue(planned.run_draft)

    def test_missing_image_resumes_at_image_generation_without_overwrite(self):
        with TemporaryDirectory() as directory:
            options, paths = self._complete_material_project(Path(directory))
            paths["asset"].unlink()
            planned = reuse_completed_materials(options, output_root=Path(directory))

        self.assertFalse(planned.run_prompts)
        self.assertTrue(planned.run_images)
        self.assertFalse(planned.overwrite_images)

    def test_edited_copy_rebuilds_downstream_and_overwrites_images(self):
        with TemporaryDirectory() as directory:
            options, paths = self._complete_material_project(Path(directory))
            stamp = paths["asset"].stat().st_mtime_ns + 1_000_000
            os.utime(paths["wenan"], ns=(stamp, stamp))
            planned = reuse_completed_materials(options, output_root=Path(directory))

        self.assertFalse(planned.run_copy)
        self.assertTrue(planned.run_voice)
        self.assertTrue(planned.run_images)
        self.assertTrue(planned.overwrite_images)

    def test_batch_topics_ignore_blank_lines_and_duplicates(self):
        self.assertEqual(
            parse_batch_topics("主题一\n\n 主题二 \r\n主题一\n"),
            ["主题一", "主题二"],
        )

    def test_batch_options_use_topic_specific_draft_names(self):
        base = Options(
            topic="单个主题",
            story_world="校园",
            target_chars="260",
            draft_name="手动草稿名",
        )

        options = build_batch_options(base, ["主题一", "主题二？"], batch_id="20260721_220000")

        self.assertEqual([item.topic for item in options], ["主题一", "主题二？"])
        self.assertEqual(
            [item.draft_name for item in options],
            ["主题一_20260721_220000", "主题二？_20260721_220000"],
        )
        self.assertEqual(base.draft_name, "手动草稿名")

    def test_batch_runner_continues_after_one_topic_fails(self):
        events: queue.Queue[tuple[str, str]] = queue.Queue()
        runner = Runner(events)
        options = [
            Options(topic="失败主题", story_world="", target_chars="0"),
            Options(topic="成功主题", story_world="", target_chars="0"),
        ]
        command_sets = [
            ([("步骤", ["first"])], Path("first")),
            ([("步骤", ["second"])], Path("second")),
        ]

        with patch("src.pipeline_runtime.build_commands", side_effect=command_sets), patch.object(
            runner,
            "_execute_commands",
            side_effect=[RuntimeError("测试失败"), None],
        ) as execute:
            runner._run_batch(options)

        emitted = []
        while not events.empty():
            emitted.append(events.get_nowait())
        self.assertEqual(execute.call_count, 2)
        self.assertIn(("status", "部分失败"), emitted)
        self.assertIn(("batch_progress", "成功 1，失败 1"), emitted)

    def test_copywriting_action_is_labeled_as_editable(self):
        copy_step = next(step for step in STEP_DEFS if step[0] == "copy")
        self.assertEqual(copy_step[4], "查看并修改文案")

    def test_image_action_is_labeled_as_editable(self):
        image_step = next(step for step in STEP_DEFS if step[0] == "images")
        self.assertEqual(image_step[4], "查看并修改图片")

    def test_layout_step_has_visible_button_explanation(self):
        self.assertEqual(
            STEP_BUTTON_DESCRIPTIONS["layout"],
            "读取现有文案时间线、分镜、图片和字幕\n重新计算图片尺寸、元素位置、关键词排布及动态重排",
        )

    def test_selected_image_regeneration_command_contains_only_selected_ids(self):
        command = build_image_regeneration_command(
            Path("image_prompts_plus.csv"),
            ["s1_img01", "s3_img02"],
            image_model="gpt-image-2",
            image_quality="high",
            visual_theme="白色主题",
        )

        self.assertIn("--overwrite", command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-image-2")
        self.assertEqual(command[command.index("--quality") + 1], "high")
        self.assertEqual(command[command.index("--theme") + 1], "white")
        self.assertEqual(
            [command[index + 1] for index, value in enumerate(command) if value == "--element-id"],
            ["s1_img01", "s3_img02"],
        )

    def test_portrait_package_command_is_separate_from_native_pipeline(self):
        command = build_portrait_package_command(
            Path("output/topic/landscape"),
            Path("exports/topic.mp4"),
            draft_folder="drafts",
            draft_name="topic_portrait_package",
            project_title="Topic",
            visual_theme="white",
            include_subtitles=True,
            include_background=False,
        )

        self.assertIn("src.commands.build_portrait_package", command)
        self.assertEqual(command[command.index("--draft-name") + 1], "topic_portrait_package")
        self.assertEqual(command[command.index("--title") + 1], "Topic")
        self.assertEqual(command[command.index("--theme") + 1], "white")
        self.assertNotIn("--no-subtitles", command)
        self.assertIn("--no-background", command)

    def test_copywriting_editor_saves_utf8_text_atomically(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wenan.txt"
            path.write_text("旧文案\n", encoding="utf-8")

            result = save_copywriting_text(path, "新标题\r\n新正文\r\n\r\n")

            self.assertEqual(result, path.resolve())
            self.assertEqual(path.read_text(encoding="utf-8"), "新标题\n新正文\n")
            self.assertFalse((path.parent / ".wenan.txt.tmp").exists())

    def test_copywriting_editor_rejects_empty_content(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wenan.txt"
            path.write_text("原文\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "文案不能为空"):
                save_copywriting_text(path, " \n\t")

            self.assertEqual(path.read_text(encoding="utf-8"), "原文\n")

    def test_full_pipeline_generates_images_by_default(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
        ))
        self.assertEqual([label for label, _ in commands], [
            "01 文案",
            "02 配音",
            "03 分镜",
            "04 图片内容",
            "05 生图提示词",
            "06 图片",
            "07 布局",
            "08 草稿",
        ])

    def test_full_pipeline_can_skip_image_generation(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
            run_images=False,
        ))
        self.assertNotIn("06 图片", [label for label, _ in commands])

    def test_direct_video_includes_title_and_subtitles(self):
        commands, _ = build_commands(Options(
            topic="Topic",
            story_world="",
            target_chars="0",
            orientation="landscape",
            include_title=True,
            include_subtitles=True,
        ))
        layout_command = next(command for _, command in commands if "src.07_compile_layout" in command)
        draft_command = next(command for _, command in commands if "src.08_generate_jianying_draft" in command)

        self.assertIn("--subtitles", layout_command)
        self.assertNotIn("--no-subtitles", layout_command)
        self.assertEqual(draft_command[draft_command.index("--title") + 1], "Topic")

    def test_landscape_master_omits_title_and_subtitles(self):
        commands, _ = build_commands(Options(
            topic="Topic",
            story_world="",
            target_chars="0",
            orientation="landscape",
            include_title=False,
            include_subtitles=False,
        ))
        layout_command = next(command for _, command in commands if "src.07_compile_layout" in command)
        draft_command = next(command for _, command in commands if "src.08_generate_jianying_draft" in command)

        self.assertIn("--no-subtitles", layout_command)
        self.assertNotIn("--subtitles", layout_command)
        self.assertEqual(draft_command[draft_command.index("--title") + 1], "")

    def test_image_command_uses_project_prompt_csv(self):
        commands, output_dir = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
        ))
        image_command = next(command for label, command in commands if label == "06 图片")
        self.assertEqual(image_command[3], str(output_dir / "image_prompts_plus.csv"))

    def test_selected_image_model_is_passed_to_image_command(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
            image_model="gpt-image-2",
        ))
        image_command = next(command for label, command in commands if label == "06 图片")
        self.assertEqual(image_command[image_command.index("--model") + 1], "gpt-image-2")

    def test_selected_visual_theme_is_passed_to_all_theme_sensitive_steps(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
            visual_theme="白色主题",
        ))
        for label in ("05 生图提示词", "06 图片", "07 布局", "08 草稿"):
            command = next(command for command_label, command in commands if command_label == label)
            self.assertEqual(command[command.index("--theme") + 1], "white")

    def test_selected_orientation_is_passed_to_prompt_layout_and_draft_steps(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
            orientation="横屏",
        ))

        for label in ("04 图片内容", "05 生图提示词", "07 布局", "08 草稿"):
            command = next(command for command_label, command in commands if command_label == label)
            self.assertEqual(command[command.index("--orientation") + 1], "横屏")

    def test_explicit_image_rerun_can_overwrite_existing_assets(self):
        commands, _ = build_commands(Options(
            topic="测试主题",
            story_world="校园",
            target_chars="260",
            run_copy=False,
            run_voice=False,
            run_shots=False,
            run_prompts=False,
            run_images=True,
            overwrite_images=True,
            run_layout=False,
            run_draft=False,
        ))
        image_command = next(command for label, command in commands if label == "06 图片")
        self.assertIn("--overwrite", image_command)

    def test_portrait_and_landscape_use_isolated_project_roots_and_drafts(self):
        portrait_commands, portrait_dir = build_commands(Options(
            topic="同一主题",
            story_world="",
            target_chars="0",
            orientation="portrait",
        ))
        landscape_commands, landscape_dir = build_commands(Options(
            topic="同一主题",
            story_world="",
            target_chars="0",
            orientation="landscape",
        ))

        self.assertEqual(portrait_dir.name, "portrait")
        self.assertEqual(landscape_dir.name, "landscape")
        self.assertNotEqual(portrait_dir, landscape_dir)
        self.assertEqual(
            next(command for label, command in portrait_commands if label == "08 草稿")[
                next(command.index("--draft-name") + 1 for command in [
                    next(command for label, command in portrait_commands if label == "08 草稿")
                ])
            ].endswith("_portrait"),
            True,
        )
        landscape_draft = next(command for label, command in landscape_commands if label == "08 草稿")
        self.assertTrue(landscape_draft[landscape_draft.index("--draft-name") + 1].endswith("_landscape"))
        for commands, project_dir in ((portrait_commands, portrait_dir), (landscape_commands, landscape_dir)):
            for label in ("01 文案", "03 分镜", "04 图片内容", "05 生图提示词", "06 图片", "07 布局", "08 草稿"):
                command = next(command for command_label, command in commands if command_label == label)
                self.assertTrue(
                    any(str(value).startswith(str(project_dir)) for value in command if isinstance(value, str)),
                    label,
                )

    def test_empty_optional_paths_use_safe_defaults(self):
        commands, _ = build_commands(Options(topic="测试主题", story_world="", target_chars="", draft_folder=""))
        copy_command = next(command for label, command in commands if label == "01 文案")
        draft_command = next(command for label, command in commands if label == "08 草稿")
        self.assertEqual(copy_command[copy_command.index("--target-chars") + 1], "0")
        self.assertEqual(draft_command[draft_command.index("--draft-folder") + 1], str(default_draft_folder()))

    def test_invalid_topic_and_target_chars_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "主题不能为空"):
            build_commands(Options(topic=" ", story_world="", target_chars="0"))
        with self.assertRaisesRegex(ValueError, "目标字数"):
            build_commands(Options(topic="测试", story_world="", target_chars="abc"))

    def test_selected_mp3_or_mp4_is_passed_to_draft_command(self):
        with TemporaryDirectory() as temp_dir:
            for suffix in (".mp3", ".mp4"):
                music = Path(temp_dir) / f"music{suffix}"
                music.write_bytes(b"music")
                commands, _ = build_commands(Options(
                    topic="测试",
                    story_world="",
                    target_chars="0",
                    background_music=str(music),
                ))
                draft_command = next(command for label, command in commands if label == "08 草稿")
                self.assertEqual(draft_command[draft_command.index("--bgm") + 1], str(music.resolve()))

    def test_background_music_can_be_disabled(self):
        commands, _ = build_commands(Options(
            topic="测试",
            story_world="",
            target_chars="0",
            include_background_music=False,
        ))
        draft_command = next(command for label, command in commands if label == "08 草稿")
        self.assertIn("--no-bgm", draft_command)
        self.assertNotIn("--bgm", draft_command)

    def test_custom_background_image_is_passed_to_draft_command(self):
        with TemporaryDirectory() as temp_dir:
            background = Path(temp_dir) / "custom.png"
            background.write_bytes(b"image")
            commands, _ = build_commands(Options(
                topic="测试",
                story_world="",
                target_chars="0",
                background_image=str(background),
            ))

        draft_command = next(command for label, command in commands if label == "08 草稿")
        self.assertEqual(
            draft_command[draft_command.index("--background") + 1],
            str(background.resolve()),
        )

    def test_white_theme_uses_white_default_background_when_not_overridden(self):
        commands, _ = build_commands(Options(
            topic="测试",
            story_world="",
            target_chars="0",
            visual_theme="white",
        ))
        draft_command = next(command for label, command in commands if label == "08 草稿")

        self.assertEqual(
            Path(draft_command[draft_command.index("--background") + 1]).parts[-3:],
            ("picturies", "background", "background_2.png"),
        )

    def test_relocated_project_asset_paths_are_resolved_from_project_root(self):
        commands, _ = build_commands(Options(
            topic="test",
            story_world="",
            target_chars="0",
            background_image="/Users/a1234/Desktop/old/donghuakoubo/picturies/background/background_2.png",
            background_music="/Users/a1234/Desktop/old/donghuakoubo/audio/bgm/bgm1.mp4",
        ))
        draft_command = next(command for label, command in commands if label == "08 草稿")

        self.assertEqual(
            Path(draft_command[draft_command.index("--background") + 1]).parts[-3:],
            ("picturies", "background", "background_2.png"),
        )
        self.assertEqual(
            Path(draft_command[draft_command.index("--bgm") + 1]).parts[-3:],
            ("audio", "bgm", "bgm1.mp4"),
        )

    def test_unsupported_background_music_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            music = Path(temp_dir) / "music.wav"
            music.write_bytes(b"music")
            with self.assertRaisesRegex(ValueError, "MP3 或 MP4"):
                build_commands(Options(
                    topic="测试",
                    story_world="",
                    target_chars="0",
                    background_music=str(music),
                ))

    def test_api_settings_preserve_other_env_values(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OTHER=value\nDEEPSEEK_API_KEY=old\n", encoding="utf-8")
            update_env_file(env_path, {"DEEPSEEK_API_KEY": "new", "VOLC_ACCESSKEY": "ak"})
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("OTHER=value", content)
            self.assertIn("DEEPSEEK_API_KEY=new", content)
            self.assertIn("VOLC_ACCESSKEY=ak", content)
            self.assertNotIn("DEEPSEEK_API_KEY=old", content)


if __name__ == "__main__":
    unittest.main()
