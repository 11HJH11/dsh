"""极简 HTML → 纯文本转换，供 web_fetch 和搜索结果解析使用。"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "footer",
    "aside",
    "form",
    "select",
    "button",
}

_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "header",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "table",
    "tr",
    "blockquote",
    "pre",
    "figure",
    "figcaption",
    "dd",
    "dt",
    "hr",
}

_SPACE_RE = re.compile(r"[ \t 　]+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._pre_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            return
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "pre":
            self._pre_depth += 1
        if tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_depth:
            return
        text = data if self._pre_depth else _SPACE_RE.sub(" ", data)
        if text:
            self.parts.append(text)


def _normalize(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def extract_text(html: str) -> tuple[str, str]:
    """返回 (页面标题, 正文纯文本)。解析失败时尽量保留已解析内容。"""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    title = _normalize(" ".join(parser.title_parts))
    body = _normalize("".join(parser.parts))
    return title, body


def strip_tags(fragment: str) -> str:
    """把一小段 HTML 压成单行纯文本，适合提取标题和摘要。"""
    _, text = extract_text(fragment)
    return re.sub(r"\s+", " ", text).strip()
