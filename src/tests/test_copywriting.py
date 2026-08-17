from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


copywriting = importlib.import_module("src.01_generate_copywriting")


class CopywritingResponseTest(unittest.TestCase):
    def test_prompt_is_general_purpose_and_preserves_topic_domain(self):
        self.assertIn("短视频科普口播文案作者", copywriting.SYSTEM_PROMPT)
        self.assertIn("输入是什么、经过哪些处理、输出怎样变化", copywriting.SYSTEM_PROMPT)
        self.assertIn("场景遇到什么问题、能观察到什么信号", copywriting.SYSTEM_PROMPT)
        self.assertIn("目标、阻碍、关键选择、转折和结果", copywriting.SYSTEM_PROMPT)
        self.assertIn("不要强行制造反常识、两次转折或戏剧冲突", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("每隔 3~5 行必须发生一次推进", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("至少两次转折", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("全文同类句式最多出现一次", copywriting.SYSTEM_PROMPT)
        self.assertIn("具体对象、过程或事件", copywriting.retention_guidance())
        self.assertIn("不强行制造反常识", copywriting.retention_guidance())

    def test_automatic_story_mode_does_not_force_a_named_story(self):
        guidance = copywriting.story_world_guidance("自动选择", "大模型如何生成文字")
        self.assertIn("根据题目本身选择最自然的表达", guidance)
        self.assertNotIn("以自动选择故事讲", guidance)
        self.assertNotIn("技术点", guidance)

        mythology = copywriting.story_world_guidance("", "八仙过海")
        self.assertIn("围绕题目本身展开", mythology)
        self.assertNotIn("CPU", mythology)

        explicit = copywriting.story_world_guidance("快递站", "TCP 为什么可靠")
        self.assertIn("以快递站故事讲TCP 为什么可靠", explicit)
        self.assertIn("服务于当前主题", explicit)

    def test_valid_json_and_code_fence(self):
        self.assertEqual(copywriting.parse_copywriting_payload('{"wenan":"标题\\n正文"}')["wenan"], "标题\n正文")
        fenced = '```json\n{"wenan":"标题\\n正文"}\n```'
        self.assertEqual(copywriting.parse_copywriting_payload(fenced)["wenan"], "标题\n正文")

    def test_repairs_raw_newlines_and_unescaped_quotes(self):
        malformed = '{"wenan":"什么是知识传递\n老师说"知识传递"很重要\n学生点头"}'
        payload = copywriting.parse_copywriting_payload(malformed)
        self.assertEqual(payload["wenan"], '什么是知识传递\n老师说"知识传递"很重要\n学生点头')

    def test_generate_copywriting_retries_with_json_repair_request(self):
        responses = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"wenan":"标题\\n第一层\\n第二层\\n第三层\\n第四层\\n结论"}'))]),
        ]
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=responses))))
        with patch.object(copywriting, "OpenAI", return_value=client):
            payload = copywriting.generate_copywriting(
                topic="测试",
                reference="",
                api_key="key",
                model="model",
                base_url="https://example.com",
                max_tokens=100,
                target_chars=100,
                story_world="",
            )
        self.assertIn("第一层", payload["wenan"])
        self.assertEqual(client.chat.completions.create.call_count, 2)
        first_prompt = client.chat.completions.create.call_args_list[0].kwargs["messages"][1]["content"]
        self.assertIn("本次创作硬约束", first_prompt)
        self.assertIn("具体对象、过程或事件", first_prompt)
        self.assertNotIn("至少两次转折", first_prompt)

    def test_single_line_copy_is_rewritten_as_layered_lines(self):
        responses = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"wenan":"标题，现象，原因，机制，结果"}'))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"wenan":"标题\\n具体现象\\n信息缺口\\n直接原因\\n更深机制\\n可见结果"}'))]),
        ]
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=responses))))
        with patch.object(copywriting, "OpenAI", return_value=client):
            payload = copywriting.generate_copywriting(
                topic="测试",
                reference="",
                api_key="key",
                model="model",
                base_url="https://example.com",
                max_tokens=100,
                target_chars=100,
                story_world="",
            )

        self.assertEqual(len(payload["wenan"].splitlines()), 6)
        self.assertEqual(client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
