from __future__ import annotations

from contextlib import contextmanager

import httpx

from dsh.config import Config
from dsh.tools.web_fetch import WebFetchTool


def make_config(**overrides) -> Config:
    values = {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "max_steps": 4,
        "request_timeout": 5.0,
        "search_backend": "auto",
        "searxng_url": None,
        "allow_private_network": False,
        "max_fetch_chars": 12000,
        "max_download_bytes": 2_000_000,
    }
    values.update(overrides)
    return Config(**values)


@contextmanager
def make_tool(handler, **overrides):
    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    tool = WebFetchTool(make_config(**overrides), client=client)
    try:
        yield tool
    finally:
        tool.close()


def test_fetches_html_and_follows_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>最终页</title></head><body>"
                "<script>SHOULD_NOT_APPEAR()</script>"
                "<h1>你好</h1><p>正文内容。</p></body></html>"
            ),
        )

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/start")

    assert result.ok
    assert "标题：最终页" in result.content
    assert "URL：https://example.com/final" in result.content
    assert "你好" in result.content
    assert "SHOULD_NOT_APPEAR" not in result.content


def test_blocks_private_addresses():
    tool = WebFetchTool(make_config())
    try:
        result = tool.run("http://127.0.0.1:8080/admin")
    finally:
        tool.close()
    assert not result.ok
    assert "禁止访问非公网地址" in result.content


def test_redirect_to_private_address_is_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/start")

    assert not result.ok
    assert "禁止访问非公网地址" in result.content


def test_rejects_non_http_scheme():
    tool = WebFetchTool(make_config())
    try:
        result = tool.run("ftp://example.com/file.txt")
    finally:
        tool.close()
    assert not result.ok
    assert "只支持 http/https" in result.content


def test_unsupported_content_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/image.png")

    assert not result.ok
    assert "不支持的内容类型" in result.content


def test_json_is_pretty_printed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            text='{"a":1,"cn":"中文"}',
        )

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/data.json")

    assert result.ok
    assert '"a": 1' in result.content
    assert '"cn": "中文"' in result.content


def test_truncates_text_to_max_chars():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=f"<html><body><p>{'长' * 2000}</p></body></html>",
        )

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/long", max_chars=500)

    assert result.ok
    assert "仅显示前 500 字符" in result.content
    assert "已截断" in result.summary


def test_gbk_meta_charset():
    body = (
        "<html><head><meta charset='gbk'><title>中文页面</title></head>"
        "<body>你好，世界</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=body.encode("gbk")
        )

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/gbk")

    assert result.ok
    assert "标题：中文页面" in result.content
    assert "你好，世界" in result.content


def test_download_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=utf-8"},
            text="A" * 1000,
        )

    with make_tool(handler, max_download_bytes=100) as tool:
        result = tool.run("https://example.com/large.txt")

    assert result.ok
    assert "下载：已截断" in result.content


def test_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with make_tool(handler) as tool:
        result = tool.run("https://example.com/missing")

    assert not result.ok
    assert "HTTP 404" in result.content
