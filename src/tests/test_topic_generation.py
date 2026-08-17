from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ..prepare.topic_generation import (
    generate_unique_topic,
    generate_unique_topics,
    load_used_topics,
    normalize_topic,
    topic_comparison_key,
    record_topic,
)


class TopicGenerationTest(unittest.TestCase):
    def test_normalize_topic_ignores_punctuation_spacing_and_case(self):
        self.assertEqual(normalize_topic("什么是 ComfyUI？"), normalize_topic("什么是comfyui"))

    def test_topic_comparison_key_catches_reordered_question_wrappers(self):
        self.assertEqual(topic_comparison_key("什么是缓存"), topic_comparison_key("缓存是什么？"))

    def test_load_used_topics_merges_history_and_existing_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "topic_history.jsonl"
            record_topic("为什么索引不是越多越好？", history_path=history)
            project = root / "什么是缓存"
            project.mkdir()
            (project / "wenan.txt").write_text("什么是缓存\n正文\n", encoding="utf-8")

            topics = load_used_topics(output_root=root, history_path=history)
            self.assertEqual(topics, ["为什么索引不是越多越好？", "什么是缓存"])

    def test_generate_unique_topic_retries_model_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "topic_history.jsonl"
            record_topic("什么是缓存", history_path=history)
            responses = [
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"topic":"什么是缓存？"}'))]),
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"topic":"为什么数据库索引不是越多越好"}'))]),
            ]
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=responses))))
            with patch("src.prepare.topic_generation.OpenAI", return_value=client):
                topic = generate_unique_topic(
                    api_key="key",
                    output_root=root,
                    history_path=history,
                )

            self.assertEqual(topic, "为什么数据库索引不是越多越好")
            self.assertEqual(client.chat.completions.create.call_count, 2)
            self.assertIn(topic, load_used_topics(output_root=root, history_path=history))

    def test_generate_unique_topics_builds_requested_batch(self):
        with patch("src.prepare.topic_generation.generate_unique_topic", side_effect=["主题一", "主题二", "主题三"]):
            self.assertEqual(generate_unique_topics(3), ["主题一", "主题二", "主题三"])
        with self.assertRaisesRegex(ValueError, "1 到 30"):
            generate_unique_topics(31)


if __name__ == "__main__":
    unittest.main()
