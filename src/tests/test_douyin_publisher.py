from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..application.douyin_publisher import (
    DouyinPublishError,
    DouyinPublishRequest,
    discover_publish_assets,
    normalize_topics,
    publish_description,
)


class DouyinPublisherTest(unittest.TestCase):
    def test_publish_request_normalizes_and_validates_video(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "clip.mp4"
            video.write_bytes(b"video")
            request = DouyinPublishRequest(video, "  计算机冷知识  ", "  #计算机  ")

            self.assertEqual(
                request.validated(),
                DouyinPublishRequest(video.resolve(), "计算机冷知识", "#计算机"),
            )

    def test_publish_request_rejects_missing_video_and_long_title(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DouyinPublishError, "视频文件不存在"):
                DouyinPublishRequest(Path(directory) / "missing.mp4", "标题").validated()

            video = Path(directory) / "clip.mp4"
            video.write_bytes(b"video")
            with self.assertRaisesRegex(DouyinPublishError, "不能超过 55"):
                DouyinPublishRequest(video, "标题" * 56).validated()

    def test_topics_are_normalized_and_added_to_description(self):
        self.assertEqual(normalize_topics("#人工智能 计算机知识, #人工智能"), ("#人工智能", "#计算机知识"))
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "clip.mp4"
            video.write_bytes(b"video")
            request = DouyinPublishRequest(video, "标题", "简介", topics="人工智能 计算机知识")
            self.assertEqual(publish_description(request), "简介 #人工智能 #计算机知识")

    def test_discover_publish_assets_prefers_explicit_video_and_latest_cover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "主题" / "landscape"
            project.mkdir(parents=True)
            generated = project / "主题_landscape.mp4"
            generated.write_bytes(b"video")
            cover_dir = root / "主题" / "cover"
            cover_dir.mkdir()
            first = cover_dir / "主题_cover_1080x1920.png"
            second = cover_dir / "主题_cover_1920x1080.png"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            explicit = root / "chosen.mp4"
            explicit.write_bytes(b"chosen")
            video, cover = discover_publish_assets(
                "主题",
                output_root=root,
                preferred_video=explicit,
                home=root / "home",
            )
            self.assertEqual(video, explicit.resolve())
            self.assertEqual(cover, second.resolve())
