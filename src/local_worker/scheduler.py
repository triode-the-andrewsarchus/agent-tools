"""
Async scheduler with mode FSM for cheap/smart GPU switching.

Mode transitions:
  idle → cheap_loading → cheap_ready
  cheap_ready → draining → smart_loading → smart_ready
  smart_ready → smart_unloading → cheap_reloading → cheap_ready
  cheap_ready → idle (on graceful shutdown)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any

from .config import AppConfig, WorkerProfile
from .db import JobStore
from .lms_client import LMSClient
from .models import Job, JobStatus, SchedulerMode, WorkerClass, utcnow

log = logging.getLogger(__name__)


@dataclass(order=True)
class _PrioritizedJob:
    """Wrapper for priority queue — sorted by (priority, queue time)."""
    sort_key: tuple = field(compare=True)
    job: Job = field(compare=False)


class Scheduler:
    """Manages GPU mode and dispatches jobs to LM Studio."""

    def __init__(self, cfg: AppConfig, store: JobStore, client: LMSClient) -> None:
        self._cfg = cfg
        self._store = store
        self._client = client

        # Priority queues, one per worker class
        self._cheap_q: asyncio.PriorityQueue[_PrioritizedJob] = asyncio.PriorityQueue()
        self._smart_q: asyncio.PriorityQueue[_PrioritizedJob] = asyncio.PriorityQueue()

        # In-flight job tracking
        self._running: set[str] = set()          # job_ids currently in inference
        self._cancelled: set[str] = set()         # job_ids cancelled by caller

        # Mode FSM
        self._mode: SchedulerMode = SchedulerMode.idle
        self._loaded_model: str | None = None     # lms identifier currently loaded

        # Observability
        self._start_time = time.monotonic()
        self._lms_reachable = False
        self._vram_free_mb: int | None = None
        self._vram_total_mb: int | None = None
        self._vram_used_mb: int | None = None
        self._last_resource_error: str | None = None
        self._last_resource_diagnostics: dict[str, Any] | None = None

        # Control
        self._shutdown = asyncio.Event()
        self._mode_lock = asyncio.Lock()

    # ──────────────────────────────────────────────
    # Public API (called by MCP server)
    # ──────────────────────────────────────────────

    async def submit(self, job: Job) -> Job:
        """Enqueue a job. Returns the job with status=queued."""
        if not self._lms_reachable:
            job.status = JobStatus.resource_error
            job.error_message = "LM Studio is not reachable at startup. Check that LM Studio is running."
            await self._store.insert_job(job)
            return job

        await self._store.insert_job(job)
        pjob = _PrioritizedJob(
            sort_key=(job.priority, job.queued_at.timestamp()),
            job=job,
        )
        if job.worker_class == WorkerClass.cheap:
            await self._cheap_q.put(pjob)
        else:
            await self._smart_q.put(pjob)

        log.info("Queued %s job %s (priority=%d)", job.worker_class, job.job_id, job.priority)
        return job

    async def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns True if job was found."""
        job = await self._store.get_job(job_id)
        if not job:
            return False
        if job.status in (JobStatus.queued, JobStatus.running):
            self._cancelled.add(job_id)
            if job.status == JobStatus.queued:
                job.status = JobStatus.cancelled
                job.completed_at = utcnow()
                await self._store.update_job(job)
            # Running jobs will be cancelled when their asyncio task checks _cancelled
        return True

    async def get_status(self) -> dict:
        """Return scheduler status dict for MCP."""
        # Refresh VRAM info
        info = await self._client.get_vram_info()
        if info:
            self._vram_total_mb = info.get("total_mb")
            self._vram_used_mb = info.get("used_mb")
            self._vram_free_mb = info.get("free_mb")

        return {
            "mode": self._mode.value,
            "loaded_model": self._loaded_model,
            "lm_studio_reachable": self._lms_reachable,
            "queue": {
                "cheap": self._cheap_q.qsize(),
                "smart": self._smart_q.qsize(),
            },
            "running_jobs": len(self._running),
            "vram_free_mb": self._vram_free_mb,
            "vram_total_mb": self._vram_total_mb,
            "vram_used_mb": self._vram_used_mb,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "last_resource_error": self._last_resource_error,
            "resource_diagnostics": self._last_resource_diagnostics,
        }

    # ──────────────────────────────────────────────
    # Background tasks (started by MCP server)
    # ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main scheduler loop. Run as a background asyncio task."""
        log.info("Scheduler starting")
        self._lms_reachable = await self._client.is_reachable()
        if not self._lms_reachable:
            log.warning("LM Studio not reachable at startup!")

        # Start background tasks
        health_task = asyncio.create_task(self._health_loop(), name="health")
        vram_task   = asyncio.create_task(self._vram_loop(), name="vram")

        try:
            await self._dispatch_loop()
        finally:
            health_task.cancel()
            vram_task.cancel()
            await asyncio.gather(health_task, vram_task, return_exceptions=True)
            await self._graceful_unload()
            log.info("Scheduler stopped")

    def request_shutdown(self) -> None:
        self._shutdown.set()

    # ──────────────────────────────────────────────
    # Dispatch loop
    # ──────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        while not self._shutdown.is_set():
            if not self._lms_reachable:
                await asyncio.sleep(2)
                continue

            has_smart = not self._smart_q.empty()
            has_cheap = not self._cheap_q.empty()

            if has_smart and self._mode in (SchedulerMode.idle, SchedulerMode.cheap_ready):
                # Drain remaining cheap jobs first (batch window)
                if has_cheap:
                    log.info("Smart job pending — draining cheap queue first (window=%.1fs)",
                             self._cfg.scheduler.cheap_drain_window)
                    await self._drain_cheap_with_window()

                # Now switch to smart mode
                try:
                    await self._switch_to_smart()
                except Exception as e:
                    err_msg = str(e)
                    log.error("Failed to switch to smart model: %s", err_msg)
                    self._last_resource_error = err_msg
                    if hasattr(e, "vram_info"):
                        self._last_resource_diagnostics = {
                            "model_key": getattr(e, "model_key", None),
                            "worker_class": getattr(e, "worker_class", None),
                            "vram_info": getattr(e, "vram_info", None),
                            "suggestions": getattr(e, "suggestions", []),
                        }
                    # Mark pending smart jobs as resource_error so they do not hang
                    while not self._smart_q.empty():
                        pjob = await self._smart_q.get()
                        job = pjob.job
                        if not self._is_cancelled(job):
                            job.status = JobStatus.resource_error
                            job.error_message = err_msg
                            job.completed_at = utcnow()
                            await self._store.update_job(job)
                        self._smart_q.task_done()
                    continue

                if not self._smart_q.empty():
                    pjob = await self._smart_q.get()
                    if self._is_cancelled(pjob.job):
                        self._smart_q.task_done()
                        continue
                    await self._run_job(pjob.job, self._cfg.smart)
                    self._smart_q.task_done()

                # Switch back to cheap mode
                try:
                    await self._switch_to_cheap()
                except Exception as e:
                    log.warning("Failed switching back to cheap: %s", e)

            elif has_cheap and self._mode in (SchedulerMode.idle, SchedulerMode.cheap_ready):
                # Ensure cheap model is loaded
                if self._mode == SchedulerMode.idle:
                    try:
                        await self._load_cheap()
                    except Exception as e:
                        err_msg = str(e)
                        log.error("Failed to load cheap model: %s", err_msg)
                        self._last_resource_error = err_msg
                        if hasattr(e, "vram_info"):
                            self._last_resource_diagnostics = {
                                "model_key": getattr(e, "model_key", None),
                                "worker_class": getattr(e, "worker_class", None),
                                "vram_info": getattr(e, "vram_info", None),
                                "suggestions": getattr(e, "suggestions", []),
                            }
                        while not self._cheap_q.empty():
                            pjob = await self._cheap_q.get()
                            job = pjob.job
                            if not self._is_cancelled(job):
                                job.status = JobStatus.resource_error
                                job.error_message = err_msg
                                job.completed_at = utcnow()
                                await self._store.update_job(job)
                            self._cheap_q.task_done()
                        continue

                # Dispatch up to parallel cheap jobs concurrently
                batch = []
                while (
                    not self._cheap_q.empty()
                    and len(batch) < self._cfg.cheap.parallel
                ):
                    pjob = await self._cheap_q.get()
                    if not self._is_cancelled(pjob.job):
                        batch.append(pjob.job)
                    self._cheap_q.task_done()

                if batch:
                    tasks = [
                        asyncio.create_task(
                            self._run_job(j, self._cfg.cheap),
                            name=f"job-{j.job_id[:8]}"
                        )
                        for j in batch
                    ]
                    # Mark as batched if >1 concurrent
                    if len(tasks) > 1:
                        for j in batch:
                            j.was_batched = True
                    await asyncio.gather(*tasks, return_exceptions=True)

            else:
                # Nothing to do — idle sleep
                if self._mode == SchedulerMode.cheap_ready and self._cheap_q.empty() and self._smart_q.empty():
                    # Optional: unload to free VRAM after a period of inactivity
                    # For now just sleep
                    pass
                await asyncio.sleep(0.5)

    async def _drain_cheap_with_window(self) -> None:
        """Run all currently-queued cheap jobs, with a short window for more to arrive."""
        deadline = asyncio.get_event_loop().time() + self._cfg.scheduler.cheap_drain_window
        while True:
            if self._cheap_q.empty():
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        self._cheap_q.get(),
                        timeout=remaining,
                    )
                    break  # let dispatch loop handle it naturally
                except asyncio.TimeoutError:
                    break

        # Process whatever is in the cheap queue now
        if not self._cheap_q.empty():
            if self._mode == SchedulerMode.idle:
                try:
                    await self._load_cheap()
                except Exception as e:
                    err_msg = str(e)
                    log.error("Failed to load cheap model during drain: %s", err_msg)
                    self._last_resource_error = err_msg
                    while not self._cheap_q.empty():
                        pjob = await self._cheap_q.get()
                        job = pjob.job
                        if not self._is_cancelled(job):
                            job.status = JobStatus.resource_error
                            job.error_message = err_msg
                            job.completed_at = utcnow()
                            await self._store.update_job(job)
                        self._cheap_q.task_done()
                    return

            batch = []
            while not self._cheap_q.empty():
                pjob = await self._cheap_q.get()
                if not self._is_cancelled(pjob.job):
                    batch.append(pjob.job)
                self._cheap_q.task_done()

            # Run in sub-batches of size parallel
            profile = self._cfg.cheap
            for i in range(0, len(batch), profile.parallel):
                sub = batch[i:i + profile.parallel]
                if len(sub) > 1:
                    for j in sub:
                        j.was_batched = True
                tasks = [
                    asyncio.create_task(self._run_job(j, profile), name=f"job-{j.job_id[:8]}")
                    for j in sub
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

    # ──────────────────────────────────────────────
    # Mode transitions
    # ──────────────────────────────────────────────

    async def _load_cheap(self) -> None:
        self._mode = SchedulerMode.cheap_loading
        log.info("Loading cheap model...")
        try:
            await self._client.load_model(self._cfg.cheap)
            self._loaded_model = self._cfg.cheap.worker_class
            self._mode = SchedulerMode.cheap_ready
        except Exception as e:
            log.error("Failed to load cheap model: %s", e)
            self._mode = SchedulerMode.idle
            raise

    async def _switch_to_smart(self) -> None:
        self._mode = SchedulerMode.draining
        # Wait for any running cheap jobs to finish
        while self._running:
            log.info("Waiting for %d running cheap job(s) to finish before smart switch...",
                     len(self._running))
            await asyncio.sleep(1)

        # Unload cheap
        if self._loaded_model:
            self._mode = SchedulerMode.smart_loading
            await self._client.unload_model(self._cfg.cheap.worker_class)
            self._loaded_model = None

        # Load smart
        log.info("Loading smart model...")
        try:
            await self._client.load_model(self._cfg.smart)
            self._loaded_model = self._cfg.smart.worker_class
            self._mode = SchedulerMode.smart_ready
        except Exception as e:
            log.error("Failed to load smart model: %s", e)
            self._mode = SchedulerMode.idle
            raise

    async def _switch_to_cheap(self) -> None:
        self._mode = SchedulerMode.smart_unloading
        await self._client.unload_model(self._cfg.smart.worker_class)
        self._loaded_model = None
        self._mode = SchedulerMode.cheap_reloading
        # Only reload cheap if there are cheap jobs waiting
        if not self._cheap_q.empty():
            await self._load_cheap()
        else:
            self._mode = SchedulerMode.idle

    # ──────────────────────────────────────────────
    # Job execution
    # ──────────────────────────────────────────────

    async def _run_job(self, job: Job, profile: WorkerProfile) -> None:
        """Execute a single job against the currently-loaded model."""
        # Check if cancelled before even starting
        if self._is_cancelled(job):
            job.status = JobStatus.cancelled
            job.completed_at = utcnow()
            await self._store.update_job(job)
            return

        job.status = JobStatus.running
        job.started_at = utcnow()
        job.model_used = profile.lms_model_key
        self._running.add(job.job_id)
        await self._store.update_job(job)

        timeout = job.timeout_seconds or profile.default_timeout
        max_tokens = job.max_output_tokens or profile.max_output_tokens

        messages = []
        if job.system_prompt:
            messages.append({"role": "system", "content": job.system_prompt})
        messages.append({"role": "user", "content": job.user_prompt})

        try:
            result = await self._client.chat_complete(
                model_identifier=profile.worker_class,
                messages=messages,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            result = None
            job.status = JobStatus.model_error
            job.error_message = f"Unexpected error during inference: {e}"
            log.exception("Job %s inference error", job.job_id)
        finally:
            self._running.discard(job.job_id)
            self._cancelled.discard(job.job_id)

        if result is not None:
            job.input_tokens = result.input_tokens
            job.output_tokens = result.output_tokens
            job.finish_reason = result.finish_reason

            if self._is_cancelled(job):
                job.status = JobStatus.cancelled
            elif result.finish_reason == "timeout":
                job.status = JobStatus.model_error
                job.error_message = f"Job timed out after {timeout}s"
            elif result.finish_reason == "error" or not result.text:
                job.status = JobStatus.model_error
                job.error_message = "Inference returned an error or empty response"
            elif result.finish_reason == "length":
                # Context exhausted — try to get a handoff summary
                job.status = JobStatus.context_exhausted
                job.result_text = result.text
                try:
                    job.handoff_summary = await self._client.generate_handoff_summary(
                        model_identifier=profile.worker_class,
                        original_prompt=job.user_prompt,
                        partial_result=result.text,
                    )
                except Exception as e:
                    job.handoff_summary = f"(summary generation failed: {e})"
            else:
                job.status = JobStatus.completed
                job.result_text = result.text

        job.completed_at = utcnow()
        await self._store.update_job(job)
        log.info(
            "Job %s finished: %s (model=%s, tokens=%s/%s, batched=%s)",
            job.job_id[:8], job.status, job.model_used,
            job.input_tokens, job.output_tokens, job.was_batched,
        )

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _is_cancelled(self, job: Job) -> bool:
        return job.job_id in self._cancelled

    async def _graceful_unload(self) -> None:
        """Unload any loaded model on shutdown."""
        if self._loaded_model:
            log.info("Graceful shutdown: unloading %s", self._loaded_model)
            try:
                await self._client.unload_model(self._loaded_model)
            except Exception:
                pass

    async def _health_loop(self) -> None:
        interval = self._cfg.scheduler.health_check_interval
        while not self._shutdown.is_set():
            await asyncio.sleep(interval)
            self._lms_reachable = await self._client.is_reachable()
            if not self._lms_reachable:
                log.warning("LM Studio health check failed")

    async def _vram_loop(self) -> None:
        while not self._shutdown.is_set():
            await asyncio.sleep(15)
            info = await self._client.get_vram_info()
            if info:
                self._vram_total_mb = info.get("total_mb")
                self._vram_used_mb = info.get("used_mb")
                self._vram_free_mb = info.get("free_mb")
