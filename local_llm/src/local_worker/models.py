"""Core data models for the local worker scheduler."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkerClass(str, Enum):
    cheap = "cheap"
    smart = "smart"


class JobStatus(str, Enum):
    queued              = "queued"
    running             = "running"
    completed           = "completed"
    cancelled           = "cancelled"
    context_exhausted   = "context_exhausted"
    capability_mismatch = "capability_mismatch"
    model_error         = "model_error"
    tool_error          = "tool_error"
    resource_error      = "resource_error"


class SchedulerMode(str, Enum):
    idle              = "idle"
    cheap_loading     = "cheap_loading"
    cheap_ready       = "cheap_ready"
    draining          = "draining"
    smart_loading     = "smart_loading"
    smart_ready       = "smart_ready"
    smart_unloading   = "smart_unloading"
    cheap_reloading   = "cheap_reloading"


def new_job_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobSubmission(BaseModel):
    """Input schema for worker_submit MCP tool."""
    worker_class: WorkerClass
    prompt: str = Field(..., description="The task prompt for the worker")
    system_prompt: str | None = Field(None, description="Optional system prompt override")
    priority: int = Field(5, ge=1, le=10, description="Job priority (1=highest, 10=lowest)")
    max_output_tokens: int | None = Field(None, description="Override profile default")
    timeout_seconds: float | None = Field(None, description="Override profile default timeout")
    context_hint: str | None = Field(None, description="Short label for logs/observability")


class Job(BaseModel):
    """Full job record — stored in SQLite and returned via MCP."""
    job_id: str = Field(default_factory=new_job_id)
    worker_class: WorkerClass
    status: JobStatus = JobStatus.queued
    priority: int = 5
    system_prompt: str | None = None
    user_prompt: str
    context_hint: str | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None

    # Set by scheduler when dispatched
    model_used: str | None = None

    # Timestamps
    queued_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Token stats (from LM Studio response)
    input_tokens: int | None = None
    output_tokens: int | None = None
    was_batched: bool = False

    # Result payload
    result_text: str | None = None
    finish_reason: str | None = None        # "stop" | "length" | "error" | "timeout"
    handoff_summary: str | None = None      # compact summary on context_exhausted
    error_message: str | None = None

    def to_mcp_dict(self) -> dict[str, Any]:
        """Serialize for MCP response (ISO timestamps, no None noise)."""
        d = self.model_dump()
        for k in ("queued_at", "started_at", "completed_at"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return {k: v for k, v in d.items() if v is not None or k in (
            "result_text", "error_message", "handoff_summary", "started_at", "completed_at"
        )}


class SchedulerStatus(BaseModel):
    """Returned by scheduler_status MCP tool."""
    mode: SchedulerMode
    loaded_model: str | None
    lm_studio_reachable: bool
    queue: dict[str, int]           # {"cheap": N, "smart": N}
    running_jobs: int
    vram_free_mb: int | None
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    uptime_seconds: float
    last_resource_error: str | None = None
    resource_diagnostics: dict[str, Any] | None = None
    is_leader: bool = True
    active_pid: int | None = None
