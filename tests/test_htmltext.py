from __future__ import annotations

from dsh.htmltext import extract_text, strip_tags


def test_extract_title_and_body():
    html = """
    <!doctype html>
    <html>
      <head>
        <title>示例 &amp; 标题</title>
        <style>body { color: red; }</style>
        <script>alert("SHOULD_NOT_APPEAR")</script>
      </head>
      <body>
        <nav>导航 SHOULD_NOT_APPEAR</nav>
        <h1>你好世界</h1>
        <p>第一段<strong>正文</strong>。</p>
        <ul><li>要点一</li><li>要点二</li></ul>
        <footer>页脚 SHOULD_NOT_APPEAR</footer>
      </body>
    </html>
    """
    title, text = extract_text(html)
    assert title == "示例 & 标题"
    assert "你好世界" in text
    assert "第一段正文。" in text
    assert "- 要点一" in text
    assert "SHOULD_NOT_APPEAR" not in text
    assert "color: red" not in text


def test_entities_and_line_breaks():
    title, text = extract_text("<title>T</title><p>a&lt;b &amp; c</p><p>下一行<br>换行</p>")
    assert title == "T"
    assert "a<b & c" in text
    assert "下一行" in text
    assert "换行" in text


def test_empty_html():
    assert extract_text("") == ("", "")


def test_strip_tags_collapses_whitespace():
    fragment = "<b>标题</b>\n<span>摘要</span><p>第二段</p>"
    assert strip_tags(fragment) == "标题 摘要 第二段"
