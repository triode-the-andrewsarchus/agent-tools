#!/usr/bin/env python3
"""
Smoke test for the local worker scheduler.

Usage:
  uv run python scripts/smoke_test.py --class cheap --prompt "What is 2+2?"
  uv run python scripts/smoke_test.py --batch 3 --class cheap
  uv run python scripts/smoke_test.py --switch-test
  uv run python scripts/smoke_test.py --status
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from local_worker.config import load_config
from local_worker.db import JobStore
from local_worker.lms_client import LMSClient
from local_worker.models import Job, JobStatus, WorkerClass
from local_worker.scheduler import Scheduler


async def wait_for_job(store: JobStore, job_id: str, timeout: float = 600.0) -> dict:
    """Poll until job reaches terminal state."""
    deadline = time.monotonic() + timeout
    dots = 0
    while time.monotonic() < deadline:
        job = await store.get_job(job_id)
        if job and job.status not in (JobStatus.queued, JobStatus.running):
            print()
            return job.to_mcp_dict()
        print(".", end="", flush=True)
        dots += 1
        if dots % 60 == 0:
            print(f" [{job.status.value if job else 'unknown'}]")
        await asyncio.sleep(2)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


async def run_smoke(args) -> None:
    cfg = load_config()
    store = JobStore(cfg.db_path)
    await store.open()

    client = LMSClient(cfg.lms_base_url, cfg.lms_cli)
    await client.start()

    scheduler = Scheduler(cfg, store, client)
    sched_task = asyncio.create_task(scheduler.run(), name="scheduler")

    # Give scheduler a moment to check LM Studio health
    await asyncio.sleep(1)

    try:
        if args.status:
            status = await scheduler.get_status()
            print(json.dumps(status, indent=2, default=str))
            return

        if args.switch_test:
            print("=== Mode switch test: cheap then smart ===")
            cheap_job = Job(
                worker_class=WorkerClass.cheap,
                user_prompt="What is the capital of France? Answer in one word.",
                context_hint="switch-test-cheap",
            )
            smart_job = Job(
                worker_class=WorkerClass.smart,
                user_prompt="Explain in 50 words how a CPU cache works.",
                context_hint="switch-test-smart",
            )
            cheap_job = await scheduler.submit(cheap_job)
            smart_job = await scheduler.submit(smart_job)
            print(f"Cheap job: {cheap_job.job_id}")
            print(f"Smart job: {smart_job.job_id}")
            cheap_result = await wait_for_job(store, cheap_job.job_id)
            print(f"\nCheap result: {cheap_result.get('result_text', cheap_result)[:200]}")
            smart_result = await wait_for_job(store, smart_job.job_id)
            print(f"Smart result: {smart_result.get('result_text', smart_result)[:200]}")
            return

        if args.batch:
            print(f"=== Batch test: {args.batch} concurrent {args.worker_class} jobs ===")
            jobs = []
            for i in range(args.batch):
                j = Job(
                    worker_class=WorkerClass(args.worker_class),
                    user_prompt=f"Count to {i+3} and list each number.",
                    context_hint=f"batch-{i}",
                    priority=5,
                )
                j = await scheduler.submit(j)
                jobs.append(j)
                print(f"Submitted job {i+1}: {j.job_id}")

            results = []
            for j in jobs:
                r = await wait_for_job(store, j.job_id)
                results.append(r)

            print(f"\n=== Results ===")
            for i, r in enumerate(results):
                print(f"Job {i+1}: status={r['status']}, batched={r.get('was_batched')}, "
                      f"tokens={r.get('output_tokens')}")
            return

        # Single job
        prompt = args.prompt or "Summarize the concept of recursion in programming in 3 sentences."
        wclass = WorkerClass(args.worker_class)
        print(f"=== Single {wclass.value} job ===")
        print(f"Prompt: {prompt}")

        job = Job(
            worker_class=wclass,
            user_prompt=prompt,
            context_hint="smoke-test",
        )
        job = await scheduler.submit(job)
        print(f"Job ID: {job.job_id}")
        result = await wait_for_job(store, job.job_id)
        print(f"\nStatus: {result['status']}")
        if result.get('result_text'):
            print(f"Result:\n{result['result_text']}")
        if result.get('handoff_summary'):
            print(f"Handoff summary:\n{result['handoff_summary']}")
        if result.get('error_message'):
            print(f"Error: {result['error_message']}")
        print(f"\nStats: tokens={result.get('input_tokens')}/{result.get('output_tokens')}, "
              f"batched={result.get('was_batched')}, model={result.get('model_used')}")

    finally:
        scheduler.request_shutdown()
        try:
            await asyncio.wait_for(sched_task, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        await client.stop()
        await store.close()


def main():
    parser = argparse.ArgumentParser(description="Local worker smoke test")
    parser.add_argument("--class", dest="worker_class", default="cheap",
                        choices=["cheap", "smart"])
    parser.add_argument("--prompt", help="Prompt text for single-job test")
    parser.add_argument("--batch", type=int, help="Run N concurrent jobs")
    parser.add_argument("--switch-test", action="store_true",
                        help="Test cheap → smart mode switch")
    parser.add_argument("--status", action="store_true",
                        help="Print scheduler status and exit")
    args = parser.parse_args()
    asyncio.run(run_smoke(args))


if __name__ == "__main__":
    main()
