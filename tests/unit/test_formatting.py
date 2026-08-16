"""Unit tests for ui.formatting.markdown_to_html -- pure string transform,
no Qt widgets involved (DiffHighlighter, which needs a QTextDocument, is
covered under tests/ui instead)."""

from ui.formatting import markdown_to_html


def test_empty_input_returns_empty_string():
    assert markdown_to_html("") == ""
    assert markdown_to_html(None) == ""


def test_headers_are_converted():
    html = markdown_to_html("# Title\n## Subtitle")
    assert "<h1>Title</h1>" in html
    assert "<h2>Subtitle</h2>" in html


def test_bold_and_italic():
    html = markdown_to_html("**bold** and *italic*")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_inline_code_is_wrapped():
    html = markdown_to_html("Use `foo()` here.")
    assert "<code" in html
    assert "foo()" in html


def test_code_block_is_preserved_and_escaped():
    html = markdown_to_html("```python\n<b>not html</b>\n```")
    assert "<pre" in html
    assert "&lt;b&gt;not html&lt;/b&gt;" in html


def test_link_is_converted_to_anchor():
    html = markdown_to_html("[Ollama](http://localhost:11434)")
    assert '<a href="http://localhost:11434"' in html
    assert ">Ollama</a>" in html


def test_unordered_list_items():
    html = markdown_to_html("- one\n- two")
    assert "<ul>" in html
    assert "<li>one</li>" in html
    assert "<li>two</li>" in html
