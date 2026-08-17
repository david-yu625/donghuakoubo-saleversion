from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


copywriting = importlib.import_module("src.01_generate_copywriting")


class CopywritingResponseTest(unittest.TestCase):
    def test_prompt_is_general_purpose_and_preserves_topic_domain(self):
        self.assertIn("计算机资深从业者", copywriting.SYSTEM_PROMPT)
        self.assertIn("开头必须抛异常或者问题", copywriting.SYSTEM_PROMPT)
        self.assertIn("持续持续持续输出高密度价值信息", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("每句话采用6到15个字", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("结尾留钩子和悬念", copywriting.SYSTEM_PROMPT)
        self.assertIn("不需要做其他的分镜头设计", copywriting.SYSTEM_PROMPT)
        self.assertIn("不要虚构作者身份、账号名称", copywriting.SYSTEM_PROMPT)
        self.assertIn("不要在文案中自称", copywriting.SYSTEM_PROMPT)
        self.assertIn("每句话必须新增事实、因果或解释", copywriting.SYSTEM_PROMPT)
        self.assertIn("同一个问题只问一次", copywriting.SYSTEM_PROMPT)
        self.assertIn("结尾不要复述全文", copywriting.SYSTEM_PROMPT)
        self.assertIn("#文案框架", copywriting.SYSTEM_PROMPT)
        self.assertIn("题意锁定", copywriting.SYSTEM_PROMPT)
        self.assertIn("不能只抓其中一个关键词", copywriting.SYSTEM_PROMPT)
        self.assertIn("题型互相替换", copywriting.SYSTEM_PROMPT)
        self.assertIn("核心答案", copywriting.SYSTEM_PROMPT)
        self.assertIn("原因—关键过程—结果或影响", copywriting.SYSTEM_PROMPT)
        self.assertIn("不中途换题", copywriting.SYSTEM_PROMPT)
        self.assertIn("禁止虚构“大家都说”", copywriting.SYSTEM_PROMPT)
        self.assertIn("禁止强行反差、文字游戏", copywriting.SYSTEM_PROMPT)
        self.assertIn("如果正文不能直接回答", copywriting.SYSTEM_PROMPT)
        self.assertIn("#背景", copywriting.SYSTEM_PROMPT)
        self.assertIn("#目标", copywriting.SYSTEM_PROMPT)
        self.assertIn("#要求", copywriting.SYSTEM_PROMPT)
        self.assertNotIn("***", copywriting.SYSTEM_PROMPT)
        self.assertIn("#程序输出", copywriting.OUTPUT_PROTOCOL_PROMPT)

    def test_valid_json_and_code_fence(self):
        self.assertEqual(copywriting.parse_copywriting_payload('{"wenan":"标题\\n正文"}')["wenan"], "标题\n正文")
        fenced = '```json\n{"wenan":"标题\\n正文"}\n```'
        self.assertEqual(copywriting.parse_copywriting_payload(fenced)["wenan"], "标题\n正文")

    def test_system_prompt_receives_current_topic_in_initialization(self):
        prompt = copywriting.build_system_prompt("计算机起源")
        self.assertIn("#初始化", prompt)
        self.assertIn("我要讲解的题目是“计算机起源”。", prompt)
        self.assertNotIn("***", prompt)

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
        first_messages = client.chat.completions.create.call_args_list[0].kwargs["messages"]
        first_prompt = first_messages[-1]["content"]
        self.assertIn("我要讲解的题目是“测试”。", first_messages[0]["content"])
        self.assertNotIn("我要讲解的题目是“***”。", first_messages[0]["content"])
        self.assertIn("文案最长不超过 100 个有效字", first_prompt)
        self.assertIn("不是最低字数", first_prompt)
        self.assertIn("#字数要求", first_prompt)
        self.assertNotIn("至少两次转折", first_prompt)

    def test_length_guidance_is_sectioned_when_target_is_omitted(self):
        self.assertTrue(copywriting.length_guidance(0).startswith("#字数要求\n"))
        self.assertNotIn("6~15", copywriting.length_guidance(0))
        self.assertNotIn("建议输出", copywriting.length_guidance(250))
        self.assertIn("不是最低字数", copywriting.length_guidance(500))
        self.assertIn("通常以 350~450 字为合适篇幅", copywriting.length_guidance(500))
        self.assertIn("信息量大的主题可以写到接近 500 字", copywriting.length_guidance(500))

    def test_single_line_copy_is_saved_without_validation_retry(self):
        responses = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"wenan":"标题，现象，原因，机制，结果"}'))])]
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

        self.assertEqual(payload["wenan"], "标题，现象，原因，机制，结果")
        self.assertNotIn("_validation_warning", payload)
        self.assertEqual(client.chat.completions.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
