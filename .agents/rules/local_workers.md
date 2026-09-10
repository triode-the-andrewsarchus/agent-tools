# Local Worker Pool — Delegation Policy

You have access to a local LLM worker pool via the `local_worker` MCP tools.
Workers are local LLMs running on the same machine. They are:
- **Substantially cheaper** than external inference (effectively free)
- **Slower** (seconds to minutes per job, plus model-load latency on first use)
- **Lower quality** than you, but capable of useful work
- **Asynchronous**: submit a job, get a job_id, poll for results later

## Worker classes

| Class | Model | Best for |
|---|---|---|
| `cheap` | Qwen3.5-9B | Extraction, classification, summarization, code review, research sub-questions, candidate generation, parallel investigations, repetitive transforms |
| `smart` | Qwen3.6-27B | Complex reasoning, difficult coding, synthesizing cheap worker results, tasks where 9B reliability is a concern |

The scheduler manages model loading/unloading automatically. Do not worry about which GPU or model file is used.

## When to delegate

**Strongly prefer delegation when:**
- The task is an independent investigation (API behavior, code inspection, doc lookup)
- You need multiple parallel sub-investigations
- The task is repetitive (applying the same transform to N items)
- The user is not waiting for an immediate response
- A wrong result can be reviewed and corrected
- The task involves gathering facts/summaries that you will synthesize

**Do it yourself when:**
- The answer is trivial (single-turn factual, one-liner)
- The final critical reasoning step must be correct and cannot be reviewed
- Delegation adds latency with no benefit (no parallelism available, no useful information)
- You are the only one who can make the decision

**Use smart worker when:**
- The task requires substantial multi-step reasoning
- Cheap worker returned low-confidence or incomplete results
- You want to synthesize results from several cheap workers
- The stakes of a wrong answer are high

## Async usage pattern

```
# Submit without blocking
job_a = worker_submit(worker_class="cheap", prompt="Investigate X", context_hint="X-investigation")
job_b = worker_submit(worker_class="cheap", prompt="Investigate Y", context_hint="Y-investigation")

# Continue with your own work...
# (reason, plan, answer other parts of the task)

# Collect when you need the results
result_a = worker_status(job_id=job_a.job_id)  # poll until status != queued/running
result_b = worker_status(job_id=job_b.job_id)
```

If `status` is `queued` or `running`, wait and try again. Poll at a reasonable interval (5–30s for cheap jobs, longer for smart).

## Context exhaustion

If `status == "context_exhausted"`:
- `result_text` contains what the worker produced before hitting the limit
- `handoff_summary` contains a compact summary of findings, what remains unresolved, and a recommendation

You can then:
- Synthesize the partial results yourself
- Retry with a smart worker for deeper analysis
- Ask the smart worker to continue from the handoff summary

## Batch parallel investigations

```
# Launch N independent cheap jobs
jobs = [
    worker_submit("cheap", prompt=f"Investigate aspect {i}", context_hint=f"aspect-{i}")
    for i in aspects
]
# Collect all
results = [worker_status(j.job_id) for j in jobs]  # wait for each
# Synthesize yourself
```

## Escalation pattern

```
cheap worker → incomplete / context_exhausted / low confidence
                          ↓
         smart worker (with handoff_summary as context)
                          ↓
              you synthesize final answer
```

## GPU-only policy and handling `resource_error`

There is **no CPU fallback** — running large models on CPU is too slow to be useful. If a model cannot fit in GPU VRAM (e.g. smart model on high desktop load), the job immediately returns `status="resource_error"`.

When `status == "resource_error"`:
- Inspect `error_message` — it details current VRAM headroom and actionable alternatives.
- If a `smart` job fails due to VRAM OOM:
  - **Downgrade to cheap worker**: `Qwen3.5-9B` uses only ~6.1 GB VRAM and fits with ample headroom.
  - **Reduce context/prompt size**: saves KV cache memory.
  - **Keep in supervisor**: do not offload to local LLM; handle directly yourself.

## Polling guidance

- Cheap job typical latency: 10–60s (longer if model needs to load first time)
- Smart job typical latency: 30–300s + model load (~30s)
- Model switch (cheap→smart or smart→cheap): ~20–60s
- Poll interval: 5s for cheap, 15s for smart
- Use `scheduler_status` to check queue depth and mode before submitting

## Default decision heuristic

| Situation | Action |
|---|---|
| Trivial, immediate response | Answer yourself |
| Difficult reasoning, immediate | Answer yourself; optionally use smart worker |
| Independent background work | Cheap worker |
| N independent investigations | N cheap workers in parallel |
| Long-running independent work | Cheap worker (even if takes minutes) |
| Cheap result can be reviewed | Delegate aggressively |
| Cheap failure would seriously mislead | Use smart or self |
| Several parallel subtasks + synthesis | Cheap workers for subtasks, you synthesize |
| No useful parallelism, worker would just delay | Answer yourself |

## Important: workers as evidence generators

Worker results are **inputs to your reasoning**, not final answers.
A cheap worker does not need to solve the problem completely to be useful —
it may only need to find a relevant fact, identify a bug, or propose a candidate.
You evaluate and synthesize.

## Checking scheduler health

Before submitting jobs on important tasks, optionally call `scheduler_status` to confirm
`lm_studio_reachable: true` and the queue is not deeply backed up.
