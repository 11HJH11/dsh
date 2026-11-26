"""命令行入口：交互式聊天与一次性提问。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace

from . import __version__
from .agent import Agent, AgentEvent
from .config import Config, ConfigError, load_dotenv
from .llm import LLMError, OpenAIChatModel
from .tools.base import ToolRegistry
from .tools.web_fetch import WebFetchTool
from .tools.web_search import WebSearchTool
from .ui import Style, make_style

HELP_TEXT = """可用命令：
  /help   显示本帮助
  /tools  查看已加载的工具
  /new    清空上下文，开始新对话
  /quit   退出（也可按 Ctrl+C）
"""


def _banner(config: Config, style: Style) -> None:
    print(style.bold(f"dsh {__version__}") + style.dim(" · 最小形态命令行 Agent"))
    print(style.dim(f"模型 {config.model} @ {config.base_url}"))
    print(style.dim(f"搜索源 {config.search_backend} · 工具 web_search / web_fetch"))
    print(style.dim("输入 /help 查看命令，/quit 退出"))
    print()


def _print_event(event: AgentEvent, style: Style) -> None:
    if event.kind == "tool_call":
        arguments = " ".join(event.arguments.split())
        if len(arguments) > 100:
            arguments = arguments[:97] + "..."
        print(
            style.dim("  ▸ ")
            + style.cyan(event.tool_name)
            + style.dim(f"({arguments})")
        )
    else:
        mark = style.green("✓") if event.ok else style.red("✗")
        print("    " + mark + " " + style.dim(event.summary))


def ask_once(agent: Agent, prompt: str, style: Style) -> int:
    try:
        answer = agent.run(prompt, on_event=lambda event: _print_event(event, style))
    except KeyboardInterrupt:
        print(style.yellow("\n已取消。"))
        return 130
    except LLMError as exc:
        print(style.red(f"模型调用失败：{exc}"), file=sys.stderr)
        return 1
    print(answer)
    return 0


def chat_loop(agent: Agent, config: Config, style: Style) -> int:
    _banner(config, style)
    while True:
        try:
            raw = input(style.cyan("› "))
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        user_text = raw.strip().lstrip("\ufeff").strip()
        if not user_text:
            continue

        if user_text.startswith("/"):
            command = user_text.lower()
            if command in {"/quit", "/exit", "/q"}:
                return 0
            if command == "/help":
                print(HELP_TEXT)
            elif command == "/tools":
                print("已加载工具：")
                for schema in agent.tool_schemas():
                    function = schema["function"]
                    print(f"  - {function['name']}：{function['description']}")
            elif command in {"/new", "/reset"}:
                agent.reset()
                print(style.dim("已清空上下文，开始新对话。"))
            else:
                print(style.yellow(f"未知命令 {user_text}，输入 /help 查看帮助。"))
            continue

        try:
            answer = agent.run(
                user_text, on_event=lambda event: _print_event(event, style)
            )
        except KeyboardInterrupt:
            print(style.yellow("\n已取消当前请求。"))
            continue
        except LLMError as exc:
            print(style.red(f"模型调用失败：{exc}"))
            continue

        print()
        print(answer)
        print()


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="dsh",
        description="dsh —— 最小形态的命令行 Web Agent（web_search + web_fetch）",
    )
    parser.add_argument("-p", "--prompt", help="一次性提问后退出，不进入交互模式")
    parser.add_argument("--model", help="覆盖 DSH_MODEL 指定的模型")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    parser.add_argument("--version", action="version", version=f"dsh {__version__}")
    args = parser.parse_args(argv)

    style = make_style(no_color=args.no_color)
    load_dotenv()

    try:
        config = Config.from_env()
        if args.model:
            config = replace(config, model=args.model)
        model = OpenAIChatModel(config)
        search_tool = WebSearchTool(config)
        fetch_tool = WebFetchTool(config)
    except ConfigError as exc:
        print(style.red(f"配置错误：{exc}"), file=sys.stderr)
        return 2
    except LLMError as exc:
        print(style.red(str(exc)), file=sys.stderr)
        return 2

    registry = ToolRegistry([search_tool, fetch_tool])
    agent = Agent(model, registry, max_steps=config.max_steps)

    try:
        if args.prompt is not None:
            prompt = args.prompt.strip()
            if not prompt:
                print(style.red("错误：-p/--prompt 不能为空。"), file=sys.stderr)
                return 2
            return ask_once(agent, prompt, style)
        return chat_loop(agent, config, style)
    finally:
        fetch_tool.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
