from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ..application.douyin_publisher import (
    DouyinPublishError,
    DouyinPublishRequest,
    _cover_is_portrait,
    _disable_download,
    _fill_description,
    _find_publish_button,
    generate_publish_metadata,
    _set_file_input,
    _wait_for_publish_success,
    _wait_for_upload_complete,
    discover_publish_assets,
    normalize_topics,
    publish_description,
)


class DouyinPublisherTest(unittest.TestCase):
    def test_disable_download_turns_checked_switch_off(self):
        class FakeControl:
            def __init__(self):
                self.checked = True
                self.clicks = 0

            def is_checked(self, timeout=None):
                return self.checked

            def locator(self, _selector):
                return FakeCollection([])

            def click(self, timeout=None):
                self.clicks += 1
                self.checked = False

        class FakeCollection:
            def __init__(self, items):
                self.items = items

            def count(self):
                return len(self.items)

            def nth(self, index):
                return self.items[index]

        class FakeLabel:
            def __init__(self, control):
                self.control = control

            def get_attribute(self, name, timeout=None):
                return None

            def locator(self, selector):
                if selector.startswith("xpath="):
                    return FakeContainer(self.control)
                return FakeCollection([])

        class FakeContainer:
            def __init__(self, control):
                self.control = control

            def locator(self, selector):
                if "checkbox" in selector:
                    return FakeCollection([self.control])
                return FakeCollection([])

        control = FakeControl()
        label = FakeLabel(control)
        page = type(
            "FakePage",
            (),
            {
                "evaluate": lambda self, *_args: None,
                "locator": lambda self, selector: FakeContainer(control),
                "wait_for_timeout": lambda self, _timeout: None,
            },
        )()
        with patch("src.application.douyin_publisher._first_visible", side_effect=[label] + [None] * 5):
            self.assertTrue(_disable_download(page))
        self.assertEqual(control.clicks, 1)

    def test_disable_download_keeps_unchecked_switch_off(self):
        control = type(
            "FakeControl",
            (),
            {
                "is_checked": lambda self, timeout=None: False,
                "click": lambda self, timeout=None: self.fail("should not click"),
            },
        )()
        controls = type("Controls", (), {"count": lambda self: 1, "nth": lambda self, index: control})()
        container = type("Container", (), {"locator": lambda self, selector: controls})()
        label = type(
            "Label",
            (),
            {
                "get_attribute": lambda self, name, timeout=None: None,
                "locator": lambda self, selector: container,
            },
        )()
        page = type("FakePage", (), {"evaluate": lambda self, *_args: None})()
        with patch("src.application.douyin_publisher._first_visible", return_value=label):
            self.assertTrue(_disable_download(page))

    def test_disable_download_rejects_unverifiable_page(self):
        page = type("FakePage", (), {"evaluate": lambda self, *_args: None})()
        with patch("src.application.douyin_publisher._first_visible", return_value=None):
            with self.assertRaisesRegex(DouyinPublishError, "没有找到"):
                _disable_download(page)

    def test_fill_description_commits_topics_as_hashtag_tokens(self):
        class FakeLocator:
            def __init__(self):
                self.calls = []

            @property
            def first(self):
                return self

            def is_visible(self, timeout=None):
                return True

            def click(self):
                self.calls.append(("click",))

            def press(self, value):
                self.calls.append(("press", value))

            def type(self, value):
                self.calls.append(("type", value))

        locator = FakeLocator()

        class FakePage:
            def locator(self, _selector):
                return locator

        _fill_description(FakePage(), "正文内容", ("#人工智能", "#电脑技巧"))

        self.assertIn(("type", "正文内容"), locator.calls)
        self.assertIn(("type", " #人工智能"), locator.calls)
        self.assertIn(("press", "Space"), locator.calls)
        self.assertIn(("type", " #电脑技巧"), locator.calls)

    def test_generate_publish_metadata_normalizes_model_topics(self):
        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": '{"title":"为什么电脑会变慢？","topics":["电脑技巧","#效率提升","电脑技巧"]}'})()},
                    )
                ]
            },
        )()
        with patch("src.application.douyin_publisher.OpenAI") as client_factory:
            client_factory.return_value.chat.completions.create.return_value = response
            title, topics = generate_publish_metadata("电脑为什么会变慢", api_key="test-key")

        self.assertEqual(title, "为什么电脑会变慢？")
        self.assertEqual(topics, ("#电脑技巧", "#效率提升"))

    def test_cover_orientation_follows_generated_dimensions(self):
        self.assertTrue(_cover_is_portrait(Path("主题_cover_1080x1920.png")))
        self.assertFalse(_cover_is_portrait(Path("主题_cover_1920x1080.png")))
        self.assertFalse(_cover_is_portrait(Path("cover.png")))

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
