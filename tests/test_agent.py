from __future__ import annotations

from typing import Any

import pytest

from dsh.agent import Agent
from dsh.llm import AssistantMessage, LLMError, ToolCall
from dsh.tools.base import FunctionTool, ToolRegistry, ToolResult


class EchoTool(FunctionTool):
    name = "echo"
    description = "回显输入"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str, **_: Any) -> ToolResult:
        return ToolResult(True, f"echo:{text}", "已回显")


class FakeModel:
    def __init__(self, replies: list[AssistantMessage]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, Any]]] = []

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage:
        self.calls.append(list(messages))
        return self._replies.pop(0)


def test_executes_tool_then_answers():
    model = FakeModel(
        [
            AssistantMessage("", [ToolCall("call_1", "echo", '{"text": "你好"}')]),
            AssistantMessage("最终回答", []),
        ]
    )
    events = []
    agent = Agent(model, ToolRegistry([EchoTool()]), max_steps=4)

    answer = agent.run("测试", on_event=events.append)

    assert answer == "最终回答"
    assert [event.kind for event in events] == ["tool_call", "tool_result"]
    assert events[0].tool_name == "echo"
    assert any(
        message.get("role") == "tool"
        and message.get("tool_call_id") == "call_1"
        and message.get("content") == "echo:你好"
        for message in agent.messages
    )
    assert agent.messages[-1] == {"role": "assistant", "content": "最终回答"}


def test_invalid_arguments_become_tool_error():
    model = FakeModel(
        [
            AssistantMessage("", [ToolCall("call_1", "echo", '{"wrong": 1}')]),
            AssistantMessage("我会调整参数。", []),
        ]
    )
    agent = Agent(model, ToolRegistry([EchoTool()]), max_steps=4)

    assert agent.run("测试") == "我会调整参数。"
    tool_message = next(m for m in agent.messages if m.get("role") == "tool")
    assert "参数不匹配" in tool_message["content"]


def test_unknown_tool_becomes_tool_error():
    model = FakeModel(
        [
            AssistantMessage("", [ToolCall("call_1", "missing", "{}")]),
            AssistantMessage("工具不存在。", []),
        ]
    )
    agent = Agent(model, ToolRegistry([EchoTool()]), max_steps=4)

    agent.run("测试")
    tool_message = next(m for m in agent.messages if m.get("role") == "tool")
    assert "不存在名为 missing 的工具" in tool_message["content"]


def test_stops_at_max_steps():
    model = FakeModel(
        [AssistantMessage("", [ToolCall(f"call_{i}", "echo", '{"text": "x"}')]) for i in range(2)]
    )
    agent = Agent(model, ToolRegistry([EchoTool()]), max_steps=2)

    answer = agent.run("循环")

    assert "最大工具调用轮数（2）" in answer
    assert len(model.calls) == 2


def test_rolls_back_on_llm_error():
    class FailingModel:
        def complete(self, messages, tools):
            raise LLMError("boom")

    agent = Agent(FailingModel(), ToolRegistry([EchoTool()]))
    with pytest.raises(LLMError, match="boom"):
        agent.run("你好")
    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "system"


def test_reset_keeps_system_prompt():
    agent = Agent(FakeModel([]), ToolRegistry([EchoTool()]))
    agent.messages.append({"role": "user", "content": "旧消息"})
    agent.reset()
    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "system"
