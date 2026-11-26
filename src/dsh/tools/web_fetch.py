"""web_fetch 工具：抓取网页并提取可读正文。"""

from __future__ import annotations

import codecs
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from ..config import Config
from ..htmltext import extract_text
from ..net import DEFAULT_HEADERS, UnsafeURLError, assert_public_url, normalize_url
from .base import FunctionTool, ToolResult

_MAX_REDIRECTS = 5
_META_CHARSET_RE = re.compile(rb"<meta[^>]*charset\s*=\s*[\"']?([\w-]+)", re.IGNORECASE)


class FetchError(RuntimeError):
    pass


@dataclass
class FetchedPage:
    status_code: int
    headers: httpx.Headers
    url: httpx.URL
    content: bytes
    download_truncated: bool


class WebFetchTool(FunctionTool):
    name = "web_fetch"
    description = (
        "抓取一个网页并提取其中的可读正文，返回标题、最终 URL 和纯文本内容。"
        "通常先用 web_search 找到链接，再用本工具阅读全文。只支持文本、HTML 和 JSON。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的 http/https URL"},
            "max_chars": {
                "type": "integer",
                "description": "返回正文的最大字符数，默认 12000，范围 500-50000",
                "minimum": 500,
                "maximum": 50000,
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(config.request_timeout),
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def run(self, url: str, max_chars: int | None = None, **_: object) -> ToolResult:
        try:
            target = normalize_url(url)
        except (ValueError, UnsafeURLError) as exc:
            return ToolResult(False, f"错误：{exc}", "URL 无效")

        if max_chars is None:
            limit = self._config.max_fetch_chars
        else:
            try:
                limit = int(max_chars)
            except (TypeError, ValueError):
                limit = self._config.max_fetch_chars
            limit = max(500, min(limit, 50000))

        try:
            page = self._get_with_redirects(target)
        except UnsafeURLError as exc:
            return ToolResult(False, f"错误：{exc}", "已拦截不安全地址")
        except FetchError as exc:
            return ToolResult(False, f"错误：{exc}", "抓取失败")
        except httpx.HTTPError as exc:
            return ToolResult(
                False,
                f"错误：网络请求失败（{type(exc).__name__}: {exc}）。",
                "请求失败",
            )

        if page.status_code >= 400:
            return ToolResult(
                False,
                f"错误：目标网页返回 HTTP {page.status_code}。",
                f"HTTP {page.status_code}",
            )

        content_type_header = page.headers.get("content-type", "")
        content_type = content_type_header.split(";")[0].strip().lower()
        if not _is_supported_type(content_type):
            return ToolResult(
                False,
                f"错误：不支持的内容类型 {content_type or '未知'}，本工具只读取文本/HTML/JSON。",
                "内容类型不支持",
            )

        text = _decode_body(page.content, content_type_header)
        is_json = content_type == "application/json" or content_type.endswith("+json")
        if is_json:
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass

        title = ""
        if not is_json and _is_html(content_type, text):
            title, text = extract_text(text)

        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            return ToolResult(False, "错误：网页没有可提取的文本内容。", "正文为空")

        total = len(text)
        truncated = total > limit
        if truncated:
            text = (
                text[:limit].rstrip()
                + f"\n\n[内容已截断：共 {total} 字符，仅显示前 {limit} 字符]"
            )

        header = (
            f"标题：{title or '（无）'}\n"
            f"URL：{page.url}\n"
            f"HTTP：{page.status_code}\n"
            f"内容类型：{content_type or '未知'}\n"
        )
        if page.download_truncated:
            header += f"下载：已截断，仅读取前 {self._config.max_download_bytes} 字节\n"
        header += "\n"

        host = urlsplit(str(page.url)).hostname or ""
        summary = f"HTTP {page.status_code} · {total} 字符 · {host}"
        if truncated:
            summary += "（已截断）"
        return ToolResult(True, header + text, summary)

    def _get_with_redirects(self, url: str) -> FetchedPage:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            if not self._config.allow_private_network:
                assert_public_url(current)
            with self._client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(
                            f"HTTP {response.status_code} 重定向缺少 Location 头"
                        )
                    current = urljoin(str(response.url), location)
                    continue
                content, truncated = _read_limited(
                    response, self._config.max_download_bytes
                )
                return FetchedPage(
                    status_code=response.status_code,
                    headers=response.headers,
                    url=response.url,
                    content=content,
                    download_truncated=truncated,
                )
        raise FetchError(f"重定向次数超过 {_MAX_REDIRECTS} 次，已停止")


def _read_limited(response: httpx.Response, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        if total + len(chunk) > limit:
            chunks.append(chunk[: limit - total])
            return b"".join(chunks), True
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks), False


def _is_supported_type(content_type: str) -> bool:
    if not content_type:
        return True
    return (
        content_type.startswith("text/")
        or content_type in {"application/xhtml+xml", "application/xml", "application/json"}
        or content_type.endswith(("+json", "+xml"))
    )


def _is_html(content_type: str, text: str) -> bool:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return True
    head = text[:500].lower()
    return "<!doctype html" in head or "<html" in head


def _decode_body(body: bytes, content_type_header: str) -> str:
    declared = _declared_charset(content_type_header, body)
    if declared:
        try:
            return body.decode(declared, errors="replace")
        except LookupError:
            pass
    for encoding in ("utf-8", "gb18030"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _declared_charset(content_type_header: str, body: bytes) -> str | None:
    match = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", content_type_header, re.IGNORECASE)
    if match:
        return match.group(1)
    match = _META_CHARSET_RE.search(body[:4096])
    if match:
        return match.group(1).decode("ascii", "ignore")
    if body.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    return None
