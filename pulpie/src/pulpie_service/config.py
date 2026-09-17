"""Configuration for the Pulpie preprocessing service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PulpieConfig:
    """Settings for Pulpie extraction service."""

    model_name: str = "orange-small"
    device: str = "auto"
    fallback_enabled: bool = True
    max_tokens: int = 8192
    max_batch_tokens: int = 16384
    http_timeout: float = 15.0
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Antigravity-Pulpie/0.1"
    )

    @classmethod
    def from_env(cls) -> PulpieConfig:
        """Construct config overriding defaults with environment variables."""
        return cls(
            model_name=os.getenv("PULPIE_MODEL", "orange-small"),
            device=os.getenv("PULPIE_DEVICE", "auto"),
            fallback_enabled=os.getenv("PULPIE_FALLBACK", "true").lower() in ("1", "true", "yes"),
            max_tokens=int(os.getenv("PULPIE_MAX_TOKENS", "8192")),
            max_batch_tokens=int(os.getenv("PULPIE_MAX_BATCH_TOKENS", "16384")),
            http_timeout=float(os.getenv("PULPIE_HTTP_TIMEOUT", "15.0")),
            user_agent=os.getenv("PULPIE_USER_AGENT", cls.user_agent),
        )
