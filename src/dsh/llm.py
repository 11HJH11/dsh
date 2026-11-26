"""把 OpenAI 兼容接口的返回值转换成 Agent 内部使用的数据结构。

Agent 只依赖 ChatModel 协议，便于在测试中替换成假模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Config


class LLMError(RuntimeError):
    """调用大模型失败。"""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class AssistantMessage:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage: ...


class OpenAIChatModel:
    """DeepSeek / OpenAI / 其他 OpenAI 兼容服务的统一适配器。"""

    def __init__(self, config: Config) -> None:
        self._model = config.model
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 正常安装后不会触发
            raise LLMError("缺少 openai 依赖，请先执行 pip install -e .") from exc
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.request_timeout,
        )

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as exc:
            raise LLMError(_friendly_error(exc)) from exc

        if not response.choices:
            raise LLMError("模型服务返回了空结果，请稍后再试。")
        message = response.choices[0].message
        calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments or "{}",
            )
            for call in (message.tool_calls or [])
        ]
        return AssistantMessage(content=message.content or "", tool_calls=calls)


def _friendly_error(exc: Exception) -> str:
    try:
        import openai
    except ImportError:  # pragma: no cover
        openai = None  # type: ignore[assignment]

    if openai is not None:
        if isinstance(exc, openai.AuthenticationError):
            return "API Key 无效或已过期（401），请检查 .env 中的 DSH_API_KEY。"
        if isinstance(exc, openai.RateLimitError):
            return "请求过于频繁或账户余额不足（429），请稍后再试。"
        if isinstance(exc, openai.APIConnectionError):
            return f"无法连接模型服务：{exc}"
        if isinstance(exc, openai.APIStatusError):
            return f"模型服务返回 HTTP {exc.status_code}：{exc}"
    return f"调用模型失败（{type(exc).__name__}）：{exc}"
