from __future__ import annotations

import base64

from dsh.search import parse_bing_html, parse_ddg_html

DDG_HTML = """
<html><body>
  <div class="result results_links results_links_deep web-result">
    <div class="result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1%26y%3D2&amp;rut=abc">
          Example <b>A</b>
        </a>
      </h2>
      <a class="result__snippet" href="https://example.com/a">这是<b>摘要</b> A。</a>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result">
    <div class="result__body">
      <h2 class="result__title">
        <a class="result__a" href="https://example.com/a?x=1&amp;y=2">重复结果</a>
      </h2>
      <div class="result__snippet">重复的摘要。</div>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result">
    <div class="result__body">
      <h2 class="result__title">
        <a class="result__a" href="https://example.org/b">Example B</a>
      </h2>
      <a class="result__snippet" href="https://example.org/b">第二个摘要。</a>
    </div>
  </div>
</body></html>
"""


def test_parse_ddg_html():
    results = parse_ddg_html(DDG_HTML)
    assert len(results) == 2
    first, second = results
    assert first.title == "Example A"
    assert first.url == "https://example.com/a?x=1&y=2"
    assert "摘要" in first.snippet
    assert second.url == "https://example.org/b"


def test_parse_ddg_skips_bad_links():
    html = (
        '<div class="result results_links">'
        '<a class="result__a" href="javascript:alert(1)">X</a></div>'
    )
    assert parse_ddg_html(html) == []


def test_parse_bing_html():
    wrapped = base64.urlsafe_b64encode(b"https://example.org/bg").decode().rstrip("=")
    html = f"""
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://www.bing.com/ck/a?!&&p=1&u=a1{wrapped}&ntb=1">
          示例 <strong>标题</strong>
        </a></h2>
        <div class="b_caption"><p class="b_lineclamp2">这是 <b>Bing</b> 摘要。</p></div>
      </li>
      <li class="b_algo">
        <h2><a href="https://example.net/page">第二条</a></h2>
        <p>第二段摘要，内容也足够长。</p>
      </li>
    </ol>
    """
    results = parse_bing_html(html)
    assert len(results) == 2
    first, second = results
    assert first.title == "示例 标题"
    assert first.url == "https://example.org/bg"
    assert first.snippet == "这是 Bing 摘要。"
    assert second.url == "https://example.net/page"
    assert "第二段摘要" in second.snippet


def test_parse_empty_pages():
    assert parse_ddg_html("") == []
    assert parse_bing_html("") == []
