# AGENTS.md — Agent Tools Monorepo

Instructions and guidelines for autonomous coding agents (Google Antigravity and OpenAI Codex) operating within this repository.

## Architecture & Layout

This repository is a monorepo housing developer tools and cross-agent skills:
1. `local_llm`: Asynchronous local model offloading (`local_worker` MCP).
2. `pulpie`: Web content extraction and cleaning (`pulpie` MCP).
3. `refactoring`: Architecture fitness, cyclomatic complexity, and clone prevention (`architecture_fitness` MCP).
4. `id_tokenizer`: Identifier tokenization, UUID substitution, and hallucination protection (`id_tokenizer` MCP).
5. `skills`: Standalone cross-agent skills (`rust-development`, `rust-doc-formatting`, `debugging-code`, `lsp-code-analysis`).

## Quick Verification Commands

```bash
# Check installation health across all agents
./install.py --status

# Run full test suite across all 4 components
local_llm/.venv/bin/pytest local_llm/tests/
pulpie/.venv/bin/pytest pulpie/tests/
refactoring/.venv/bin/pytest refactoring/tests/
id_tokenizer/.venv/bin/pytest id_tokenizer/tests/

# Run smoke tests
pulpie/.venv/bin/python pulpie/scripts/smoke_test.py --sample
refactoring/.venv/bin/python refactoring/scripts/smoke_test.py
local_llm/.venv/bin/python local_llm/scripts/smoke_test.py --status
id_tokenizer/.venv/bin/python id_tokenizer/scripts/smoke_test.py
```

## Management & Conventions

- Keep dependencies decoupled: each component has its own `.venv` and `pyproject.toml`.
- When updating MCP endpoints, skills, or rules, run `./install.py --all` to synchronize global agent configurations across Antigravity and Codex.
