"""Graceful fallback content extractors when Pulpie model is unavailable or fails."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class FallbackResult:
    """Result of fallback extraction."""

    content: str
    format: str  # "markdown" or "html"
    method: str  # "trafilatura", "readability", "soup_html2text", "raw_stripped"
    success: bool
    reason: Optional[str] = None


def extract_fallback(html: str, target_format: str = "markdown", reason: str = "model_unavailable") -> FallbackResult:
    """Extract content using heuristic methods when Pulpie cannot be used.

    Order of attempts:
      1. Trafilatura (preserves tables, links, headings)
      2. BeautifulSoup + html2text (strip scripts, styles, nav, footer, ads)
      3. Naive tag stripping / raw text
    """
    if not html or not html.strip():
        return FallbackResult(
            content="",
            format=target_format,
            method="empty_input",
            success=True,
            reason=reason,
        )

    # 1. Try Trafilatura
    try:
        import trafilatura

        trafilatura_output = trafilatura.extract(
            html,
            output_format="markdown" if target_format == "markdown" else "xml",
            include_tables=True,
            include_links=True,
            include_images=False,
            include_formatting=True,
        )
        if trafilatura_output and len(trafilatura_output.strip()) > 50:
            return FallbackResult(
                content=trafilatura_output.strip(),
                format=target_format,
                method="trafilatura",
                success=True,
                reason=reason,
            )
    except Exception as e:
        log.warning("Trafilatura fallback failed: %s", e)

    # 2. Try BeautifulSoup + html2text
    try:
        from bs4 import BeautifulSoup
        import html2text

        soup = BeautifulSoup(html, "lxml")
        # Remove noisy elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg"]):
            tag.decompose()

        body = soup.body or soup
        body_html = str(body)

        if target_format == "markdown":
            h = html2text.HTML2Text(bodywidth=0)
            h.ignore_links = False
            h.ignore_images = True
            text = h.handle(body_html).strip()
        else:
            text = body_html

        if text and len(text.strip()) > 20:
            return FallbackResult(
                content=text,
                format=target_format,
                method="soup_html2text",
                success=True,
                reason=reason,
            )
    except Exception as e:
        log.warning("BeautifulSoup fallback failed: %s", e)

    # 3. Last-ditch: simple regex tag stripping so we never return empty text
    clean_text = re.sub(r"<[^>]+>", " ", html)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return FallbackResult(
        content=clean_text[:50000],
        format="markdown",
        method="raw_stripped",
        success=bool(clean_text),
        reason=reason,
    )
