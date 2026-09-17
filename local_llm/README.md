# Local LLM Worker Pool

An MCP-based local LLM worker scheduler for Google Antigravity.

## Architecture

```
Antigravity Instance 1 ──┐
                         ├─►  ~/.local/share/local-worker/jobs.db (SQLite WAL)
Antigravity Instance 2 ──┘                 ▲
       │                                   │ claims queued jobs
   (MCP stdio)                             │
       ▼                                   ▼
  Follower Client ──────────► [Active Leader Scheduler]
   (submits to DB)                 (holds POSIX lock)
                                           │
                                 ┌─────────┴──────────┐
                                 │                    │
                           lms CLI subprocess    aiohttp REST
                           (load/unload)         /v1/chat/completions
                                 │                    │
                                 └────────┬───────────┘
                                          ▼
                                     LM Studio
                                    localhost:1234
                                          │
                                ┌─────────┴─────────┐
                              cheap              smart
                           Qwen3.5-9B        Qwen3.6-27B
                           parallel=2         parallel=1
```

## Worker Classes

| Class | Model | VRAM loaded | Concurrency | Primary Use |
|---|---|---|---|---|
| `cheap` | `qwen/qwen3.5-9b` (Q4_K_M) | ~6.1 GiB (ctx 8192) | `parallel = 2` | Fast extraction, classification, code reviews, batch parallel sub-tasks |
| `smart` | `qwen/qwen3.6-27b` (Q4_K_M) | ~16.3 GiB (ctx 8192) | `parallel = 1` | Deep multi-step reasoning, synthesis, complex coding |

*(Secondary downloaded variant `unsloth/qwen3.5-9b` Q4_K_S at ~6.72 GiB is also supported).*

---

## Multi-Instance & Cross-Process Coordination

Antigravity launches a dedicated stdio MCP server process for **each** active window or workspace. To prevent multiple instances from fighting over GPU VRAM or issuing conflicting model loads to LM Studio:

1. **POSIX File Lock Leader Election**:
   - The first Antigravity process acquires an exclusive non-blocking lock on `~/.local/share/local-worker/scheduler.lock`.
   - The lock holder becomes the **Active Leader**, managing model loading/unloading and dispatching to LM Studio.
2. **Follower / Client Mode**:
   - Secondary Antigravity processes detect the active lock and run as **Followers**.
   - Followers do not touch LM Studio or GPU state directly. Instead, they insert submitted jobs into the shared SQLite DB (`~/.local/share/local-worker/jobs.db`).
   - The Leader picks up queued jobs from SQLite, executes them on the GPU, and writes back the results.
3. **Automatic Failover**:
   - If the Antigravity window running the Leader is closed, the OS automatically releases the file lock.
   - A remaining Follower acquires the lock within ~2 seconds and seamlessly promotes itself to Leader without losing any queued jobs.
4. **Standalone Daemon (Optional)**:
   - You can optionally run `python -m local_worker.scheduler` as an independent background daemon or user service. It will hold the leader lock continuously, and all Antigravity windows will cleanly act as clients.

---

## Global Antigravity Setup

To use the local worker pool across all Antigravity windows and workspaces:

### 1. MCP Server Registration (`~/.gemini/settings.json`)
The MCP server is registered in your global settings:
```json
{
  "mcpServers": {
    "local_worker": {
      "command": "/home/vega/Documents/git/local/antigravity_with_local_llm/.venv/bin/python",
      "args": ["-m", "local_worker.mcp_server"],
      "env": {
        "PYTHONPATH": "/home/vega/Documents/git/local/antigravity_with_local_llm/src",
        "LOCAL_WORKER_PROFILES": "/home/vega/Documents/git/local/antigravity_with_local_llm/worker_profiles.toml",
        "LOCAL_WORKER_DB": "/home/vega/.local/share/local-worker/jobs.db",
        "LMS_BASE_URL": "http://localhost:1234",
        "LMS_CLI": "/home/vega/.lmstudio/bin/lms"
      }
    }
  }
}
```

### 2. Global Skills & Rules Symlinks
Symlinked to the global Antigravity customization root (`~/.gemini/config/`) so any window/project discovers the tool cheatsheet and delegation policy:
```bash
# Skills
ln -sfn /home/vega/Documents/git/local/antigravity_with_local_llm/.agents/skills/local-workers ~/.gemini/config/skills/local-workers

# Rules (delegation heuristics)
ln -sfn /home/vega/Documents/git/local/antigravity_with_local_llm/.agents/rules/local_workers.md ~/.gemini/config/rules/local_workers.md
```

---

## Execution Policy & Resource Handling

- **GPU Only (No CPU Fallback)**:
  Running 27B models on CPU is impractically slow. If a model cannot fit in VRAM, the loader fails cleanly.
- **Graceful Downgrade & Diagnostic Feedback**:
  If GPU VRAM is insufficient (e.g. smart model requested when desktop apps are using high VRAM), the job returns `status="resource_error"`.
  The error message details:
  - Current free and total VRAM
  - Attempt history
  - Actionable downgrade suggestions (e.g. downgrade to `cheap` worker `Qwen3.5-9B`, reduce context length, or handle directly in supervisor without offloading).

---

## Testing & Verification

```bash
# Run unit tests (mocked LM Studio, 12 test cases including multi-instance coordination)
PYTHONPATH=src .venv/bin/pytest tests/ -v

# Check live scheduler status
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --status

# Run single cheap job
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --class cheap --prompt "What is 15 * 3?"

# Run concurrent batch test
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --batch 2 --class cheap
```
