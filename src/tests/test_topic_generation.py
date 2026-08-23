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
                    direction="数据库",
                    api_key="key",
                    output_root=root,
                    history_path=history,
                )

            self.assertEqual(topic, "为什么数据库索引不是越多越好")
            self.assertEqual(client.chat.completions.create.call_count, 2)
            messages = client.chat.completions.create.call_args_list[0].kwargs["messages"]
            self.assertIn("用户指定的选题大方向是：数据库", messages[1]["content"])
            self.assertIn("必须直接属于这个方向", messages[1]["content"])
            self.assertIn("看完后能解决问题或立即采取行动", messages[1]["content"])
            self.assertIn("用户看完后能立刻获得实际帮助", messages[0]["content"])
            self.assertIn("看完后能采取什么行动", messages[0]["content"])
            self.assertIn(topic, load_used_topics(output_root=root, history_path=history))

    def test_generate_unique_topic_uses_context_and_selects_best_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "topic_history.jsonl"
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"candidates":['
                '{"topic":"什么是操作系统","score":10},'
                '{"topic":"为什么电脑内存还有很多却会变慢","audience":"普通用户","scenario":"电脑变慢","problem":"判断原因","action":"检查内存和进程","reason":"实用","score":9},'
                '{"topic":"磁盘清理有哪些误区","audience":"普通用户","scenario":"清理磁盘","problem":"避免误删","action":"按步骤检查","reason":"实用","score":8}'
                ']}')))])
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response))))
            with patch("src.prepare.topic_generation.OpenAI", return_value=client):
                topic = generate_unique_topic(
                    direction="计算机操作系统",
                    context="面向普通 Windows 用户，重点讲内存、进程、磁盘原理和提升电脑速度的实际操作。",
                    api_key="key",
                    output_root=root,
                    history_path=history,
                )

            self.assertEqual(topic, "为什么电脑内存还有很多却会变慢")
            prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
            self.assertIn("面向普通 Windows 用户", prompt)
            self.assertIn("内存、进程、磁盘原理", prompt)

    def test_similar_topic_subset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "topic_history.jsonl"
            record_topic("为什么电脑运行越来越慢", history_path=history)
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"candidates":['
                '{"topic":"电脑运行越来越慢怎么办","audience":"普通用户","scenario":"电脑变慢","problem":"排查原因","action":"检查系统","reason":"实用","score":10},'
                '{"topic":"Windows 进程太多怎么排查","audience":"Windows 用户","scenario":"任务管理器进程过多","problem":"找到异常进程","action":"按步骤排查","reason":"实用","score":8}'
                ']}')))])
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response))))
            with patch("src.prepare.topic_generation.OpenAI", return_value=client):
                topic = generate_unique_topic(
                    direction="计算机操作系统",
                    api_key="key",
                    output_root=root,
                    history_path=history,
                )

            self.assertEqual(topic, "Windows 进程太多怎么排查")

    def test_generate_unique_topics_builds_requested_batch(self):
        with patch(
            "src.prepare.topic_generation.generate_unique_topic",
            side_effect=["主题一", "主题二", "主题三"],
        ) as generate:
            self.assertEqual(
                generate_unique_topics(3, direction="计算机操作系统"),
                ["主题一", "主题二", "主题三"],
            )
            self.assertEqual(
                [call.kwargs["direction"] for call in generate.call_args_list],
                ["计算机操作系统"] * 3,
            )
        with self.assertRaisesRegex(ValueError, "1 到 30"):
            generate_unique_topics(31)

    def test_topic_direction_has_a_reasonable_length_limit(self):
        with self.assertRaisesRegex(ValueError, "200"):
            generate_unique_topic(direction="x" * 201, api_key="key")


if __name__ == "__main__":
    unittest.main()
