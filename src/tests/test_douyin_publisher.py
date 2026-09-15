from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..application.douyin_publisher import (
    DouyinPublishError,
    DouyinPublishRequest,
    _find_publish_button,
    _set_file_input,
    _wait_for_publish_success,
    _wait_for_upload_complete,
    discover_publish_assets,
    normalize_topics,
    publish_description,
)


class DouyinPublisherTest(unittest.TestCase):
    def test_publish_button_requires_exact_accessible_name(self):
        class FakeLocator:
            @property
            def first(self):
                return self

            def is_visible(self, timeout=None):
                return True

        class FakePage:
            def get_by_role(self, role, *, name, exact):
                self.lookup = (role, name, exact)
                return FakeLocator()

            def locator(self, _selector):
                return FakeLocator()

        page = FakePage()
        self.assertIsNotNone(_find_publish_button(page, timeout_ms=100))
        self.assertEqual(page.lookup, ("button", "发布", True))

    def test_large_file_input_uses_direct_cdp_path(self):
        class FakeSession:
            def __init__(self):
                self.calls = []
                self.detached = False

            def send(self, method, params):
                self.calls.append((method, params))
                if method == "DOM.getDocument":
                    return {"root": {"nodeId": 1}}
                if method == "DOM.querySelector":
                    return {"nodeId": 2}
                return {}

            def detach(self):
                self.detached = True

        class FakeLocator:
            def set_input_files(self, _path):
                raise AssertionError("large files must bypass Playwright transfer")

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "large.mp4"
            with video.open("wb") as file_obj:
                file_obj.truncate(51 * 1024 * 1024)
            session = FakeSession()
            context = type("FakeContext", (), {"new_cdp_session": lambda self, page: session})()
            page = type("FakePage", (), {"context": context})()

            _set_file_input(page, FakeLocator(), video, selectors=('input[type="file"]',))

        self.assertIn(
            ("DOM.setFileInputFiles", {"nodeId": 2, "files": [str(video)]}),
            session.calls,
        )
        self.assertTrue(session.detached)

    def test_upload_wait_uses_douyin_completed_marker(self):
        class FakeLocator:
            def __init__(self, *, count=0, visible=False, enabled=True):
                self._count = count
                self._visible = visible
                self._enabled = enabled

            @property
            def first(self):
                return self

            def count(self):
                return self._count

            def is_visible(self, timeout=None):
                return self._visible

            def is_enabled(self, timeout=None):
                return self._enabled

        class FakePage:
            def evaluate(self, *_args):
                return None

            def get_by_role(self, role, *, name, exact):
                self.test_case.assertEqual((role, name, exact), ("button", "发布", True))
                return FakeLocator(visible=True)

            def locator(self, selector):
                if "重新上传" in selector:
                    return FakeLocator(count=1)
                return FakeLocator(visible="发布" in selector)

        page = FakePage()
        page.test_case = self
        _wait_for_upload_complete(page, timeout_ms=1000)

    def test_publish_wait_accepts_manage_page_url(self):
        class FakeLocator:
            @property
            def first(self):
                return self

            def is_visible(self, timeout=None):
                return False

        class FakePage:
            url = "https://creator.douyin.com/creator-micro/content/manage"

            def locator(self, _selector):
                return FakeLocator()

        _wait_for_publish_success(FakePage(), timeout_ms=1000)

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

    def test_discover_publish_assets_finds_canonical_topic_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "什么是AI" / "portrait" / "什么是AI_portrait.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")

            discovered, _cover = discover_publish_assets(
                "什么是 AI",
                output_root=root,
                home=root / "empty-home",
            )

            self.assertEqual(discovered, video.resolve())
