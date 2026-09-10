"""
MCP server for the local worker scheduler.

Uses MCP Python SDK v2.x (MCPServer / FastMCP renamed API).

Exposes 5 tools:
  worker_submit      — Submit a job, returns job_id immediately
  worker_status      — Get status/result for one job
  worker_cancel      — Cancel a queued or running job
  worker_list        — List recent jobs (filterable)
  scheduler_status   — Current mode, queue depth, VRAM, uptime
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Annotated, Any, Optional

from mcp.server.mcpserver import MCPServer

from .config import load_config
from .db import JobStore
from .lms_client import LMSClient
from .models import Job, JobStatus, JobSubmission, WorkerClass
from .scheduler import Scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# Global singletons — initialized in async_main before server starts
_scheduler: Scheduler | None = None
_store: JobStore | None = None


def _fmt(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def _make_mcp() -> MCPServer:
    mcp = MCPServer(
        name="local-worker",
        version="0.1.0",
        instructions=(
            "Local LLM worker pool. Use worker_submit to delegate tasks to local models, "
            "worker_status to retrieve results, and scheduler_status to check availability. "
            "Worker classes: 'cheap' (Qwen3.5-9B, parallel) or 'smart' (Qwen3.6-27B, high quality)."
        ),
    )

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="worker_submit",
        description=(
            "Submit a task to a local LLM worker. Returns a job_id immediately — "
            "use worker_status to poll for the result. "
            "Use worker_class='cheap' for fast/parallel tasks (Qwen3.5-9B, batches up to 2 concurrent); "
            "use 'smart' for complex reasoning (Qwen3.6-27B, sequential). "
            "The scheduler manages GPU allocation and model switching automatically. "
            "Do NOT specify a model name or GPU — use worker_class only."
        ),
    )
    async def worker_submit(
        worker_class: Annotated[str, "Worker capability class: 'cheap' or 'smart'"],
        prompt: Annotated[str, "The task prompt for the worker"],
        system_prompt: Annotated[Optional[str], "Optional system prompt"] = None,
        priority: Annotated[int, "Job priority 1-10 (1=highest). Default 5"] = 5,
        max_output_tokens: Annotated[Optional[int], "Override profile default max output tokens"] = None,
        timeout_seconds: Annotated[Optional[float], "Override profile default timeout in seconds"] = None,
        context_hint: Annotated[Optional[str], "Short label for logs/observability"] = None,
    ) -> str:
        try:
            wclass = WorkerClass(worker_class)
        except ValueError:
            return _fmt({"error": f"Invalid worker_class '{worker_class}'. Must be 'cheap' or 'smart'."})

        job = Job(
            worker_class=wclass,
            priority=max(1, min(10, priority)),
            system_prompt=system_prompt,
            user_prompt=prompt,
            context_hint=context_hint,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        job = await _scheduler.submit(job)
        return _fmt({
            "job_id": job.job_id,
            "status": job.status.value,
            "worker_class": job.worker_class.value,
            "queued_at": job.queued_at.isoformat(),
            "message": (
                "Job queued. Use worker_status(job_id=...) to poll for results."
                if job.status == JobStatus.queued
                else f"Job not queued: {job.error_message}"
            ),
        })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="worker_status",
        description=(
            "Get the current status and result of a submitted job. "
            "Poll until status is not 'queued' or 'running'. "
            "On 'context_exhausted', check handoff_summary for compact findings. "
            "On 'completed', check result_text."
        ),
    )
    async def worker_status(
        job_id: Annotated[str, "Job ID returned by worker_submit"],
    ) -> str:
        job = await _store.get_job(job_id)
        if not job:
            return _fmt({"error": f"Job '{job_id}' not found"})
        return _fmt(job.to_mcp_dict())

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="worker_cancel",
        description="Cancel a queued or running job by job_id.",
    )
    async def worker_cancel(
        job_id: Annotated[str, "Job ID to cancel"],
    ) -> str:
        found = await _scheduler.cancel(job_id)
        return _fmt({
            "job_id": job_id,
            "found": found,
            "message": "Cancellation requested." if found else "Job not found.",
        })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="worker_list",
        description=(
            "List recent jobs with optional filters. "
            "Use to inspect what is queued, running, or recently completed."
        ),
    )
    async def worker_list(
        status: Annotated[Optional[str], "Filter by status (e.g. 'queued', 'completed', 'running')"] = None,
        worker_class: Annotated[Optional[str], "Filter by class ('cheap' or 'smart')"] = None,
        limit: Annotated[int, "Max number of jobs to return"] = 20,
    ) -> str:
        status_filter = JobStatus(status) if status else None
        class_filter = WorkerClass(worker_class) if worker_class else None
        jobs = await _store.list_jobs(
            status=status_filter,
            worker_class=class_filter,
            limit=limit,
        )
        return _fmt({
            "count": len(jobs),
            "jobs": [
                {
                    "job_id": j.job_id,
                    "worker_class": j.worker_class.value,
                    "status": j.status.value,
                    "priority": j.priority,
                    "context_hint": j.context_hint,
                    "queued_at": j.queued_at.isoformat(),
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                    "model_used": j.model_used,
                    "was_batched": j.was_batched,
                    "input_tokens": j.input_tokens,
                    "output_tokens": j.output_tokens,
                }
                for j in jobs
            ],
        })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="scheduler_status",
        description=(
            "Get the current scheduler state: mode (idle/cheap_ready/smart_ready/etc.), "
            "loaded model, queue depths, running job count, free VRAM MB, and uptime. "
            "Check lm_studio_reachable before submitting important jobs."
        ),
    )
    async def scheduler_status() -> str:
        status = await _scheduler.get_status()
        return _fmt(status)

    return mcp


async def async_main() -> None:
    global _scheduler, _store

    cfg = load_config()
    log.info("Starting local-worker MCP server")
    log.info("LM Studio URL: %s", cfg.lms_base_url)
    log.info("DB: %s", cfg.db_path)
    log.info("Profiles: cheap=%s ctx=%d par=%d | smart=%s ctx=%d par=%d",
             cfg.cheap.lms_model_key, cfg.cheap.context_length, cfg.cheap.parallel,
             cfg.smart.lms_model_key, cfg.smart.context_length, cfg.smart.parallel)

    # Open DB
    _store = JobStore(cfg.db_path)
    await _store.open()
    await _store.prune_old_jobs(cfg.scheduler.job_retention_days)

    # LM Studio client
    client = LMSClient(cfg.lms_base_url, cfg.lms_cli)
    await client.start()

    # Scheduler
    _scheduler = Scheduler(cfg, _store, client)
    sched_task = asyncio.create_task(_scheduler.run(), name="scheduler")

    # MCP server (blocks until stdio closes)
    mcp = _make_mcp()
    try:
        await mcp.run_stdio_async()
    finally:
        log.info("MCP stdio closed, shutting down...")
        _scheduler.request_shutdown()
        try:
            await asyncio.wait_for(sched_task, timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            log.warning("Scheduler did not shut down cleanly in 15s")
        await client.stop()
        await _store.close()
        log.info("Shutdown complete")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
