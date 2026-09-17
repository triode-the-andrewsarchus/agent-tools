# AGENTS.md — Agent Tools Monorepo

Instructions and guidelines for autonomous coding agents (Google Antigravity and OpenAI Codex) operating within this repository.

## Architecture & Layout

This repository is a monorepo housing three decoupled developer tools:
1. `local_llm`: Asynchronous local model offloading (`local_worker` MCP).
2. `pulpie`: Web content extraction and cleaning (`pulpie` MCP).
3. `refactoring`: Architecture fitness, cyclomatic complexity, and clone prevention (`architecture_fitness` MCP).

## Quick Verification Commands

```bash
# Check installation health across all agents
./install.py --status

# Run full test suite across all 3 components
local_llm/.venv/bin/pytest local_llm/tests/
pulpie/.venv/bin/pytest pulpie/tests/
refactoring/.venv/bin/pytest refactoring/tests/

# Run smoke tests
pulpie/.venv/bin/python pulpie/scripts/smoke_test.py --sample
refactoring/.venv/bin/python refactoring/scripts/smoke_test.py
local_llm/.venv/bin/python local_llm/scripts/smoke_test.py --status
```

## Management & Conventions

- Keep dependencies decoupled: each component has its own `.venv` and `pyproject.toml`.
- When updating MCP endpoints, skills, or rules, run `./install.py --all` to synchronize global agent configurations across Antigravity and Codex.
