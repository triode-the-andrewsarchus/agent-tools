"""
Async scheduler with mode FSM for cheap/smart GPU switching and cross-process coordination.

Coordination architecture:
- Multiple Antigravity instances/processes can connect to the same SQLite database.
- A POSIX file lock (`scheduler.lock`) designates one active Leader scheduler.
- The Leader scheduler owns model loading/unloading and inference against LM Studio.
- Other instances run as Followers: they submit jobs to SQLite and read results.
- If the Leader instance exits or closes, a Follower automatically acquires the lock
  and promotes itself to Leader without missing any queued jobs.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Any

from .config import AppConfig, WorkerProfile, load_config
from .db import JobStore
from .lms_client import LMSClient
from .models import Job, JobStatus, SchedulerMode, WorkerClass, utcnow

log = logging.getLogger(__name__)


class SchedulerLock:
    """Inter-process leader lock using fcntl.flock on a lockfile."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fp = None
        self.is_leader = False

    def try_acquire(self) -> bool:
        if self.is_leader:
            return True
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = open(self.lock_path, "a+")
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fp.seek(0)
            self._fp.truncate()
            self._fp.write(f"{os.getpid()}\n")
            self._fp.flush()
            self.is_leader = True
            return True
        except (BlockingIOError, OSError):
            if self._fp:
                try:
                    self._fp.close()
                except Exception:
                    pass
                self._fp = None
            self.is_leader = False
            return False

    def release(self) -> None:
        if self._fp:
            try:
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
                self._fp.close()
            except Exception:
                pass
            self._fp = None
        self.is_leader = False


class Scheduler:
    """Manages GPU mode, cross-process coordination, and dispatches jobs to LM Studio."""

    def __init__(
        self,
        cfg: AppConfig,
        store: JobStore,
        client: LMSClient,
        lock_path: Path | None = None,
        acquire_lock: bool = True,
        reload_config: bool = False,
    ) -> None:
        self._cfg = cfg
        self._store = store
        self._client = client
        self._reload_config = reload_config

        # Coordination
        is_memory_db = str(cfg.db_path) == ":memory:"
        if is_memory_db and lock_path is None:
            acquire_lock = False

        default_lock = cfg.db_path.parent / "scheduler.lock"
        self._lock_path = lock_path if lock_path is not None else default_lock
        self._state_path = self._lock_path.parent / "scheduler_state.json"
        self._should_acquire_lock = acquire_lock
        self._leader_lock = SchedulerLock(self._lock_path) if acquire_lock else None
        self._is_leader = not acquire_lock  # If acquire_lock is False (e.g. tests), default to leader
        self._wake_event = asyncio.Event()

        # In-flight job tracking
        self._running: set[str] = set()
        self._cancelled: set[str] = set()

        # Mode FSM
        self._mode: SchedulerMode = SchedulerMode.idle
        self._loaded_model: str | None = None

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
        """Enqueue a job. Persists to SQLite so any active Leader can claim it."""
        if not self._lms_reachable:
            # Re-check reachability
            if not await self._client.is_reachable():
                job.status = JobStatus.resource_error
                job.error_message = "LM Studio is not reachable. Check that LM Studio is running."
                await self._store.insert_job(job)
                return job
            self._lms_reachable = True

        await self._store.insert_job(job)
        self._wake_event.set()
        log.info("Queued %s job %s (priority=%d)", job.worker_class, job.job_id, job.priority)
        return job

    async def cancel(self, job_id: str) -> bool:
        """Request cancellation. Updates DB and in-flight tracking."""
        self._cancelled.add(job_id)
        found = await self._store.cancel_job(job_id)
        return found

    async def get_status(self) -> dict:
        """Return scheduler status dict for MCP."""
        if not self._is_leader and self._state_path.exists():
            try:
                with open(self._state_path, "r") as f:
                    state = json.load(f)
                if time.time() - state.get("updated_at", 0) < 15:
                    state["is_leader"] = False
                    state["active_pid"] = os.getpid()
                    return state
            except Exception:
                pass

        # If Leader, or if Follower without a fresh state file:
        info = await self._client.get_vram_info()
        if info:
            self._vram_total_mb = info.get("total_mb")
            self._vram_used_mb = info.get("used_mb")
            self._vram_free_mb = info.get("free_mb")

        counts = await self._store.get_queued_counts()
        status = {
            "mode": self._mode.value,
            "loaded_model": self._loaded_model,
            "lm_studio_reachable": self._lms_reachable,
            "queue": counts,
            "running_jobs": len(self._running),
            "vram_free_mb": self._vram_free_mb,
            "vram_total_mb": self._vram_total_mb,
            "vram_used_mb": self._vram_used_mb,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "last_resource_error": self._last_resource_error,
            "resource_diagnostics": self._last_resource_diagnostics,
            "is_leader": self._is_leader,
            "active_pid": os.getpid(),
        }
        if self._is_leader:
            self._write_state_file(status)
        return status

    def _write_state_file(self, status: dict) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(status)
            payload["updated_at"] = time.time()
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(payload, f)
            tmp.replace(self._state_path)
        except Exception as e:
            log.debug("Failed writing state file: %s", e)

    # ──────────────────────────────────────────────
    # Background tasks
    # ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main scheduler loop. Handles leader election and dispatch."""
        log.info("Scheduler process starting (PID=%d)", os.getpid())

        while not self._shutdown.is_set():
            if self._should_acquire_lock and self._leader_lock:
                acquired = self._leader_lock.try_acquire()
                if not acquired:
                    self._is_leader = False
                    # Follower loop: wait 2s or until shutdown, then retry lock
                    try:
                        await asyncio.wait_for(self._shutdown.wait(), timeout=2.0)
                        break
                    except asyncio.TimeoutError:
                        continue
                self._is_leader = True

            # Leader initialized
            log.info("Scheduler acquired leader lock (PID=%d)", os.getpid())
            self._lms_reachable = await self._client.is_reachable()
            if not self._lms_reachable:
                log.warning("LM Studio not reachable at startup!")

            # Reset any orphaned 'running' jobs from a previous leader
            await self._store.reset_stale_running_jobs()

            health_task = asyncio.create_task(self._health_loop(), name="health")
            vram_task = asyncio.create_task(self._vram_loop(), name="vram")
            state_task = asyncio.create_task(self._state_loop(), name="state")

            try:
                await self._dispatch_loop()
            finally:
                health_task.cancel()
                vram_task.cancel()
                state_task.cancel()
                await asyncio.gather(health_task, vram_task, state_task, return_exceptions=True)
                await self._graceful_unload()
                if self._leader_lock:
                    self._leader_lock.release()
                log.info("Scheduler leader stopped (PID=%d)", os.getpid())
            break

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._wake_event.set()

    # ──────────────────────────────────────────────
    # Dispatch loop (Leader only)
    # ──────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        while not self._shutdown.is_set():
            if not self._lms_reachable:
                await asyncio.sleep(2)
                continue

            counts = await self._store.get_queued_counts()
            has_smart = counts.get("smart", 0) > 0
            has_cheap = counts.get("cheap", 0) > 0

            if has_smart and self._mode in (SchedulerMode.idle, SchedulerMode.cheap_ready):
                if has_cheap:
                    log.info("Smart job pending — draining cheap queue first (window=%.1fs)",
                             self._cfg.scheduler.cheap_drain_window)
                    await self._drain_cheap_with_window()

                # Switch to smart mode
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
                    # Mark all queued smart jobs in SQLite as resource_error
                    queued_smart = await self._store.list_jobs(
                        status=JobStatus.queued, worker_class=WorkerClass.smart
                    )
                    for job in queued_smart:
                        job.status = JobStatus.resource_error
                        job.error_message = err_msg
                        job.completed_at = utcnow()
                        await self._store.update_job(job)
                    continue

                claimed_smart = await self._store.claim_queued_jobs(WorkerClass.smart, limit=1)
                if claimed_smart:
                    job = claimed_smart[0]
                    if not self._is_cancelled(job):
                        await self._run_job(job, self._cfg.smart)

                # Switch back to cheap mode
                try:
                    await self._switch_to_cheap()
                except Exception as e:
                    log.warning("Failed switching back to cheap: %s", e)

            elif has_cheap and self._mode in (SchedulerMode.idle, SchedulerMode.cheap_ready):
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
                        queued_cheap = await self._store.list_jobs(
                            status=JobStatus.queued, worker_class=WorkerClass.cheap
                        )
                        for job in queued_cheap:
                            job.status = JobStatus.resource_error
                            job.error_message = err_msg
                            job.completed_at = utcnow()
                            await self._store.update_job(job)
                        continue

                # Claim up to parallel cheap jobs
                batch = await self._store.claim_queued_jobs(
                    WorkerClass.cheap, limit=self._cfg.cheap.parallel
                )
                active_batch = [j for j in batch if not self._is_cancelled(j)]
                if active_batch:
                    tasks = [
                        asyncio.create_task(
                            self._run_job(j, self._cfg.cheap),
                            name=f"job-{j.job_id[:8]}"
                        )
                        for j in active_batch
                    ]
                    if len(tasks) > 1:
                        for j in active_batch:
                            j.was_batched = True
                    await asyncio.gather(*tasks, return_exceptions=True)

            else:
                # Idle sleep: wait on local wake event or 0.5s periodic check
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._wake_event.clear()

    async def _drain_cheap_with_window(self) -> None:
        """Run all currently-queued cheap jobs, with a short window for more to arrive."""
        deadline = asyncio.get_event_loop().time() + self._cfg.scheduler.cheap_drain_window
        while True:
            counts = await self._store.get_queued_counts()
            if counts.get("cheap", 0) == 0:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=remaining)
                    self._wake_event.clear()
                    break
                except asyncio.TimeoutError:
                    break
            else:
                break

        counts = await self._store.get_queued_counts()
        if counts.get("cheap", 0) > 0:
            if self._mode == SchedulerMode.idle:
                try:
                    await self._load_cheap()
                except Exception as e:
                    err_msg = str(e)
                    log.error("Failed to load cheap model during drain: %s", err_msg)
                    self._last_resource_error = err_msg
                    queued_cheap = await self._store.list_jobs(
                        status=JobStatus.queued, worker_class=WorkerClass.cheap
                    )
                    for job in queued_cheap:
                        job.status = JobStatus.resource_error
                        job.error_message = err_msg
                        job.completed_at = utcnow()
                        await self._store.update_job(job)
                    return

            batch = await self._store.claim_queued_jobs(
                WorkerClass.cheap, limit=self._cfg.cheap.parallel * 2
            )
            active_batch = [j for j in batch if not self._is_cancelled(j)]
            profile = self._cfg.cheap
            for i in range(0, len(active_batch), profile.parallel):
                sub = active_batch[i:i + profile.parallel]
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
        if self._reload_config:
            try:
                self._cfg = load_config()
            except Exception as e:
                log.warning("Could not reload config from disk, using existing: %s", e)
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
        while self._running:
            log.info("Waiting for %d running cheap job(s) before smart switch...",
                     len(self._running))
            await asyncio.sleep(1)

        if self._loaded_model:
            self._mode = SchedulerMode.smart_loading
            await self._client.unload_model(self._cfg.cheap.worker_class)
            self._loaded_model = None

        log.info("Loading smart model...")
        if self._reload_config:
            try:
                self._cfg = load_config()
            except Exception as e:
                log.warning("Could not reload config from disk, using existing: %s", e)
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
        counts = await self._store.get_queued_counts()
        if counts.get("cheap", 0) > 0:
            try:
                await self._load_cheap()
            except Exception as e:
                log.error("Failed to reload cheap model: %s", e)
        else:
            self._mode = SchedulerMode.idle

    # ──────────────────────────────────────────────
    # Job execution
    # ──────────────────────────────────────────────

    async def _run_job(self, job: Job, profile: WorkerProfile) -> None:
        """Execute a single job against the currently-loaded model."""
        fresh = await self._store.get_job(job.job_id)
        if fresh and fresh.status == JobStatus.cancelled:
            return

        self._running.add(job.job_id)
        job.status = JobStatus.running
        job.started_at = utcnow()
        job.model_used = profile.lms_model_key
        await self._store.update_job(job)

        timeout = job.timeout_seconds or profile.default_timeout
        max_tokens = job.max_output_tokens or profile.max_output_tokens

        messages = []
        if job.system_prompt:
            messages.append({"role": "system", "content": job.system_prompt})
        messages.append({"role": "user", "content": job.user_prompt})

        log.info("Starting job %s [%s] timeout=%.0fs max_tokens=%d",
                 job.job_id[:8], profile.worker_class, timeout, max_tokens)

        try:
            result = await self._client.chat_complete(
                model_identifier=profile.worker_class,
                messages=messages,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            log.error("Inference exception on job %s: %s", job.job_id[:8], e)
            job.status = JobStatus.model_error
            job.error_message = str(e)
            job.completed_at = utcnow()
            await self._store.update_job(job)
            self._running.discard(job.job_id)
            return

        self._running.discard(job.job_id)

        fresh = await self._store.get_job(job.job_id)
        if fresh and fresh.status == JobStatus.cancelled:
            log.info("Job %s was cancelled during inference", job.job_id[:8])
            return

        job.input_tokens = result.input_tokens
        job.output_tokens = result.output_tokens
        job.finish_reason = result.finish_reason

        if self._is_cancelled(job):
            job.status = JobStatus.cancelled
        else:
            if result.finish_reason == "timeout":
                job.status = JobStatus.model_error
                job.error_message = f"Job timed out after {timeout}s"
            elif result.finish_reason == "error" or not result.text:
                job.status = JobStatus.model_error
                job.error_message = "Inference returned an error or empty response"
            elif result.finish_reason == "length":
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

    async def _state_loop(self) -> None:
        """Leader publishes state to scheduler_state.json every 5 seconds."""
        while not self._shutdown.is_set():
            try:
                status = await self.get_status()
                self._write_state_file(status)
            except Exception as e:
                log.debug("State loop error: %s", e)
            await asyncio.sleep(5)
