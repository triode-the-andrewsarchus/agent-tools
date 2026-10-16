"""Configuration loader and schema for Architecture Fitness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


DEFAULT_EXCLUDES = [
    ".git/**",
    ".fitness/**",
    ".valknut/**",
    ".jscpd/**",
    "**/.git/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/dist/**",
    "**/build/**",
    "**/target/**",
    "**/.cache/**",
    "**/.next/**",
    "**/.nuxt/**",
    "**/out/**",
    "**/.turbo/**",
    "**/.pytest_cache/**",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.avif",
    "**/*.heic",
    "**/*.ico",
    "**/*.svg",
    "**/*.ttf",
    "**/*.otf",
    "**/*.woff",
    "**/*.woff2",
    "**/*.eot",
    "**/*.mp3",
    "**/*.wav",
    "**/*.ogg",
    "**/*.flac",
    "**/*.mp4",
    "**/*.webm",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.bz2",
    "**/*.7z",
    "**/*.pdf",
    "**/*.so",
    "**/*.dylib",
    "**/*.dll",
    "**/*.exe",
    "**/*.bin",
]


class ThresholdsConfig(BaseModel):
    max_function_ccn: int = 15
    max_duplication_percentage_delta: float = 0.5
    max_complexity_delta: float = 5.0
    max_health_drop: float = 5.0
    fail_on_cycles: bool = True
    new_clone_groups_allowed: int = 0


class FitnessConfig(BaseModel):
    exclude_paths: List[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    languages: List[str] = Field(default_factory=list)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    profile: str = "fast"
    baseline_dir: str = ".fitness/baselines"

    @classmethod
    def load(cls, repo_path: Path | str) -> FitnessConfig:
        root = Path(repo_path).resolve()

        # Check common config locations
        candidates = [
            root / ".fitness.toml",
            root / "fitness.toml",
            root / ".architecture-fitness.json",
            root / ".fitness.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                try:
                    if candidate.suffix == ".json":
                        with open(candidate, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            return cls.model_validate(data)
                    elif candidate.suffix == ".toml":
                        import tomllib
                        with open(candidate, "rb") as f:
                            data = tomllib.load(f)
                            return cls.model_validate(data)
                except Exception:
                    pass  # Fall back to default on error

        return cls()
