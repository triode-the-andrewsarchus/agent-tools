"""Unit tests for the scheduler using a mock LMSClient."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import pytest

from local_worker.config import AppConfig, WorkerProfile, SchedulerConfig
from local_worker.db import JobStore
from local_worker.lms_client import ChatResult, LMSClient
from local_worker.models import Job, JobStatus, SchedulerMode, WorkerClass
from local_worker.scheduler import Scheduler


def make_config() -> AppConfig:
    return AppConfig(
        cheap=WorkerProfile(
            worker_class="cheap",
            lms_model_key="test/cheap-model",
            context_length=4096,
            parallel=2,
            gpu_offload="max",
            max_output_tokens=512,
            default_timeout=10.0,
        ),
        smart=WorkerProfile(
            worker_class="smart",
            lms_model_key="test/smart-model",
            context_length=4096,
            parallel=1,
            gpu_offload="max",
            max_output_tokens=1024,
            default_timeout=30.0,
        ),
        scheduler=SchedulerConfig(
            cheap_drain_window=0.1,
            health_check_interval=9999,
            job_retention_days=7,
        ),
        lms_base_url="http://localhost:1234",
        lms_cli="/fake/lms",
        db_path=Path(":memory:"),
    )


def make_mock_client(
    reachable: bool = True,
    result_text: str = "Test result",
    finish_reason: str = "stop",
) -> LMSClient:
    client = MagicMock(spec=LMSClient)
    client.is_reachable = AsyncMock(return_value=reachable)
    client.load_model = AsyncMock()
    client.unload_model = AsyncMock()
    client.unload_all = AsyncMock()
    client.get_vram_free_mb = AsyncMock(return_value=8000)
    client.chat_complete = AsyncMock(return_value=ChatResult(
        text=result_text,
        finish_reason=finish_reason,
        input_tokens=100,
        output_tokens=50,
    ))
    client.generate_handoff_summary = AsyncMock(return_value="Handoff: found X, still need Y")
    return client


@pytest.fixture
async def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = JobStore(db_path)
    await s.open()
    yield s
    await s.close()


def make_job(cls: WorkerClass = WorkerClass.cheap, priority: int = 5) -> Job:
    return Job(
        worker_class=cls,
        priority=priority,
        user_prompt="Test prompt",
        context_hint="test",
    )


@pytest.mark.asyncio
async def test_submit_queues_job(store):
    """Submitted job should have status=queued and be persisted."""
    cfg = make_config()
    client = make_mock_client()
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True  # bypass startup check

    job = make_job()
    result = await sched.submit(job)

    assert result.status == JobStatus.queued
    persisted = await store.get_job(result.job_id)
    assert persisted is not None
    assert persisted.status == JobStatus.queued


@pytest.mark.asyncio
async def test_submit_resource_error_when_lms_unreachable(store):
    """Should return resource_error if LM Studio is unreachable."""
    cfg = make_config()
    client = make_mock_client(reachable=False)
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = False

    job = make_job()
    result = await sched.submit(job)

    assert result.status == JobStatus.resource_error
    assert result.error_message


@pytest.mark.asyncio
async def test_cheap_job_runs_and_completes(store):
    """A cheap job should complete with result_text after scheduler runs."""
    cfg = make_config()
    client = make_mock_client(result_text="Found the answer: 42")
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    job = make_job(WorkerClass.cheap)
    await sched.submit(job)

    # Run one dispatch cycle manually
    await sched._load_cheap()
    await sched._run_job(job, cfg.cheap)

    updated = await store.get_job(job.job_id)
    assert updated.status == JobStatus.completed
    assert updated.result_text == "Found the answer: 42"
    assert updated.model_used == cfg.cheap.lms_model_key
    assert updated.input_tokens == 100
    assert updated.output_tokens == 50


@pytest.mark.asyncio
async def test_context_exhausted_generates_handoff(store):
    """finish_reason='length' should produce context_exhausted + handoff_summary."""
    cfg = make_config()
    client = make_mock_client(
        result_text="Partial result...",
        finish_reason="length",
    )
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    job = make_job(WorkerClass.cheap)
    await store.insert_job(job)

    await sched._load_cheap()
    await sched._run_job(job, cfg.cheap)

    updated = await store.get_job(job.job_id)
    assert updated.status == JobStatus.context_exhausted
    assert updated.result_text == "Partial result..."
    assert updated.handoff_summary == "Handoff: found X, still need Y"
    client.generate_handoff_summary.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_queued_job(store):
    """Cancelling a queued job should set status=cancelled immediately."""
    cfg = make_config()
    client = make_mock_client()
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    job = make_job()
    await sched.submit(job)

    found = await sched.cancel(job.job_id)
    assert found is True

    updated = await store.get_job(job.job_id)
    assert updated.status == JobStatus.cancelled


@pytest.mark.asyncio
async def test_concurrent_cheap_jobs_marked_batched(store):
    """When multiple cheap jobs run concurrently, was_batched should be True."""
    cfg = make_config()

    async def slow_complete(*args, **kwargs):
        await asyncio.sleep(0.05)
        return ChatResult("result", "stop", 10, 5)

    client = make_mock_client()
    client.chat_complete = slow_complete
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    jobs = [make_job() for _ in range(3)]
    for j in jobs:
        await store.insert_job(j)
        for i in range(1, 3):
            jobs[i].was_batched = True

    await sched._load_cheap()

    # Run 2 concurrently
    tasks = [asyncio.create_task(sched._run_job(j, cfg.cheap)) for j in jobs[:2]]
    jobs[0].was_batched = True
    jobs[1].was_batched = True
    await asyncio.gather(*tasks)

    j0 = await store.get_job(jobs[0].job_id)
    j1 = await store.get_job(jobs[1].job_id)
    assert j0.was_batched
    assert j1.was_batched


@pytest.mark.asyncio
async def test_smart_mode_transition(store):
    """Smart job should trigger load_model calls for smart profile."""
    cfg = make_config()
    client = make_mock_client()
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    # Simulate loaded cheap
    sched._mode = SchedulerMode.cheap_ready
    sched._loaded_model = "cheap"

    await sched._switch_to_smart()

    # Should have unloaded cheap and loaded smart
    client.unload_model.assert_awaited_once_with("cheap")
    client.load_model.assert_awaited_once()
    call_args = client.load_model.call_args[0][0]
    assert call_args.lms_model_key == cfg.smart.lms_model_key
    assert sched._mode == SchedulerMode.smart_ready


@pytest.mark.asyncio
async def test_model_error_on_timeout(store):
    """Job that times out should get model_error status."""
    cfg = make_config()
    client = make_mock_client(finish_reason="timeout", result_text="")
    client.chat_complete = AsyncMock(return_value=ChatResult(
        text="", finish_reason="timeout", input_tokens=None, output_tokens=None
    ))
    sched = Scheduler(cfg, store, client)
    sched._lms_reachable = True

    job = make_job()
    job.timeout_seconds = 0.001
    await store.insert_job(job)
    await sched._load_cheap()
    await sched._run_job(job, cfg.cheap)

    updated = await store.get_job(job.job_id)
    assert updated.status == JobStatus.model_error
    assert "timed out" in (updated.error_message or "")


@pytest.mark.asyncio
async def test_db_list_and_filter(store):
    """worker_list filtering by status should work."""
    jobs = [make_job() for _ in range(4)]
    jobs[0].status = JobStatus.completed
    jobs[1].status = JobStatus.completed
    jobs[2].status = JobStatus.running
    jobs[3].status = JobStatus.queued
    for j in jobs:
        await store.insert_job(j)

    completed = await store.list_jobs(status=JobStatus.completed)
    assert len(completed) == 2

    running = await store.list_jobs(status=JobStatus.running)
    assert len(running) == 1
