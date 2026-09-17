# Architecture Fitness for Antigravity & Codex (`refactoring`)

A local, repository-agnostic architecture-fitness and complexity feedback system designed for coding agents (Google Antigravity, OpenAI Codex CLI, and the Codex IDE extension).

## Problem Statement

Coding agents (and human "vibe-coders") suffer from a systematic failure mode:
When asked to implement a feature or solve an issue, agents tend to write brand new functions, classes, wrappers, and redundant algorithms from scratch rather than inspecting and reusing pre-existing mechanisms in the repository. Over multiple iterations, this causes:
- **Code bloat** (uncontrolled LOC growth)
- **Mental model fragmentation** (multiple ways to do the exact same thing)
- **High cyclomatic complexity** (compound conditionals and unhandled edge cases)
- **Duplication accumulation** (copy-pasting with trivial tweaks)
- **Architectural rot** (hidden dependency cycles and bloated modules)

`architecture-fitness` counters this by providing an objective, multidimensional architectural measurement loop exposed via the Model Context Protocol (MCP) and paired with specialized agent skills.

---

## The Core Feedback Loop

```
1. Establish Baseline (pre-feature / pre-refactor)
      ↓
2. Inspect Existing Architecture & Reuse Candidates
      ↓
3. Agent Implements Feature or Refactoring Pass
      ↓
4. Run Multidimensional Measurement (Lizard + jscpd + Valknut)
      ↓
5. Diff-Aware Comparison Against Baseline
      ↓
6. Identify Regressions vs. Accidental vs. Necessary Complexity
      ↓
7. Revise Implementation if Appropriate
```

---

## Architectural Measurement Engines

Rather than attempting to reinvent static analysis or reducing health to a single opaque score, the system orchestrates three specialized tools:

| Engine | Role & Capabilities | Limitations |
|---|---|---|
| **Lizard** (1.24.0) | Function-level cyclomatic complexity number (CCN), parameter count, token count, and non-comment lines of code (NLOC) across 20+ languages. | Does not analyze dependencies or detect copy/paste duplication. |
| **jscpd** (5.2.0) | Fast, language-agnostic clone and copy/paste detection across 224 programming languages. Outputs exact clone pairs, duplicate lines, and duplication percentages. | Does not analyze function complexity or semantic architecture. |
| **Valknut** (1.5.1) | Modern Rust-native refactoring and architectural health analyzer. Computes cognitive complexity, maintainability index, Halstead metrics, dependency cycles, chokepoints, and refactoring opportunities. | Supports Python, TypeScript, JavaScript, Rust, Go, C++. |

### What the System Deliberately Does NOT Measure
- **Runtime correctness or test coverage quality**: Use your testing framework (`pytest`, `cargo test`, `npm test`) for functional correctness.
- **Micro-optimizations / execution speed**: Use profilers or benchmarks for latency measurements.
- **Subjective formatting aesthetics**: Use formatters (`ruff`, `prettier`, `rustfmt`).

---

## Multidimensional Architecture Vector

The system never hides behind a single magical score. The MCP tools output and diff a full dimensional vector:

```
Lines of Code (NLOC):         +487
Files:                        +3
Functions:                    +11
Total Cyclomatic Complexity:  +23
Average Complexity:           +0.4
Max Function Complexity:      +14
Duplication Rate:             +0.7%
Clone Groups:                 +2
Dependency Cycles:            +0
Valknut Health Score:         -3.2
```

Changes are categorized into four states:
- `IMPROVED`: Measurable reduction in system complexity, resolved clone groups, or eliminated cycles.
- `NEUTRAL`: Expected growth with clean abstractions and no architectural degradation.
- `REGRESSION`: Accidental complexity, new clone groups, cyclomatic spikes (>15), or new dependency cycles.
- `UNKNOWN`: Analyzer unavailable; never falsely reported as healthy zero.

---

## Installation & Setup

### Prerequisites
- Python >= 3.11
- Node.js & npm (for Valknut and jscpd)
- Linux / macOS (native, zero Docker required)

### Quick Setup

```bash
# Clone and enter directory
cd refactoring

# Create virtual environment and install package
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# Install global analyzers (or let runners use npx automatically)
npm install -g --prefix ~/.local @sibyllinesoft/valknut jscpd
uv tool install lizard

# Register MCP server and Agent Skills in both Antigravity and Codex
.venv/bin/python scripts/register_mcp.py
```

### Verification
Run the smoke test and test suite:
```bash
.venv/bin/python scripts/smoke_test.py
.venv/bin/pytest -v tests/
```

---

## Assistant Integrations

Architecture Fitness works seamlessly with both **OpenAI Codex** (CLI and IDE extension) and **Google Antigravity**.

### Automatic Unified Setup
You can configure both Antigravity and Codex in a single command:
```bash
.venv/bin/python scripts/register_mcp.py
```
*(Pass `--codex-only` or `--antigravity-only` if you only want to register with one assistant).*

---

### 1. OpenAI Codex Integration (CLI & IDE Extension)

#### A. Automatic Registration via Script
Run:
```bash
.venv/bin/python scripts/register_mcp.py --codex-only
```
This automatically:
- Registers the MCP server globally in Codex (`~/.codex/config.toml` via `codex mcp add`)
- Writes project-level config (`.codex/config.toml`)
- Links all 3 architecture skills (`architecture-check`, `architecture-refactor`, `architecture-review`) into `~/.codex/skills/`
- Appends architecture fitness guidance to `~/.codex/AGENTS.md`

#### B. Manual CLI Registration
To register manually using the Codex CLI:
```bash
codex mcp add architecture_fitness \
  --env PYTHONPATH=/home/vega/Documents/git/local/agent-tools/refactoring/src \
  --env PATH=/home/vega/.local/bin:/usr/local/bin:/usr/bin:/bin \
  -- /home/vega/Documents/git/local/agent-tools/refactoring/.venv/bin/python -m architecture_fitness.mcp_server
```

#### C. Manual Config (`~/.codex/config.toml` or Project `.codex/config.toml`)
Alternatively, add the server definition directly to TOML configuration:
```toml
[mcp_servers.architecture_fitness]
command = "/home/vega/Documents/git/local/agent-tools/refactoring/.venv/bin/python"
args = ["-m", "architecture_fitness.mcp_server"]

[mcp_servers.architecture_fitness.env]
PYTHONPATH = "/home/vega/Documents/git/local/agent-tools/refactoring/src"
PATH = "/home/vega/.local/bin:/usr/local/bin:/usr/bin:/bin"
```

#### D. Global Skills Symlinks
Link the architecture skills into `~/.codex/skills/` so Codex can discover and invoke the skill workflows:
```bash
ln -sfn /home/vega/Documents/git/local/agent-tools/refactoring/.agents/skills/architecture-check ~/.codex/skills/architecture-check
ln -sfn /home/vega/Documents/git/local/agent-tools/refactoring/.agents/skills/architecture-refactor ~/.codex/skills/architecture-refactor
ln -sfn /home/vega/Documents/git/local/agent-tools/refactoring/.agents/skills/architecture-review ~/.codex/skills/architecture-review
```

#### E. Global & Project Agent Guidance (`AGENTS.md`)
- **Global**: Appended to `~/.codex/AGENTS.md` so any project worked on by Codex abides by benefit-of-the-doubt and regression-checking rules.
- **Repository**: A dedicated [AGENTS.md](file:///home/vega/Documents/git/local/agent-tools/refactoring/AGENTS.md) is included in the project root with test commands, MCP signatures, and discipline principles.

#### F. Using with the Codex IDE Extension
- The Codex VS Code extension automatically picks up MCP servers configured in `~/.codex/config.toml` and workspace `.codex/config.toml`.
- When prompting Codex in the IDE extension sidebar or composer, all 5 architecture tools (`architecture_baseline`, `architecture_measure`, `architecture_compare`, `architecture_hotspots`, `architecture_reuse_candidates`) are available for tool calls.
- Verify active server status anytime:
  ```bash
  codex mcp list
  codex mcp get architecture_fitness
  ```

---

### 2. Antigravity Integration

#### MCP Server Registration (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "architecture_fitness": {
      "command": "/home/vega/Documents/git/local/agent-tools/refactoring/.venv/bin/python",
      "args": ["-m", "architecture_fitness.mcp_server"],
      "env": {
        "PYTHONPATH": "/home/vega/Documents/git/local/agent-tools/refactoring/src",
        "PATH": "/home/vega/.local/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

#### Tool Schemas & Customizations
- Tool schemas are placed in `~/.gemini/antigravity-ide/mcp/architecture_fitness/*.json`.
- Skills are symlinked to `~/.gemini/config/skills/`.
- Rules are symlinked to `~/.gemini/config/rules/`.


---

## MCP Server Tools

The MCP server is registered under `architecture_fitness` and exposes 5 tools:

### 1. `architecture_baseline`
Establish or retrieve an architecture baseline.
- `repo_path`: Path to repository root.
- `name`: (Optional) Friendly name (e.g. `'pre-feature'`, `'release-1.0'`).
- Saves baseline data to `.fitness/baselines/<name>.json`.

### 2. `architecture_measure`
Run full measurement on current working tree.
- `repo_path`: Path to repository root.
- `target_paths`: (Optional) Subdirectories or specific files.
- `profile`: `'fast'`, `'balanced'`, or `'thorough'`.

### 3. `architecture_compare`
Compare current working tree against baseline.
- `repo_path`: Path to repository root.
- `baseline_name`: (Optional) Name or commit of baseline (defaults to latest/HEAD).
- `diff_aware`: `true` (default). Only blames changes on files and line ranges touched in the diff.

### 4. `architecture_hotspots`
Identify ranked architectural hotspots.
- `repo_path`: Path to repository root.
- `top_n`: Maximum items to return (default: `10`).
- Combines functions with CCN > 15, duplicate clusters, and dependency cycles.

### 5. `architecture_reuse_candidates`
Search for existing mechanisms before writing new abstractions.
- `repo_path`: Path to repository root.
- `query`: Description or symbol name of functionality to find.
- Returns candidate symbols with file locations, signatures, and match evidence.

---

## Repository Configuration

Configure `.fitness.toml` or `.architecture-fitness.json` in repository root (optional, defaults provided):

```toml
exclude_paths = [
    ".git/**",
    ".fitness/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/dist/**",
    "**/tests/**"
]

[thresholds]
max_function_ccn = 15
max_duplication_percentage_delta = 0.5
max_complexity_delta = 5.0
max_health_drop = 5.0
fail_on_cycles = true
new_clone_groups_allowed = 0
```

---

## Agent Skills

Three Agent Skills are included in `.agents/skills/`:

| Skill | Purpose |
|---|---|
| `architecture-check` | Feature implementation guide. Mandates checking existing architecture and reuse candidates before introducing new code. |
| `architecture-refactor` | Targeted technical debt cleanup. Ranks measurable hotspots and warns against "refactoring theater" (splitting files without reducing complexity). |
| `architecture-review` | Post-implementation audit. Analyzes the diff against baseline and provides a clear regression/improvement report. |

---

## End-to-End Walkthrough Example

### 1. Agent plans a feature: Adding token validation
Before implementing, the agent checks reuse candidates:
```json
call_mcp_tool(
  ServerName="architecture_fitness",
  ToolName="architecture_reuse_candidates",
  Arguments={"repo_path": ".", "query": "validate authentication token"}
)
```
*Result*: Discovers existing `verify_user_token(token)` in `auth/tokens.py`.

### 2. Bad Agent Implementation (Vibe Coding):
The agent ignores the candidate and writes a 40-line duplicated token validator with 18 nested `if` statements in a new file `utils/token_checker.py`.

### 3. Measurement & Diff-Aware Compare:
```
ARCHITECTURE RESULT: REGRESSION

Duplication:         0.6% -> 1.4%   (+0.80%)
Complexity (avg):     4.7 -> 5.3    (+0.60)
Max complexity:        40 -> 58     (+18)
Files:                 27 -> 28     (+1)
Functions:             94 -> 95     (+1)

Significant regressions:
  - Code duplication increased by +0.80%
  - New clone groups detected: +1
  - Maximum function complexity spiked by +18 (40 -> 58)

New problems introduced in this change:
  - New function 'validate_token_custom' introduced with excessive CCN=18
  - Duplicate logic (28 lines) touching modified file utils/token_checker.py

Suggested next action:
  Investigate the newly introduced complexity, clone groups, or dependency regressions before accepting this implementation.
```

### 4. Agent Revises Implementation:
The agent deletes `utils/token_checker.py`, imports `auth/tokens.py:verify_user_token`, and calls it directly.
Re-measuring:
```
ARCHITECTURE RESULT: NEUTRAL
Lines of Code: +4
Duplication: 0.6% -> 0.6% (+0.00%)
Max Complexity: 40 -> 40 (+0)
No new clone groups. No regressions.
```
The architecture remains pristine.
