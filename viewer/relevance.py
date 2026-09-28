"""Conservative AI-policy relevance scoring."""

from __future__ import annotations

import re


VERSION = "2026-07-v1"


PHRASES = [
    "artificial intelligence", "generative ai", "generative artificial intelligence",
    "machine learning", "deep learning", "large language model", "foundation model",
    "algorithmic accountability", "algorithmic transparency", "algorithmic decision",
    "automated decision", "expert system", "neural network", "computer vision",
    "natural language processing", "facial recognition", "deepfake", "deep synthesis",
    "predictive algorithm", "ai governance", "ai safety", "ai risk", "ai system",
    "人工智能", "生成式ai", "生成式 AI", "生成式人工智能", "机器学习", "深度学习",
    "大语言模型", "基础模型", "算法治理", "算法监管", "算法透明", "自动化决策",
    "人脸识别", "深度合成", "智能算法", "人工智慧",
    "intelligence artificielle", "künstliche intelligenz", "intelligenza artificiale",
    "inteligencia artificial", "inteligência artificial", "kunstmatige intelligentie",
    "sztuczna inteligencja", "τεχνητή νοημοσύνη",
]


AI_ACRONYM = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")


def hits(text: str) -> list[str]:
    lowered = text.casefold()
    found = [phrase for phrase in PHRASES if phrase.casefold() in lowered]
    if AI_ACRONYM.search(text):
        found.append("AI")
    return found


def evaluate(title: str, topics: str, summary: str, structured: str) -> tuple[str, int, str]:
    title_hits = hits(title)
    topic_hits = hits(topics)
    summary_hits = hits(summary + "\n" + structured)
    if title_hits:
        return "明确相关", min(100, 80 + len(title_hits) * 4), "标题命中：" + "、".join(title_hits[:4])
    if topic_hits:
        return "明确相关", min(95, 72 + len(topic_hits) * 4), "主题字段命中：" + "、".join(topic_hits[:4])
    if summary_hits:
        return "可能相关", min(70, 45 + len(summary_hits) * 4), "摘要或结构化内容命中：" + "、".join(summary_hits[:4])
    return "待复核", 10, "标题、主题和摘要均未发现明确 AI 术语"
