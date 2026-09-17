"""Unit and integration tests for PulpieService."""

import pytest
from pulpie_service.config import PulpieConfig
from pulpie_service.extractor import PulpieService, CleanResult


def test_service_initialization():
    cfg = PulpieConfig(model_name="orange-small", fallback_enabled=True)
    svc = PulpieService(cfg)
    status = svc.status()
    assert status["service"] == "pulpie-preprocessing"
    assert status["model_configured"] == "orange-small"
    assert status["fallback_enabled"] is True


def test_clean_html_empty():
    svc = PulpieService()
    res = svc.clean_html("")
    assert isinstance(res, CleanResult)
    assert res.content == ""
    assert res.char_count_in == 0
    assert res.char_count_out == 0


def test_clean_html_title_extraction():
    svc = PulpieService()
    html = "<html><head><title>My Special Page</title></head><body><p>Hello world</p></body></html>"
    res = svc.clean_html(html)
    assert res.title == "My Special Page"


def test_clean_html_with_fallback_mode():
    # Force model load failure by pointing to non-existent model name
    cfg = PulpieConfig(model_name="nonexistent-dummy-model-test", fallback_enabled=True)
    svc = PulpieService(cfg)
    html = """
    <html>
      <head><title>Fallback Test</title></head>
      <body>
        <nav>Nav link 1 | Nav link 2</nav>
        <main>
          <h1>Main Article</h1>
          <p>This content must be recovered via fallback.</p>
        </main>
        <footer>Footer noise</footer>
      </body>
    </html>
    """
    res = svc.clean_html(html)
    assert res.used_fallback is True
    assert "model_unavailable" in (res.fallback_reason or "")
    assert "Main Article" in res.content
    assert res.char_count_out > 0
    assert res.token_savings_pct >= 0


def test_clean_html_without_fallback_mode():
    # When fallback is disabled and model fails, returns raw HTML and error
    cfg = PulpieConfig(model_name="nonexistent-dummy-model-test", fallback_enabled=False)
    svc = PulpieService(cfg)
    html = "<html><body><p>Direct error test</p></body></html>"
    res = svc.clean_html(html, fallback=False)
    assert res.used_fallback is False
    assert res.error is not None
    assert res.content == html


def test_clean_result_to_dict():
    res = CleanResult(
        content="# Hello World",
        format="markdown",
        title="Greeting",
        n_blocks=5,
        n_main=3,
        n_other=2,
        char_count_in=100,
        char_count_out=15,
        compression_ratio=0.15,
        token_estimate_in=25,
        token_estimate_out=4,
        token_savings_pct=84.0,
        latency_ms=12.5,
    )
    d = res.to_dict()
    assert d["title"] == "Greeting"
    assert d["format"] == "markdown"
    assert d["content"] == "# Hello World"
    assert d["stats"]["blocks_total"] == 5
    assert d["stats"]["token_savings_pct"] == 84.0
    assert d["stats"]["compression_ratio"] == 0.15
