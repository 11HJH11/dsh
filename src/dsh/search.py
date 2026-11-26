"""搜索源实现：DuckDuckGo HTML、Bing HTML、SearXNG JSON。

只使用公开的 HTML/JSON 页面，不依赖任何付费搜索 API。
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

import httpx

from .htmltext import strip_tags
from .net import DEFAULT_HEADERS


class SearchError(RuntimeError):
    """单个搜索源请求或解析失败。"""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"""
)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_H2_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2\s*>", re.IGNORECASE | re.DOTALL)
_P_RE = re.compile(r"<p\b([^>]*)>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)
_ELEMENT_RE = re.compile(r"<(a|div|span)\b([^>]*)>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL)

_DDG_BLOCK_RE = re.compile(
    r'<div\b(?=[^>]*\bclass\s*=\s*"[^"]*\bresult\b[^"]*")[^>]*>', re.IGNORECASE
)
_BING_BLOCK_RE = re.compile(
    r'<li\b(?=[^>]*\bclass\s*=\s*"[^"]*\bb_algo\b[^"]*")[^>]*>', re.IGNORECASE
)


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name, double_quoted, single_quoted, bare in _ATTR_RE.findall(raw):
        value = double_quoted or single_quoted or bare
        attrs.setdefault(name.lower(), unescape(value))
    return attrs


def _find_anchor_by_class(fragment: str, class_name: str) -> tuple[str, str] | None:
    for match in _ANCHOR_RE.finditer(fragment):
        attrs = _parse_attrs(match.group(1))
        if class_name in attrs.get("class", "").split():
            return attrs.get("href", ""), match.group(2)
    return None


def _find_class_text(fragment: str, class_name: str) -> str:
    for match in _ELEMENT_RE.finditer(fragment):
        attrs = _parse_attrs(match.group(2))
        if class_name in attrs.get("class", "").split():
            text = strip_tags(match.group(3))
            if text:
                return text
    return ""


def _clean_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", strip_tags(fragment)).strip()


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for result in results:
        key = result.url.rstrip("/")
        if key and key not in seen:
            seen.add(key)
            unique.append(result)
    return unique


def _resolve_ddg_url(href: str) -> str:
    href = unescape(href).strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/l/"):
        href = "https://duckduckgo.com" + href

    parts = urlsplit(href)
    if parts.netloc.endswith("duckduckgo.com") and parts.path.startswith("/l/"):
        target = parse_qs(parts.query).get("uddg", [""])[0]
        if target:
            href = target
            parts = urlsplit(href)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return href


def _resolve_bing_url(href: str) -> str:
    href = unescape(href).strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href

    parts = urlsplit(href)
    if parts.netloc.endswith("bing.com") and parts.path.startswith("/ck/a"):
        wrapped = parse_qs(parts.query).get("u", [""])[0]
        if wrapped.startswith("a1"):
            encoded = wrapped[2:]
            padding = "=" * (-len(encoded) % 4)
            try:
                decoded = base64.urlsafe_b64decode(encoded + padding).decode(
                    "utf-8", "replace"
                )
            except Exception:
                decoded = ""
            if decoded.startswith(("http://", "https://")):
                href = decoded
                parts = urlsplit(href)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return href


def parse_ddg_html(html: str) -> list[SearchResult]:
    starts = [match.start() for match in _DDG_BLOCK_RE.finditer(html)]
    results: list[SearchResult] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(html)
        chunk = html[start:end]

        anchor = _find_anchor_by_class(chunk, "result__a")
        if anchor is None:
            continue
        href, title_html = anchor
        url = _resolve_ddg_url(href)
        title = _clean_text(title_html)
        if not url or not title:
            continue

        snippet = ""
        snippet_anchor = _find_anchor_by_class(chunk, "result__snippet")
        if snippet_anchor is not None:
            snippet = _clean_text(snippet_anchor[1])
        if not snippet:
            snippet = _find_class_text(chunk, "result__snippet")
        results.append(SearchResult(title=title, url=url, snippet=snippet))

    return _dedupe(results)


def parse_bing_html(html: str) -> list[SearchResult]:
    starts = [match.start() for match in _BING_BLOCK_RE.finditer(html)]
    results: list[SearchResult] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(html)
        chunk = html[start:end]

        block = _H2_RE.search(chunk)
        title_area = block.group(1) if block else chunk
        anchor = None
        for match in _ANCHOR_RE.finditer(title_area):
            attrs = _parse_attrs(match.group(1))
            href = attrs.get("href", "")
            title = _clean_text(match.group(2))
            if href and title:
                anchor = (href, match.group(2))
                break
        if anchor is None:
            continue

        url = _resolve_bing_url(anchor[0])
        title = _clean_text(anchor[1])
        if not url or not title:
            continue

        paragraphs = [
            _clean_text(inner) for _, inner in _P_RE.findall(chunk)
        ]
        paragraphs = [text for text in paragraphs if text]
        snippet = max(paragraphs, key=len) if paragraphs else ""
        results.append(SearchResult(title=title, url=url, snippet=snippet))

    return _dedupe(results)


class DuckDuckGoProvider:
    name = "DuckDuckGo"
    endpoint = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            response = httpx.get(
                self.endpoint,
                params={"q": query, "kl": "cn-zh"},
                headers=DEFAULT_HEADERS,
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"请求失败：{exc}") from exc
        results = parse_ddg_html(response.text)
        if not results:
            raise SearchError("没有解析到结果（可能被风控或网络受限）")
        return results[:max_results]


class BingProvider:
    name = "Bing"
    endpoint = "https://www.bing.com/search"

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            response = httpx.get(
                self.endpoint,
                params={"q": query, "setlang": "zh-hans", "count": str(max_results)},
                headers=DEFAULT_HEADERS,
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"请求失败：{exc}") from exc
        results = parse_bing_html(response.text)
        if not results:
            raise SearchError("没有解析到结果（页面结构可能变化）")
        return results[:max_results]


class SearXNGProvider:
    name = "SearXNG"

    def __init__(self, base_url: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            response = httpx.get(
                f"{self._base_url}/search",
                params={"q": query, "format": "json"},
                headers={**DEFAULT_HEADERS, "Accept": "application/json"},
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise SearchError(f"请求失败：{exc}") from exc

        results: list[SearchResult] = []
        for item in payload.get("results", []):
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("content", "")).strip()
            if url.startswith(("http://", "https://")) and title:
                results.append(SearchResult(title=title, url=url, snippet=snippet))
        if not results:
            raise SearchError("没有返回结果")
        return _dedupe(results)[:max_results]


def build_providers(
    backend: str, searxng_url: str | None, timeout: float
) -> list[SearchProvider]:
    providers: list[SearchProvider] = []
    if backend in {"auto", "searxng"} and searxng_url:
        providers.append(SearXNGProvider(searxng_url, timeout))
    if backend in {"auto", "bing"}:
        providers.append(BingProvider(timeout))
    if backend in {"auto", "ddg"}:
        providers.append(DuckDuckGoProvider(timeout))
    return providers
