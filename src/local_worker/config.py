"""Load and expose worker profile configuration from worker_profiles.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkerProfile:
    worker_class: str
    lms_model_key: str
    context_length: int
    parallel: int
    gpu_offload: str
    max_output_tokens: int
    default_timeout: float


@dataclass
class SchedulerConfig:
    cheap_drain_window: float
    health_check_interval: float
    job_retention_days: int


@dataclass
class AppConfig:
    cheap: WorkerProfile
    smart: WorkerProfile
    scheduler: SchedulerConfig
    lms_base_url: str
    lms_cli: str
    db_path: Path


_DEFAULT_PROFILES_PATH = Path(__file__).parent.parent.parent / "worker_profiles.toml"


def load_config() -> AppConfig:
    profiles_path = Path(
        os.environ.get("LOCAL_WORKER_PROFILES", str(_DEFAULT_PROFILES_PATH))
    )
    with open(profiles_path, "rb") as f:
        raw = tomllib.load(f)

    def make_profile(cls: str, d: dict) -> WorkerProfile:
        return WorkerProfile(
            worker_class=cls,
            lms_model_key=d["lms_model_key"],
            context_length=d["context_length"],
            parallel=d["parallel"],
            gpu_offload=d["gpu_offload"],
            max_output_tokens=d["max_output_tokens"],
            default_timeout=float(d["default_timeout"]),
        )

    sched = raw.get("scheduler", {})
    db_default = Path.home() / ".local" / "share" / "local-worker" / "jobs.db"

    return AppConfig(
        cheap=make_profile("cheap", raw["worker"]["cheap"]),
        smart=make_profile("smart", raw["worker"]["smart"]),
        scheduler=SchedulerConfig(
            cheap_drain_window=float(sched.get("cheap_drain_window", 5.0)),
            health_check_interval=float(sched.get("health_check_interval", 30.0)),
            job_retention_days=int(sched.get("job_retention_days", 7)),
        ),
        lms_base_url=os.environ.get("LMS_BASE_URL", "http://localhost:1234"),
        lms_cli=os.environ.get("LMS_CLI", str(Path.home() / ".lmstudio" / "bin" / "lms")),
        db_path=Path(os.environ.get("LOCAL_WORKER_DB", str(db_default))),
    )
