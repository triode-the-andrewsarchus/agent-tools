"""Pulpie web content extraction and preprocessing service for Antigravity."""

from .config import PulpieConfig
from .extractor import CleanResult, PulpieService
from .fallback import FallbackResult, extract_fallback

__version__ = "0.1.0"
__all__ = [
    "CleanResult",
    "FallbackResult",
    "PulpieConfig",
    "PulpieService",
    "extract_fallback",
]
