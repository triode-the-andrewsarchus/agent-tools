"""Core Pulpie content extraction service."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from .config import PulpieConfig
from .fallback import extract_fallback

log = logging.getLogger(__name__)


@dataclass
class CleanResult:
    """Structured extraction result."""

    content: str
    format: str = "markdown"  # "markdown" or "html"
    title: Optional[str] = None
    n_blocks: int = 0
    n_main: int = 0
    n_other: int = 0
    char_count_in: int = 0
    char_count_out: int = 0
    compression_ratio: float = 1.0  # char_count_out / char_count_in
    token_estimate_in: int = 0
    token_estimate_out: int = 0
    token_savings_pct: float = 0.0
    used_fallback: bool = False
    fallback_reason: Optional[str] = None
    fallback_method: Optional[str] = None
    model_used: Optional[str] = None
    device: Optional[str] = None
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for MCP tools or JSON APIs."""
        return {
            "title": self.title,
            "format": self.format,
            "content": self.content,
            "stats": {
                "blocks_total": self.n_blocks,
                "blocks_main": self.n_main,
                "blocks_other": self.n_other,
                "char_count_in": self.char_count_in,
                "char_count_out": self.char_count_out,
                "compression_ratio": round(self.compression_ratio, 4),
                "token_estimate_in": self.token_estimate_in,
                "token_estimate_out": self.token_estimate_out,
                "token_savings_pct": round(self.token_savings_pct, 2),
                "latency_ms": round(self.latency_ms, 2),
            },
            "status": {
                "used_fallback": self.used_fallback,
                "fallback_reason": self.fallback_reason,
                "fallback_method": self.fallback_method,
                "model_used": self.model_used,
                "device": self.device,
                "error": self.error,
            },
        }


class PulpieService:
    """Singleton/service wrapper managing the Pulpie model lifecycle and extractions."""

    def __init__(self, config: Optional[PulpieConfig] = None):
        self.config = config or PulpieConfig.from_env()
        self._extractor: Any = None
        self._device: Optional[str] = None
        self._model_loaded: bool = False
        self._load_error: Optional[str] = None

    def _detect_device(self) -> str:
        """Resolve device preference."""
        if self.config.device != "auto":
            return self.config.device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def ensure_loaded(self) -> bool:
        """Load the Pulpie model into memory if not already loaded."""
        if self._model_loaded and self._extractor is not None:
            return True

        target_device = self._detect_device()
        log.info("Loading Pulpie model '%s' on %s...", self.config.model_name, target_device)

        try:
            from pulpie import Extractor

            # Attempt load on preferred device
            try:
                self._extractor = Extractor(
                    model=self.config.model_name,
                    device=target_device,
                    max_tokens=self.config.max_tokens,
                    max_batch_tokens=self.config.max_batch_tokens,
                )
                self._device = target_device
                self._model_loaded = True
                self._load_error = None
                log.info("Pulpie model successfully loaded on %s", target_device)
                return True
            except Exception as e:
                # If CUDA OOM, attempt CPU fallback
                if target_device == "cuda" and ("out of memory" in str(e).lower() or "cuda" in str(e).lower()):
                    log.warning("CUDA load failed (%s), retrying on CPU...", e)
                    self._extractor = Extractor(
                        model=self.config.model_name,
                        device="cpu",
                        max_tokens=self.config.max_tokens,
                        max_batch_tokens=self.config.max_batch_tokens,
                    )
                    self._device = "cpu"
                    self._model_loaded = True
                    self._load_error = None
                    return True
                raise e

        except Exception as e:
            self._load_error = str(e)
            self._model_loaded = False
            self._extractor = None
            log.error("Failed to load Pulpie model: %s", e)
            return False

    def _extract_title(self, html: str) -> Optional[str]:
        """Extract title from HTML if present."""
        try:
            soup = BeautifulSoup(html[:10000], "html.parser")
            if soup.title and soup.title.string:
                return soup.title.string.strip()
            h1 = soup.find("h1")
            if h1 and h1.text:
                return h1.text.strip()
        except Exception:
            pass
        return None

    def clean_html(
        self,
        html: str,
        output_format: str = "markdown",
        fallback: bool = True,
    ) -> CleanResult:
        """Extract main content from raw HTML.

        Args:
            html: Raw HTML string.
            output_format: "markdown" (default) or "html".
            fallback: Whether to use fallback heuristic if Pulpie is unavailable or fails.

        Returns:
            CleanResult with extracted content and execution metadata.
        """
        start_time = time.perf_counter()
        char_in = len(html) if html else 0
        tokens_in = max(1, char_in // 4) if char_in > 0 else 0
        title = self._extract_title(html) if html else None

        if not html or not html.strip():
            return CleanResult(
                content="",
                format=output_format,
                title=title,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        # 1. Try Pulpie model extraction
        model_ready = self.ensure_loaded()
        if model_ready and self._extractor is not None:
            try:
                res = self._extractor.extract(html)
                content = res.markdown if output_format == "markdown" else res.html

                # Suspiciously empty / all-pruned check:
                # If output is completely empty, or if HTML was substantial but output was pruned to almost nothing
                content_stripped = content.strip()
                is_empty = len(content_stripped) == 0
                is_suspiciously_sparse = char_in > 300 and len(content_stripped) < 30
                if (is_empty or is_suspiciously_sparse) and fallback and self.config.fallback_enabled:
                    log.warning("Pulpie produced empty or sparse extraction (%d chars from %d input), trying fallback",
                                len(content_stripped), char_in)
                    fb = extract_fallback(html, target_format=output_format, reason="empty_or_sparse_pulpie_output")
                    if fb.success and len(fb.content.strip()) > len(content_stripped):
                        char_out = len(fb.content)
                        tokens_out = max(1, char_out // 4)
                        savings = max(0.0, (1.0 - (tokens_out / tokens_in)) * 100) if tokens_in else 0.0
                        return CleanResult(
                            content=fb.content,
                            format=output_format,
                            title=title,
                            n_blocks=res.n_blocks,
                            n_main=res.n_main,
                            n_other=res.n_other,
                            char_count_in=char_in,
                            char_count_out=char_out,
                            compression_ratio=char_out / max(1, char_in),
                            token_estimate_in=tokens_in,
                            token_estimate_out=tokens_out,
                            token_savings_pct=savings,
                            used_fallback=True,
                            fallback_reason="empty_or_sparse_pulpie_output",
                            fallback_method=fb.method,
                            model_used=self.config.model_name,
                            device=self._device,
                            latency_ms=(time.perf_counter() - start_time) * 1000,
                        )

                char_out = len(content)
                tokens_out = max(1, char_out // 4)
                savings = max(0.0, (1.0 - (tokens_out / tokens_in)) * 100) if tokens_in else 0.0

                return CleanResult(
                    content=content,
                    format=output_format,
                    title=title,
                    n_blocks=res.n_blocks,
                    n_main=res.n_main,
                    n_other=res.n_other,
                    char_count_in=char_in,
                    char_count_out=char_out,
                    compression_ratio=char_out / max(1, char_in),
                    token_estimate_in=tokens_in,
                    token_estimate_out=tokens_out,
                    token_savings_pct=savings,
                    used_fallback=False,
                    model_used=self.config.model_name,
                    device=self._device,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )
            except Exception as e:
                log.warning("Pulpie extraction error: %s", e)
                if not fallback or not self.config.fallback_enabled:
                    return CleanResult(
                        content=html,
                        format=output_format,
                        title=title,
                        char_count_in=char_in,
                        char_count_out=char_in,
                        used_fallback=False,
                        error=f"Pulpie extraction error: {e}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                    )
                fallback_reason = f"inference_error: {e}"
        else:
            fallback_reason = f"model_unavailable: {self._load_error or 'unknown'}"
            if not fallback or not self.config.fallback_enabled:
                return CleanResult(
                    content=html,
                    format=output_format,
                    title=title,
                    char_count_in=char_in,
                    char_count_out=char_in,
                    used_fallback=False,
                    error=fallback_reason,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

        # 2. Execute Fallback
        fb = extract_fallback(html, target_format=output_format, reason=fallback_reason)
        char_out = len(fb.content)
        tokens_out = max(1, char_out // 4)
        savings = max(0.0, (1.0 - (tokens_out / tokens_in)) * 100) if tokens_in else 0.0

        return CleanResult(
            content=fb.content,
            format=output_format,
            title=title,
            char_count_in=char_in,
            char_count_out=char_out,
            compression_ratio=char_out / max(1, char_in),
            token_estimate_in=tokens_in,
            token_estimate_out=tokens_out,
            token_savings_pct=savings,
            used_fallback=True,
            fallback_reason=fallback_reason,
            fallback_method=fb.method,
            device=self._device,
            latency_ms=(time.perf_counter() - start_time) * 1000,
        )

    async def clean_web_page(
        self,
        url: str,
        output_format: str = "markdown",
        fallback: bool = True,
        timeout: Optional[float] = None,
    ) -> CleanResult:
        """Fetch URL and clean the resulting HTML content."""
        timeout_val = timeout or self.config.http_timeout
        headers = {"User-Agent": self.config.user_agent}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_val)) as resp:
                    if resp.status >= 400:
                        return CleanResult(
                            content="",
                            format=output_format,
                            error=f"HTTP {resp.status} fetching {url}",
                        )
                    raw_html = await resp.text()
        except Exception as e:
            return CleanResult(
                content="",
                format=output_format,
                error=f"Failed to fetch {url}: {e}",
            )

        res = self.clean_html(raw_html, output_format=output_format, fallback=fallback)
        return res

    def status(self) -> dict[str, Any]:
        """Return diagnostic health and status info."""
        info: dict[str, Any] = {
            "service": "pulpie-preprocessing",
            "model_configured": self.config.model_name,
            "model_loaded": self._model_loaded,
            "device": self._device,
            "fallback_enabled": self.config.fallback_enabled,
            "error": self._load_error,
        }

        try:
            import torch
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["vram_allocated_mb"] = round(torch.cuda.memory_allocated(0) / (1024 * 1024), 2)
                info["vram_reserved_mb"] = round(torch.cuda.memory_reserved(0) / (1024 * 1024), 2)
        except ImportError:
            info["cuda_available"] = False

        return info

    def preload(self) -> dict[str, Any]:
        """Explicitly load model into memory."""
        success = self.ensure_loaded()
        st = self.status()
        st["preload_success"] = success
        return st
