"""工具基类与注册表。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolResult:
    ok: bool
    content: str
    summary: str


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    def run(self, **kwargs: Any) -> ToolResult: ...

    def schema(self) -> dict[str, Any]: ...


class FunctionTool:
    """OpenAI function-calling 风格的工具基类。"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments_json: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            available = "、".join(self._tools) or "（空）"
            return ToolResult(
                False,
                f"错误：不存在名为 {name} 的工具。可用工具：{available}。",
                "未知工具",
            )

        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return ToolResult(False, f"错误：工具参数不是合法 JSON（{exc}）。", "参数解析失败")
        if not isinstance(arguments, dict):
            return ToolResult(False, "错误：工具参数必须是 JSON 对象。", "参数格式错误")

        try:
            return tool.run(**arguments)
        except TypeError as exc:
            return ToolResult(False, f"错误：工具参数不匹配（{exc}）。", "参数不匹配")
        except Exception as exc:
            return ToolResult(
                False,
                f"错误：工具执行失败（{type(exc).__name__}: {exc}）。",
                "执行失败",
            )
