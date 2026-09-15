from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ..prepare.topic_generation import (
    generate_unique_topic,
    generate_unique_topics,
    load_topic_catalog,
    load_used_topics,
    normalize_topic,
    topic_comparison_key,
    record_topic,
)


class TopicGenerationTest(unittest.TestCase):
    def test_load_topic_catalog_reads_marked_section_and_inline_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "主题清单.md"
            path.write_text(
                "## 已有主题\n- [ ] 主题一\n"
                "## 待制作主题（暂缓/感觉一般）\n- [ ] 主题二\n"
                "- [ ] 主题三 [感觉一般]\n",
                encoding="utf-8",
            )
            listed, discouraged = load_topic_catalog(path)
            self.assertEqual(listed, ["主题一", "主题二", "主题三"])
            self.assertEqual(discouraged, ["主题二", "主题三"])

    def test_generated_topic_goes_to_unreviewed_section(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "主题清单.md"
            catalog.write_text(
                "## 已有主题\n\n"
                "## 待制作主题（暂缓/感觉一般）\n\n"
                "## 待评估主题（尚未查看）\n",
                encoding="utf-8",
            )
            record_topic("尚未评估的新主题", topic_list_path=catalog)
            content = catalog.read_text(encoding="utf-8")
            self.assertIn("## 待评估主题（尚未查看）\n- [ ] 尚未评估的新主题", content)
            self.assertNotIn("尚未评估的新主题", content.split("## 待评估主题")[0])

    def test_record_topic_updates_markdown_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "主题清单.md"
            record_topic("归档主题", status="used", topic_list_path=catalog)
            content = catalog.read_text(encoding="utf-8")
            self.assertIn("## 已有主题", content)
            self.assertIn("- [x] 归档主题", content)

    def test_topic_comparison_normalizes_cosmetic_variants(self):
        self.assertEqual(normalize_topic("什么是 ComfyUI？"), normalize_topic("什么是comfyui"))
        self.assertEqual(topic_comparison_key("什么是缓存"), topic_comparison_key("缓存是什么？"))
        self.assertEqual(
            topic_comparison_key("内存和硬盘有什么区别"),
            topic_comparison_key("内存和磁盘有什么区别"),
        )

    def test_load_used_topics_merges_history_and_existing_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "主题清单.md"
            catalog.write_text("## 已有主题\n- [ ] 为什么索引不是越多越好？\n", encoding="utf-8")
            project = root / "什么是缓存"
            project.mkdir()
            (project / "wenan.txt").write_text("什么是缓存\n正文\n", encoding="utf-8")

            topics = load_used_topics(output_root=root, topic_list_path=catalog)
            self.assertEqual(topics, ["为什么索引不是越多越好？", "什么是缓存"])

    def test_generate_unique_topic_retries_model_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "主题清单.md"
            catalog.write_text("## 已有主题\n- [ ] 什么是缓存\n", encoding="utf-8")
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
                    topic_list_path=catalog,
                )

            self.assertEqual(topic, "为什么数据库索引不是越多越好")
            self.assertEqual(client.chat.completions.create.call_count, 2)
            messages = client.chat.completions.create.call_args_list[0].kwargs["messages"]
            self.assertIn("用户指定的选题大方向是：数据库", messages[1]["content"])
            self.assertIn("必须直接属于这个方向", messages[1]["content"])
            self.assertIn("看完后能解决问题或立即采取行动", messages[1]["content"])
            self.assertIn("用户看完后能立刻获得实际帮助", messages[0]["content"])
            self.assertIn("看完后能采取什么行动", messages[0]["content"])
            self.assertIn(topic, load_used_topics(output_root=root, topic_list_path=catalog))

    def test_generate_unique_topic_retries_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            responses = [
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                    '{"candidates":[{"topic":"缺少逗号的主题" "score":9}]}'
                )))]),
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                    '{"candidates":[{"topic":"为什么电脑休眠后网络会断开",'
                    '"audience":"普通用户","scenario":"电脑休眠后",'
                    '"problem":"网络断开","action":"检查电源设置",'
                    '"reason":"可以解决实际问题","score":9}]}'
                )))]),
            ]
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=responses))))
            with patch("src.prepare.topic_generation.OpenAI", return_value=client):
                topic = generate_unique_topic(api_key="key", output_root=root)

            self.assertEqual(topic, "为什么电脑休眠后网络会断开")
            self.assertEqual(client.chat.completions.create.call_count, 2)
            retry_prompt = client.chat.completions.create.call_args_list[1].kwargs["messages"][1]["content"]
            self.assertIn("上一次输出无法解析", retry_prompt)

    def test_generate_unique_topic_uses_current_topic_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "主题清单.md"
            catalog.write_text(
                "## 已有主题\n- [ ] 已讲过的主题\n"
                "## 待制作主题（暂缓/感觉一般）\n- [ ] 不太满意的主题\n",
                encoding="utf-8",
            )
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"candidates":[{"topic":"新的具体问题","audience":"普通用户",'
                '"scenario":"日常使用","problem":"判断原因","action":"按步骤检查",'
                '"reason":"实用","score":9}]}'
            )))])
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response))))
            with patch("src.prepare.topic_generation.OpenAI", return_value=client):
                topic = generate_unique_topic(
                    direction="计算机",
                    current_topic="当前正在制作的主题",
                    api_key="key",
                    output_root=root,
                    topic_list_path=catalog,
                )
            self.assertEqual(topic, "新的具体问题")
            prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
            self.assertIn("当前正在制作的主题", prompt)
            self.assertIn("不太满意的主题", prompt)

    def test_generate_unique_topic_uses_context_and_selects_best_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
                )

            self.assertEqual(topic, "为什么电脑内存还有很多却会变慢")
            prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
            self.assertIn("面向普通 Windows 用户", prompt)
            self.assertIn("内存、进程、磁盘原理", prompt)

    def test_similar_topic_subset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "主题清单.md"
            catalog.write_text("## 已有主题\n- [ ] 为什么电脑运行越来越慢\n", encoding="utf-8")
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
                    topic_list_path=catalog,
                )

            self.assertEqual(topic, "Windows 进程太多怎么排查")

    def test_generate_unique_topics_builds_requested_batch(self):
        progress: list[str] = []
        with patch(
            "src.prepare.topic_generation.generate_unique_topic",
            side_effect=["主题一", "主题二", "主题三"],
        ) as generate:
            self.assertEqual(
                generate_unique_topics(
                    3,
                    direction="计算机操作系统",
                    progress_callback=progress.append,
                ),
                ["主题一", "主题二", "主题三"],
            )
            self.assertEqual(
                [call.kwargs["direction"] for call in generate.call_args_list],
                ["计算机操作系统"] * 3,
            )
            self.assertEqual(progress[0], "正在生成第 1/3 个主题...")
            self.assertIn("第 3/3 个主题生成完成：主题三", progress)
        with self.assertRaisesRegex(ValueError, "1 到 30"):
            generate_unique_topics(31)

    def test_topic_direction_has_a_reasonable_length_limit(self):
        with self.assertRaisesRegex(ValueError, "200"):
            generate_unique_topic(direction="x" * 201, api_key="key")


if __name__ == "__main__":
    unittest.main()
