"""SQLite job store using aiosqlite.

Schema:
  jobs — one row per job, all fields from models.Job serialized.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .models import Job, JobStatus, WorkerClass

log = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id            TEXT PRIMARY KEY,
    worker_class      TEXT NOT NULL,
    status            TEXT NOT NULL,
    priority          INTEGER NOT NULL DEFAULT 5,
    system_prompt     TEXT,
    user_prompt       TEXT NOT NULL,
    context_hint      TEXT,
    max_output_tokens INTEGER,
    timeout_seconds   REAL,
    model_used        TEXT,
    queued_at         TEXT NOT NULL,
    started_at        TEXT,
    completed_at      TEXT,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    was_batched       INTEGER NOT NULL DEFAULT 0,
    result_text       TEXT,
    finish_reason     TEXT,
    handoff_summary   TEXT,
    error_message     TEXT
)
"""

CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)"


def _row_to_job(row: aiosqlite.Row) -> Job:
    d = dict(row)
    d["worker_class"] = WorkerClass(d["worker_class"])
    d["status"] = JobStatus(d["status"])
    d["was_batched"] = bool(d["was_batched"])
    for ts_field in ("queued_at", "started_at", "completed_at"):
        if d[ts_field]:
            d[ts_field] = datetime.fromisoformat(d[ts_field])
    return Job(**d)


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(CREATE_TABLE)
        await self._db.execute(CREATE_INDEX)
        await self._db.commit()
        log.info("Database opened: %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def insert_job(self, job: Job) -> None:
        await self._db.execute(
            """INSERT INTO jobs VALUES (
                :job_id, :worker_class, :status, :priority, :system_prompt,
                :user_prompt, :context_hint, :max_output_tokens, :timeout_seconds,
                :model_used, :queued_at, :started_at, :completed_at,
                :input_tokens, :output_tokens, :was_batched,
                :result_text, :finish_reason, :handoff_summary, :error_message
            )""",
            _job_to_row(job),
        )
        await self._db.commit()

    async def update_job(self, job: Job) -> None:
        await self._db.execute(
            """UPDATE jobs SET
                status=:status, model_used=:model_used,
                started_at=:started_at, completed_at=:completed_at,
                input_tokens=:input_tokens, output_tokens=:output_tokens,
                was_batched=:was_batched, result_text=:result_text,
                finish_reason=:finish_reason, handoff_summary=:handoff_summary,
                error_message=:error_message
            WHERE job_id=:job_id""",
            _job_to_row(job),
        )
        await self._db.commit()

    async def get_job(self, job_id: str) -> Job | None:
        async with self._db.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ) as cur:
            row = await cur.fetchone()
            return _row_to_job(row) if row else None

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        worker_class: WorkerClass | None = None,
        limit: int = 50,
    ) -> list[Job]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status.value)
        if worker_class:
            clauses.append("worker_class=?")
            params.append(worker_class.value)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        async with self._db.execute(
            f"SELECT * FROM jobs {where} ORDER BY queued_at DESC LIMIT ?", params
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_job(r) for r in rows]

    async def get_queued_counts(self) -> dict[str, int]:
        """Return count of queued jobs per worker class."""
        counts = {"cheap": 0, "smart": 0}
        async with self._db.execute(
            "SELECT worker_class, COUNT(*) as cnt FROM jobs WHERE status='queued' GROUP BY worker_class"
        ) as cur:
            rows = await cur.fetchall()
            for r in rows:
                counts[r["worker_class"]] = r["cnt"]
        return counts

    async def claim_queued_jobs(
        self, worker_class: WorkerClass, limit: int = 1
    ) -> list[Job]:
        """Atomically claim up to `limit` queued jobs by setting status='running'."""
        now_str = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            """SELECT job_id FROM jobs
               WHERE status='queued' AND worker_class=?
               ORDER BY priority ASC, queued_at ASC
               LIMIT ?""",
            (worker_class.value, limit),
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return []

        claimed: list[Job] = []
        for r in rows:
            jid = r["job_id"]
            res = await self._db.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE job_id=? AND status='queued'",
                (now_str, jid),
            )
            if res.rowcount > 0:
                job = await self.get_job(jid)
                if job:
                    claimed.append(job)
        await self._db.commit()
        return claimed

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job. If queued, sets status='cancelled' immediately."""
        now_str = datetime.now(timezone.utc).isoformat()
        res = await self._db.execute(
            """UPDATE jobs SET status='cancelled', completed_at=?
               WHERE job_id=? AND status IN ('queued', 'running')""",
            (now_str, job_id),
        )
        await self._db.commit()
        return res.rowcount > 0

    async def reset_stale_running_jobs(self) -> int:
        """Reset orphaned 'running' jobs back to 'queued' when a leader starts."""
        res = await self._db.execute(
            "UPDATE jobs SET status='queued', started_at=NULL WHERE status='running'"
        )
        await self._db.commit()
        if res.rowcount > 0:
            log.info("Reset %d stale running jobs back to queued", res.rowcount)
        return res.rowcount

    async def prune_old_jobs(self, retention_days: int) -> int:
        """Remove terminal jobs older than retention_days. Returns count deleted."""
        result = await self._db.execute(
            """DELETE FROM jobs
               WHERE status IN ('completed','cancelled','context_exhausted',
                                'model_error','tool_error','resource_error')
                 AND completed_at < datetime('now', ?)""",
            (f"-{retention_days} days",),
        )
        await self._db.commit()
        deleted = result.rowcount
        if deleted:
            log.info("Pruned %d old jobs", deleted)
        return deleted


def _job_to_row(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "worker_class": job.worker_class.value,
        "status": job.status.value,
        "priority": job.priority,
        "system_prompt": job.system_prompt,
        "user_prompt": job.user_prompt,
        "context_hint": job.context_hint,
        "max_output_tokens": job.max_output_tokens,
        "timeout_seconds": job.timeout_seconds,
        "model_used": job.model_used,
        "queued_at": job.queued_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "input_tokens": job.input_tokens,
        "output_tokens": job.output_tokens,
        "was_batched": int(job.was_batched),
        "result_text": job.result_text,
        "finish_reason": job.finish_reason,
        "handoff_summary": job.handoff_summary,
        "error_message": job.error_message,
    }
