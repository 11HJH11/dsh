"""最小 Agent 循环：模型 → 工具 → 模型 → …… → 最终回答。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .llm import AssistantMessage, ChatModel, LLMError
from .tools.base import ToolRegistry

SYSTEM_PROMPT = """你是 dsh，一个运行在命令行里的最小形态 Agent。

你拥有两个工具：
- web_search：搜索互联网，得到标题、链接和摘要；
- web_fetch：抓取网页并提取正文。

工作原则：
1. 遇到实时信息、事实核查、你不确定或无法凭记忆回答的问题，先搜索再作答。
2. 搜索结果不够时，主动打开高相关链接阅读全文；可以多次调用工具。
3. 引用网页信息时给出 Markdown 链接，不要编造来源。
4. 工具失败时如实说明，并尝试更换搜索词或来源。
5. 用用户使用的语言回答，简洁、直接、有条理。"""


@dataclass
class AgentEvent:
    kind: str  # "tool_call" | "tool_result"
    tool_name: str
    arguments: str = ""
    summary: str = ""
    ok: bool = True


EventHandler = Callable[[AgentEvent], None]


class Agent:
    def __init__(
        self, model: ChatModel, registry: ToolRegistry, max_steps: int = 8
    ) -> None:
        self._model = model
        self._registry = registry
        self._max_steps = max_steps
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def reset(self) -> None:
        del self.messages[1:]

    def tool_schemas(self) -> list[dict[str, Any]]:
        return self._registry.schemas()

    def run(self, user_text: str, on_event: EventHandler | None = None) -> str:
        start = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        try:
            return self._loop(on_event)
        except (KeyboardInterrupt, LLMError):
            # 中断或模型报错时回滚整轮，避免留下不完整的历史
            del self.messages[start:]
            raise

    def _loop(self, on_event: EventHandler | None) -> str:
        for _ in range(self._max_steps):
            reply = self._model.complete(self.messages, self._registry.schemas())
            if not reply.tool_calls:
                content = (reply.content or "").strip() or "（模型未返回文本内容）"
                self.messages.append({"role": "assistant", "content": content})
                return content

            self.messages.append(_assistant_record(reply))
            for call in reply.tool_calls:
                if on_event is not None:
                    on_event(AgentEvent("tool_call", call.name, call.arguments))
                result = self._registry.execute(call.name, call.arguments)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result.content,
                    }
                )
                if on_event is not None:
                    on_event(
                        AgentEvent(
                            "tool_result",
                            call.name,
                            summary=result.summary,
                            ok=result.ok,
                        )
                    )

        message = (
            f"已达到最大工具调用轮数（{self._max_steps}），本轮停止。"
            "你可以继续追问，或输入 /new 重开对话。"
        )
        self.messages.append({"role": "assistant", "content": message})
        return message


def _assistant_record(reply: AssistantMessage) -> dict[str, Any]:
    record: dict[str, Any] = {"role": "assistant", "content": reply.content or ""}
    if reply.tool_calls:
        record["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in reply.tool_calls
        ]
    return record
