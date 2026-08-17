from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..application.douyin_publisher import DouyinPublishError, DouyinPublishRequest


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

