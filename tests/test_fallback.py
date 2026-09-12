"""Tests for graceful fallback mechanisms."""

import pytest
from pulpie_service.fallback import extract_fallback, FallbackResult


def test_fallback_empty_html():
    res = extract_fallback("", target_format="markdown")
    assert isinstance(res, FallbackResult)
    assert res.content == ""
    assert res.success is True


def test_fallback_whitespace():
    res = extract_fallback("   \n\t  ", target_format="markdown")
    assert res.content == ""
    assert res.success is True


def test_fallback_removes_scripts_and_styles():
    raw_html = """
    <html>
      <head><style>.ad { color: red; }</style></head>
      <body>
        <script>alert('noise');</script>
        <nav><a href="#">Navigation</a></nav>
        <main>
          <h1>Actual Article Content</h1>
          <p>This is meaningful paragraph text that must survive fallback extraction.</p>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    res = extract_fallback(raw_html, target_format="markdown")
    assert res.success is True
    assert "alert('noise')" not in res.content
    assert ".ad { color: red; }" not in res.content
    assert "Actual Article Content" in res.content
    assert "meaningful paragraph text" in res.content


def test_fallback_preserves_tables_and_code():
    raw_html = """
    <html>
      <body>
        <h1>Code & Table Test</h1>
        <pre><code>def compute(x): return x * 42</code></pre>
        <table>
          <tr><th>Col A</th><th>Col B</th></tr>
          <tr><td>Val 1</td><td>Val 2</td></tr>
        </table>
      </body>
    </html>
    """
    res = extract_fallback(raw_html, target_format="markdown")
    assert res.success is True
    assert "compute" in res.content
    assert "Col A" in res.content
    assert "Val 1" in res.content


def test_fallback_malformed_html():
    raw_html = "<div><p>Unclosed paragraph <span>with text table <tr><td>Cell 1<td>Cell 2"
    res = extract_fallback(raw_html, target_format="markdown")
    assert res.success is True
    assert "Unclosed paragraph" in res.content
    assert "Cell 1" in res.content
