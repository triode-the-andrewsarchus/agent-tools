# Local LLM Worker Pool

An MCP-based local LLM worker scheduler for Antigravity.

## Architecture

```
Antigravity (coordinator)
    │  MCP stdio
    ▼
mcp_server.py  ──async──►  scheduler.py
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

## Worker classes

| Class | Model | VRAM |
|---|---|---|
| `cheap` | Qwen3.5-9B Q4_K_M | ~7 GB |
| `smart` | Qwen3.6-27B Q4_K_M | ~18.3 GB |

## Requirements

- LM Studio running at `localhost:1234`
- RTX 3090 with ≥4 GB VRAM headroom (typically available; desktop uses ~4 GB)
- `qwen/qwen3.5-9b` downloaded in LM Studio (cheap model)
- `qwen/qwen3.6-27b` downloaded in LM Studio (smart model, already present)

## First run

If the cheap model is not downloaded yet:
```bash
~/.lmstudio/bin/lms get qwen/qwen3.5-9b -y --gguf
```

## Setup

```bash
cd antigravity_with_local_llm
uv venv
uv pip install "mcp[cli]>=2.2.0" "aiohttp>=3.13" "aiosqlite>=0.21" "pydantic>=2.0"
```

The MCP server is registered in `~/.gemini/settings.json` and started automatically
by Antigravity when needed.

## Testing

```bash
# Unit tests (no LM Studio required)
PYTHONPATH=src .venv/bin/pytest tests/ -v

# Smoke tests (LM Studio must be running)
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --status
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --class cheap --prompt "What is 2+2?"
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --batch 3 --class cheap
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --switch-test
```

## Configuration

Edit `worker_profiles.toml` to adjust context length, parallel slots, or timeouts.
Only pre-validated values should be used — do not generate parameters at runtime.

## Future GPUs

To add a new GPU/worker, add a new profile section in `worker_profiles.toml` and
extend the scheduler to route jobs by class. The MCP API (`worker_class=cheap|smart`)
does not change.
