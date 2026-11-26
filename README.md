# dsh

**最小形态的命令行 Web Agent。** 一个模型、两个联网工具、一条清晰可读的 Agent 循环。

`dsh` 从零实现了 Agent 最核心的三件事——**大模型调用、工具调用协议、对话循环**，并内置真实可用的 `web_search`（联网搜索）与 `web_fetch`（网页抓取）工具。它没有依赖 LangChain 等 Agent 框架，Agent 循环、工具注册表、HTML 正文解析均为独立实现，代码量小，适合阅读、演示和二次开发。

## 功能

- 命令行交互式聊天，提供 `/help`、`/tools`、`/new`、`/quit` 命令
- 支持一次性提问：`dsh -p "问题"`
- `web_search`：Bing / DuckDuckGo / SearXNG 三种搜索源，失败自动回退
- `web_fetch`：抓取网页并提取正文，识别 charset、跟随并校验重定向、限制下载大小
- 兼容任何 OpenAI 风格接口，默认接入 DeepSeek
- 多轮工具调用，带最大轮数保护和 Ctrl+C 回滚，不会留下残缺对话
- 纯标准库实现 HTML 解析，运行期只依赖 `openai` 与 `httpx`
- 31 个完全离线的测试（Mock 网络），GitHub Actions 自动跑 lint + test


## 效果示例

```text
$ dsh
dsh 0.1.0 · 最小形态命令行 Agent
模型 deepseek-chat @ https://api.deepseek.com
搜索源 auto · 工具 web_search / web_fetch
输入 /help 查看命令，/quit 退出

› 查一下 DeepSeek 官网最近发布了什么模型，给我官方链接
  ▸ web_search({"query": "DeepSeek 官网 最新模型 发布"})
    ✓ Bing 找到 5 条结果
  ▸ web_fetch({"url": "https://www.deepseek.com/..."})
    ✓ HTTP 200 · 9321 字符 · www.deepseek.com

根据 DeepSeek 官网的介绍……（最终回答与引用略）
```

> 以上为输出示意，实际结果取决于模型与当时的网络内容。

## 快速开始

要求：Python 3.10+，可访问模型服务与搜索网站。

### Windows（PowerShell）

```powershell
git clone https://github.com/11HJH11/dsh.git dsh
cd dsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env   # 填入 DSH_API_KEY
dsh
```

如果 PowerShell 禁止执行激活脚本，可以跳过激活，直接使用虚拟环境里的解释器：

```powershell
.\.venv\Scripts\python.exe -m dsh
```

### macOS / Linux

```bash
git clone https://github.com/11HJH11/dsh.git dsh
cd dsh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
$EDITOR .env   # 填入 DSH_API_KEY
dsh
```

### 获取 API Key

默认配置使用 [DeepSeek 开放平台](https://platform.deepseek.com/) 的接口：注册后创建 API Key，写入 `.env`：

```dotenv
DSH_API_KEY=sk-你的密钥
```

任何 OpenAI 兼容服务都可以使用，只需同时修改：

```dotenv
DSH_BASE_URL=https://你的服务地址/v1
DSH_MODEL=服务支持的模型名
DSH_API_KEY=对应的密钥
```

## 命令行用法

```text
dsh                         进入交互式聊天
dsh -p "用一句话介绍你自己"   一次性提问后退出
dsh --model deepseek-chat   临时覆盖模型
dsh --no-color              禁用彩色输出
dsh --version               查看版本
```

交互模式内置命令：

| 命令 | 作用 |
| --- | --- |
| `/help` | 显示帮助 |
| `/tools` | 查看已加载的工具及其说明 |
| `/new` | 清空上下文，开始新对话 |
| `/quit` | 退出（`Ctrl+C` 也可以） |

`Ctrl+C` 会取消当前请求并回滚这一轮的上下文，不会污染下一轮对话。

## 配置项

配置从环境变量读取；如果存在 `.env`，会从当前目录向上最多查找 5 层并加载最近的一个（已存在的环境变量优先）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DSH_API_KEY` | 必填 | 模型服务密钥；也兼容 `DEEPSEEK_API_KEY` |
| `DSH_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口地址 |
| `DSH_MODEL` | `deepseek-chat` | 模型名 |
| `DSH_SEARCH_BACKEND` | `auto` | `auto` / `bing` / `ddg` / `searxng` |
| `DSH_SEARXNG_URL` | 无 | 自建 SearXNG 地址，`searxng` 模式必填 |
| `DSH_MAX_STEPS` | `8` | 单轮对话最多调用模型的次数 |
| `DSH_TIMEOUT` | `30` | 单次 HTTP 请求超时（秒） |
| `DSH_MAX_FETCH_CHARS` | `12000` | `web_fetch` 返回正文的默认上限（500–50000） |
| `DSH_MAX_DOWNLOAD_BYTES` | `2000000` | `web_fetch` 单次下载字节上限 |
| `DSH_ALLOW_PRIVATE_NETWORK` | `0` | 设为 `1` 后允许抓取 localhost/内网（仅在本地调试时使用） |

`auto` 搜索模式按 **SearXNG（若已配置）→ Bing → DuckDuckGo** 依次尝试；某一个源超时或解析失败时会自动换下一个。

## 工具

### `web_search`

输入搜索词，返回 JSON：查询词、实际使用的搜索源，以及若干条 `title / url / snippet`。适合查询实时信息或需要核实的事实。

- Bing：解析 `b_algo` 结果块，并还原 `bing.com/ck/a` 跳转链接
- DuckDuckGo：解析 HTML 版结果页，并还原 `uddg=` 跳转链接
- SearXNG：调用实例的 JSON 接口，需要实例开启 `format=json`

### `web_fetch`

输入一个 URL，抓取网页并转换为纯文本，输出标题、最终 URL、HTTP 状态和正文。为避免误用和危险请求，内置了以下边界：

- 只允许 `http` / `https`，拒绝 `file:`、`javascript:` 等协议
- 拒绝解析到环回、内网、链路本地等非公网地址，且**每一次重定向都会重新校验**
- 手动跟随最多 5 次重定向，防止跳转到内网绕过检查
- 下载大小上限，解析前按 `charset` 或 `<meta charset>` 解码，缺失时依次尝试 UTF-8、GB18030
- 只处理文本/HTML/JSON/XML；二进制内容直接报错
- 返回正文按字符数截断，并明确标注截断信息

## 架构

```text
                 ┌──────────────────────────────────────────────┐
   用户输入 ───▶ │  cli.py：REPL / 一次性提问 / 事件展示          │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  agent.py：消息历史 + 工具调用循环            │
                 │  模型返回 tool_calls → 执行工具 → 回填结果     │
                 │  直到模型给出最终文本，或达到 max_steps        │
                 └───────────┬──────────────────────┬───────────┘
                             │                      │
                             ▼                      ▼
                 ┌────────────────────┐  ┌────────────────────────┐
                 │ llm.py             │  │ tools/base.py          │
                 │ OpenAI 兼容适配器   │  │ FunctionTool + 注册表   │
                 └─────────┬──────────┘  └───────────┬────────────┘
                           │                         │
                           ▼                         ▼
                    模型服务（默认 DeepSeek）    web_search / web_fetch
                                                     │
                                      ┌──────────────┴──────────────┐
                                      ▼                             ▼
                              search.py 多源搜索            htmltext.py HTML→文本
                              Bing / DDG / SearXNG          net.py URL 安全校验
```

一次完整的 Agent 步骤如下：

1. `cli.py` 把用户输入交给 `agent.py`，追加到消息历史；
2. `agent.py` 把「系统提示 + 历史 + 工具 schema」发给模型；
3. 如果模型返回 `tool_calls`，注册表执行对应工具，并把工具结果作为 `role="tool"` 消息追加；
4. 回到第 2 步，直到模型不再调用工具并输出最终回答；
5. 若达到 `DSH_MAX_STEPS`，停止并提示用户；若用户取消或模型报错，回滚整轮消息。

### 项目结构

```text
dsh/
├── pyproject.toml
├── .env.example
├── .github/workflows/ci.yml
├── src/dsh/
│   ├── cli.py            # 命令行入口与终端事件展示
│   ├── agent.py          # 最小 Agent 循环
│   ├── llm.py            # ChatModel 协议与 OpenAI 兼容实现
│   ├── config.py          # .env / 环境变量配置
│   ├── search.py          # 搜索源、结果解析、URL 还原
│   ├── htmltext.py        # 标准库 HTML → 纯文本
│   ├── net.py             # 请求头、URL 规范化、内网拦截
│   ├── ui.py              # 终端颜色
│   └── tools/
│       ├── base.py        # FunctionTool / ToolResult / 注册表
│       ├── web_search.py  # web_search 工具
│       └── web_fetch.py   # web_fetch 工具
└── tests/                 # 全部离线，无需 API Key 与网络
```

## 设计说明

**为什么不用 Agent 框架？** 这个项目的目标是理解 Agent 的最小构成，而不是堆叠依赖。工具调用协议直接使用 OpenAI function calling；循环、注册表、错误回填都在百行以内，读一遍就能掌握 Agent 的骨架。

**工具错误不会中断会话。** 参数 JSON 解析失败、工具名不存在、参数签名不匹配、工具内部异常，都会被注册表捕获为一条 `role="tool"` 的错误消息交给模型，让模型有机会自行纠正。

**搜索源可插拔。** 每个 provider 只负责「查询 → `SearchResult` 列表」，解析失败抛出 `SearchError`；`WebSearchTool` 负责按顺序回退，并把最终结果序列化为 JSON。想接入新的搜索 API，只需新增一个类。

**HTML 解析不依赖 BeautifulSoup。** 基于标准库 `html.parser` 实现了一个容错的正文抽取器：跳过脚本、样式、导航、页脚等噪音，保留标题、段落、列表结构；解析异常时保留已解析内容。搜索结果的标题/摘要也复用它。

**测试不依赖外网。** 模型通过 `ChatModel` 协议注入假实现；HTTP 抓取通过 `httpx.MockTransport` 模拟，覆盖重定向、私网拦截、GBK 编码、下载截断等分支；搜索解析使用固定 HTML 片段。CI 中没有真实网络请求。

## 开发与测试

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
```

- 测试：31 个用例，覆盖配置、HTML 解析、搜索解析、抓取安全边界和 Agent 循环
- CI：`.github/workflows/ci.yml` 在 Python 3.10 / 3.12 上执行 `ruff check` 与 `pytest`

## 常见问题

**`dsh` 提示“不是内部或外部命令”**
确认虚拟环境已激活；或直接运行 `python -m dsh` / `.\.venv\Scripts\python.exe -m dsh`。

**401 / 余额不足**
检查 `.env` 中的密钥是否有效。401 通常是密钥错误，429 通常是频率限制或余额不足。

**搜索总是超时**
当前网络可能无法访问默认搜索源。可尝试 `DSH_SEARCH_BACKEND=bing`；若所在网络需要代理，`httpx` 会自动读取 `HTTPS_PROXY` / `HTTP_PROXY` 环境变量。也可以配置自建 SearXNG。

**提示模型不存在（model not found）**
不同账号可用的模型名可能不同。DeepSeek 官方公开接口通常使用 `deepseek-chat` / `deepseek-reasoner`；部分账号提供 `deepseek-flash`、`deepseek-v4-pro`。以服务端 `/v1/models` 返回为准，并通过 `DSH_MODEL` 指定。

**抓取某些网页没有正文**
`web_fetch` 只获取服务器返回的 HTML，不执行 JavaScript。SPA 或需要登录的页面可能得到空内容。

**Windows 终端显示乱码或颜色异常**
建议使用 Windows Terminal / PowerShell 7；也可以用 `dsh --no-color` 关闭 ANSI 颜色。

## 已知限制

- 不执行 JavaScript，不处理 PDF、图片等非文本内容
- 搜索解析依赖 Bing/DuckDuckGo 的 HTML 结构，页面改版可能导致解析失败（可切换到 SearXNG）
- 上下文只保存在内存中，退出后不保留；长对话需要手动 `/new`
- 内网拦截基于请求时的 DNS 解析，未完整防御 DNS rebinding；面向本地个人使用而非多租户服务

## 隐私与安全

- 密钥只从环境变量 / 本地 `.env` 读取，`.env` 已被 `.gitignore` 忽略
- 对话内容与抓取到的网页正文会发送给所配置的模型服务
- `web_fetch` 的 URL 校验、重定向校验与大小限制，用于降低 SSRF 和资源滥用风险

## License

[MIT](LICENSE)
