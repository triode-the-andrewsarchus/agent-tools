---
name: local-workers
description: Reference card for the local LLM worker pool MCP tools. Load this when you need tool signatures, status codes, or usage patterns for worker_submit, worker_status, worker_cancel, worker_list, or scheduler_status.
---

# Local Worker Pool — Quick Reference

## Tools

### `worker_submit`
Submit a task to a local LLM worker. Returns immediately with a `job_id`.

```json
{
  "worker_class": "cheap | smart",
  "prompt": "task text (required)",
  "system_prompt": "optional",
  "priority": 5,
  "max_output_tokens": null,
  "timeout_seconds": null,
  "context_hint": "short label for logs"
}
```

Returns:
```json
{
  "job_id": "uuid",
  "status": "queued | resource_error",
  "worker_class": "cheap | smart",
  "queued_at": "ISO timestamp",
  "message": "human-readable status"
}
```

### `worker_status`
Poll for job result.

```json
{"job_id": "uuid"}
```

Returns a full job record:
```json
{
  "job_id": "...",
  "status": "completed | running | queued | context_exhausted | model_error | ...",
  "worker_class": "cheap | smart",
  "model_used": "qwen/qwen3.5-9b",
  "result_text": "... (on completed or context_exhausted)",
  "handoff_summary": "... (on context_exhausted only)",
  "finish_reason": "stop | length | error | timeout",
  "queued_at": "...", "started_at": "...", "completed_at": "...",
  "input_tokens": 312, "output_tokens": 187,
  "was_batched": true,
  "error_message": "... (on error statuses)"
}
```

### `worker_cancel`
```json
{"job_id": "uuid"}
```
Returns: `{"job_id": "...", "found": true, "message": "..."}`

### `worker_list`
```json
{
  "status": "queued | running | completed | ...",   // optional filter
  "worker_class": "cheap | smart",                  // optional filter
  "limit": 20
}
```

### `scheduler_status`
No inputs required. Returns:
```json
{
  "mode": "idle | cheap_loading | cheap_ready | draining | smart_loading | smart_ready | smart_unloading | cheap_reloading",
  "loaded_model": "qwen/qwen3.5-9b | null",
  "lm_studio_reachable": true,
  "queue": {"cheap": 3, "smart": 0},
  "running_jobs": 2,
  "vram_free_mb": 4800,
  "uptime_seconds": 3610
}
```

## Status codes

| Status | Meaning |
|---|---|
| `queued` | Waiting to run |
| `running` | Currently in inference |
| `completed` | Success — check `result_text` |
| `context_exhausted` | Hit token limit — check `result_text` + `handoff_summary` |
| `cancelled` | Cancelled by caller |
| `model_error` | Inference error or timeout — check `error_message` |
| `resource_error` | LM Studio not reachable |
| `tool_error` | Scheduler/tool internal error |
| `capability_mismatch` | Unsupported worker class |

## Scheduler modes

| Mode | Meaning |
|---|---|
| `idle` | No model loaded, nothing running |
| `cheap_loading` | Loading 9B model |
| `cheap_ready` | 9B loaded, accepting cheap jobs |
| `draining` | Draining cheap jobs before smart switch |
| `smart_loading` | Unloaded 9B, loading 27B |
| `smart_ready` | 27B loaded, running smart job |
| `smart_unloading` | Unloading 27B |
| `cheap_reloading` | Reloading 9B after smart job |

## Common patterns

### Parallel investigation
```
job_a = worker_submit("cheap", prompt="Investigate A", context_hint="inv-A")
job_b = worker_submit("cheap", prompt="Investigate B", context_hint="inv-B")
job_c = worker_submit("cheap", prompt="Investigate C", context_hint="inv-C")
# Poll each: worker_status(job_id) until status not in [queued, running]
# Then synthesize
```

### Escalation
```
cheap_job = worker_submit("cheap", prompt=task)
# ... wait ...
result = worker_status(cheap_job.job_id)
if result.status == "context_exhausted":
    smart_job = worker_submit("smart", prompt=f"""
    A previous worker investigated this task but ran out of context.
    Handoff summary: {result.handoff_summary}
    Please complete the analysis.
    Original task: {task}
    """)
```

### Check before submitting
```
status = scheduler_status()
if not status.lm_studio_reachable:
    # handle gracefully — LM Studio may not be running
```

## Notes

- Model load on first use: ~20–60s (cheap), ~30–90s (smart) — normal, expected
- Model switch (cheap ↔ smart): ~20–60s — scheduler handles automatically
- Cheap jobs batch automatically (up to parallel=2 concurrently)
- Smart jobs are exclusive (parallel=1) — scheduler drains cheap queue first
- Job results persist in SQLite for 7 days
