"""HTTP 公共工具：请求头、URL 规范化、内网地址拦截。"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class UnsafeURLError(ValueError):
    """URL 指向本机或内网，出于安全考虑拒绝访问。"""


def normalize_url(raw: str) -> str:
    url = str(raw).strip()
    if not url:
        raise ValueError("URL 不能为空")
    if len(url) > 2000:
        raise ValueError("URL 过长（超过 2000 字符）")
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url

    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UnsafeURLError("只支持 http/https 链接")
    if not parts.hostname:
        raise ValueError("URL 缺少主机名")
    return url


def assert_public_url(url: str) -> None:
    """解析域名并拒绝环回、内网、链路本地等非公网地址。"""
    host = urlsplit(url).hostname or ""
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeURLError("出于安全考虑，禁止访问本机地址")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # 解析失败时交给 HTTP 客户端给出具体错误
        return

    for info in infos:
        address = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not ip.is_global:
            raise UnsafeURLError(f"出于安全考虑，禁止访问非公网地址（{host} → {address}）")


def build_client(timeout: float) -> httpx.Client:
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
    )
