"""web_search 工具：按配置依次尝试多个搜索源。"""

from __future__ import annotations

import json
from typing import Any

from ..config import Config
from ..search import SearchError, build_providers
from .base import FunctionTool, ToolResult


class WebSearchTool(FunctionTool):
    name = "web_search"
    description = (
        "在互联网上搜索信息，返回若干条标题、链接和摘要。"
        "适合查询实时新闻、事实、人物、产品等不确定的信息；"
        "拿到结果后可以用 web_fetch 打开链接阅读全文。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，尽量具体，例如「2026 年诺贝尔物理学奖」",
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，1-10，默认 5",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, config: Config) -> None:
        self._providers = build_providers(
            config.search_backend, config.searxng_url, config.request_timeout
        )

    def run(self, query: str, max_results: int = 5, **_: Any) -> ToolResult:
        query = str(query).strip()
        if not query:
            return ToolResult(False, "错误：query 不能为空。", "参数无效")
        try:
            limit = int(max_results)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 10))

        errors: list[str] = []
        for provider in self._providers:
            try:
                results = provider.search(query, limit)
            except SearchError as exc:
                errors.append(f"- {provider.name}：{exc}")
                continue
            if not results:
                errors.append(f"- {provider.name}：没有找到结果")
                continue

            payload = {
                "query": query,
                "provider": provider.name,
                "results": [
                    {"title": item.title, "url": item.url, "snippet": item.snippet}
                    for item in results
                ],
            }
            summary = f"{provider.name} 找到 {len(results)} 条结果"
            return ToolResult(
                True, json.dumps(payload, ensure_ascii=False, indent=2), summary
            )

        detail = "\n".join(errors) if errors else "- 没有可用的搜索源"
        return ToolResult(
            False,
            "搜索失败，所有搜索源均不可用：\n"
            f"{detail}\n"
            "可以稍后重试，或直接把已知 URL 交给我用 web_fetch 抓取。",
            "搜索失败",
        )
