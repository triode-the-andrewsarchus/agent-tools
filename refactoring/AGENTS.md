# AGENTS.md — Architecture Fitness (`refactoring`)

This repository provides a local, repository-agnostic architecture-fitness and complexity feedback system designed for coding agents (including Google Antigravity and OpenAI Codex CLI / IDE extension). It continuously inspects structural complexity, duplication, and coupling using Lizard, jscpd, and Valknut, exposed via the Model Context Protocol (MCP) and agent skills.

---

## Environment & Architecture

- **Python Version**: Python >= 3.11
- **Virtual Environment**: `.venv` (located at `/home/vega/Documents/git/local/agent-tools/refactoring/.venv`)
- **Package Source**: `src/` (root module: `architecture_fitness`)
- **Analyzers**:
  - **Lizard** (1.24.0): Cyclomatic complexity (CCN), parameter count, token count, NLOC.
  - **jscpd** (5.2.0): Exact clone pairs, duplicate lines, and duplication percentages.
  - **Valknut** (1.5.1): Rust-native maintainability index, cognitive complexity, dependency cycles, and chokepoints.
  - Binaries reside in `/home/vega/.local/bin` (included in PATH).
- **MCP Server**: Stdio MCP server implemented in `architecture_fitness.mcp_server`.

---

## Verification & Development Commands

Always run commands using the project virtualenv:

```bash
# Run full automated test suite (27 unit & integration tests)
.venv/bin/pytest tests/ -v

# Run smoke test on a sample synthetic multi-file codebase
.venv/bin/python scripts/smoke_test.py

# Register MCP server and agent skills across Antigravity and Codex
.venv/bin/python scripts/register_mcp.py

# Check Codex MCP status and tool registrations
codex mcp list
codex mcp get architecture_fitness --json
```

---

## MCP Server Tools

When running as an MCP server (`architecture_fitness`), the following 5 tools are available:

1. **`architecture_baseline`**:
   - `repo_path: str` (required): Absolute path to repository root.
   - `name: str` (optional): Baseline name/tag (e.g. `'pre-feature'`). Defaults to commit hash / timestamp.
   - `profile: "fast" | "balanced" | "thorough"` (optional, default: `"fast"`).
   - Establishes or retrieves a structural baseline saved under `.fitness/baselines/`.

2. **`architecture_measure`**:
   - `repo_path: str` (required): Absolute path to repository root.
   - `target_paths: list[str]` (optional): Subdirectories or specific files.
   - `profile: "fast" | "balanced" | "thorough"` (optional, default: `"fast"`).
   - Runs Lizard, jscpd, and Valknut against the current working tree.

3. **`architecture_compare`**:
   - `repo_path: str` (required): Absolute path to repository root.
   - `baseline_name: str` (optional): Baseline identifier or commit to compare against.
   - `diff_aware: bool` (optional, default: `true`): Focuses regressions specifically on modified files/lines.
   - `profile: "fast" | "balanced" | "thorough"` (optional, default: `"fast"`).
   - Classifies change as `IMPROVED`, `NEUTRAL`, `REGRESSION`, or `UNKNOWN`.

4. **`architecture_hotspots`**:
   - `repo_path: str` (required): Absolute path to repository root.
   - `top_n: int` (optional, default: `10`): Maximum hotspots to return.
   - `criteria: str` (optional): Filter by `'complexity'`, `'duplication'`, or `'cycle'`.
   - Returns ranked structural debt items with source locations and severity.

5. **`architecture_reuse_candidates`**:
   - `repo_path: str` (required): Absolute path to repository root.
   - `query: str` (required): Functionality description or candidate symbol name.
   - `context: str` (optional): Domain or parameter context.
   - `top_n: int` (optional, default: `5`): Maximum candidates.
   - Searches repository for existing symbols and utilities before adding redundant code.

---

## Rules of Engagement for Coding Agents

### 1. The Principle of Benefit of the Doubt
> **New mechanism requires justification; existing mechanism gets the benefit of the doubt.**
- Before writing a new utility, helper, data structure, or validation function, query `architecture_reuse_candidates`.
- Extend or parameterize existing mechanisms whenever possible rather than creating parallel implementations.

### 2. Measurement Discipline
- Freeze a reference point with `architecture_baseline` prior to modifying code.
- Run `architecture_compare` after implementation.
- If `architecture_compare` reports `ARCHITECTURE RESULT: REGRESSION` (e.g., CCN spike > 15, new clone groups, or dependency cycles), treat it as an objective indicator of accidental complexity and revise.

### 3. Anti-Gaming Heuristics
- Moving code across files without simplifying logic is **not** an architectural improvement.
- Splitting cohesive functions into arbitrary one-line delegators increases indirection without reducing system complexity.
- Deleting required features or tests to improve metrics is strictly forbidden.
