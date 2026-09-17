# Agent Tools Monorepo

A unified monorepo containing local agent tools, Model Context Protocol (MCP) servers, skills, and rules designed for **Google Antigravity** and **OpenAI Codex** (CLI and IDE extensions).

---

## Included Components

| Subdirectory | MCP Server | Description | Primary Models / Stack |
|---|---|---|---|
| [`local_llm`](local_llm) | `local_worker` | Local LLM worker pool with asynchronous job scheduling and automatic GPU memory coordination. | Qwen3.5-9B (cheap/parallel), Qwen3.6-27B (smart/reasoning) via LM Studio |
| [`pulpie`](pulpie) | `pulpie` | Local neural web content extraction service that strips boilerplate (nav, ads, footers) while strictly preserving document semantics. | Pulpie Orange Small (`feyninc/pulpie-orange-small`, 210M params) |
| [`refactoring`](refactoring) | `architecture_fitness` | Multidimensional architecture fitness, cyclomatic complexity tracking, duplication detection, and reuse discovery. | Lizard (CCN), jscpd (clones), Valknut (structural graph) |

*Note: For convenience and backwards-compatibility, `local_worker -> local_llm` and `architecture_fitness -> refactoring` symlinks exist within the monorepo.*

---

## Installation & Setup

A unified installer (`install.py`) is provided at the root of the repository. It supports both **all-in-one** setup and **granular** single-tool/single-agent installations.

### 1. Check Status
Inspect the current registration, symlinks, and virtual environment status across all agents:
```bash
./install.py --status
```

### 2. Install All Tools to All Agents
Installs all 3 tools (MCP servers, schemas, skills, and rules) to both Antigravity and Codex:
```bash
./install.py --all
```

### 3. Install All Tools to a Specific Agent
```bash
# Antigravity only (~/.gemini/)
./install.py --agent antigravity --all

# Codex only (~/.codex/)
./install.py --agent codex --all
```

### 4. Granular Installation (Specific Tool to Specific Agent)
Install only what you need without bloating other environments:
```bash
# Install only Pulpie to Codex
./install.py --tool pulpie --agent codex

# Install only Architecture Fitness to Antigravity
./install.py --tool refactoring --agent antigravity

# Install only Local Worker to all agents
./install.py --tool local_llm --agent all
```

### 5. Uninstall / Unlink
```bash
./install.py --uninstall --tool pulpie --agent codex
```

### 6. Component-Level Registration
Each component also contains a `scripts/register_mcp.py` script for local invocation inside its folder:
```bash
cd pulpie && python scripts/register_mcp.py
cd refactoring && python scripts/register_mcp.py
cd local_llm && python scripts/register_mcp.py
```

---

## Running Tests

Each component maintains its own isolated virtual environment:

```bash
# Run local_llm tests
local_llm/.venv/bin/pytest local_llm/tests/

# Run pulpie tests
pulpie/.venv/bin/pytest pulpie/tests/

# Run refactoring tests
refactoring/.venv/bin/pytest refactoring/tests/
```

---

## Repository Structure

```
agent-tools/
├── install.py                      # Unified CLI installer and health status
├── README.md                       # Monorepo documentation
├── AGENTS.md                       # Cross-agent developer guide
├── local_llm/                      # Local LLM worker pool
│   ├── src/local_worker/           # MCP server & scheduler source
│   ├── .agents/                    # Skills & rules
│   └── tests/                      # Pytest suite
├── pulpie/                         # Web preprocessing service
│   ├── src/pulpie_service/         # MCP server & extractor source
│   ├── .agents/                    # Skills & rules
│   └── tests/                      # Pytest suite
└── refactoring/                    # Architecture fitness system
    ├── src/architecture_fitness/   # MCP server & analyzers
    ├── .agents/                    # Skills & rules
    └── tests/                      # Pytest suite
```
