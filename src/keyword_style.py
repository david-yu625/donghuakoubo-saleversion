"""Semantic font and color runs for keyword text."""

from __future__ import annotations

from dataclasses import dataclass

from .settings import DEFAULT_KEYWORD_COLOR


SEMANTIC_KEYWORD_COLORS = {
    "positive": "#F4C542",
    "risk": "#EE7A7A",
    "quantity": "#F28C28",
    "technology": DEFAULT_KEYWORD_COLOR,
    "concept": "#F4C542",
    "neutral": DEFAULT_KEYWORD_COLOR,
}
SEMANTIC_KEYWORDS = {
    "positive": (
        "少很多", "降低", "减少", "节省", "提升", "增长", "成功", "收益", "效率",
        "优化", "改善", "优势", "机会", "学习", "更快", "更强", "免费",
    ),
    "risk": (
        "耗电", "消耗", "电力", "风险", "危险", "失败", "错误", "问题", "下降",
        "亏损", "成本", "污染", "浪费", "淘汰", "失业", "焦虑", "骗局", "惊人", "夸张",
    ),
    "quantity": (
        "几百上千", "海量", "万", "亿", "千", "百", "几十", "数十", "数百", "数千",
        "数万", "几天", "一次", "每秒", "/秒", "倍", "%", "％",
    ),
    "technology": (
        "AI", "GPU", "CPU", "模型", "算法", "数据", "参数", "芯片", "计算", "运算",
        "训练", "推理", "显存", "内存", "并行", "软件", "硬件", "机器人", "互联网", "旋钮",
    ),
    "concept": (
        "本质", "原理", "原因", "核心", "关键", "规律", "逻辑", "真相", "方法", "结果",
    ),
}


@dataclass(frozen=True)
class KeywordColorRun:
    start: int
    end: int
    category: str
    color: str


def semantic_keyword_runs(text: str, role: str = "label") -> list[KeywordColorRun]:
    if not text:
        return []
    normalized = text.upper()
    fallback_category = "quantity" if role == "number" else "neutral"
    runs: list[KeywordColorRun] = []
    index = 0
    while index < len(text):
        matches = [
            (len(keyword), category)
            for category, keywords in SEMANTIC_KEYWORDS.items()
            for keyword in keywords
            if normalized.startswith(keyword.upper(), index)
        ]
        if matches:
            length, category = max(matches, key=lambda item: item[0])
        else:
            length, category = 1, fallback_category
        color = SEMANTIC_KEYWORD_COLORS[category]
        if runs and runs[-1].category == category and runs[-1].end == index:
            previous = runs[-1]
            runs[-1] = KeywordColorRun(previous.start, index + length, category, color)
        else:
            runs.append(KeywordColorRun(index, index + length, category, color))
        index += length
    return runs


def semantic_keyword_style(text: str, role: str = "label") -> tuple[str, str]:
    runs = semantic_keyword_runs(text, role)
    meaningful = [run for run in runs if run.category != "neutral"]
    selected = max(meaningful or runs, key=lambda run: run.end - run.start, default=None)
    if selected is None:
        return "neutral", SEMANTIC_KEYWORD_COLORS["neutral"]
    return selected.category, selected.color
