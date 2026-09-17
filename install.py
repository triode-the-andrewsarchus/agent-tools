#!/usr/bin/env python3
"""Unified installer for agent-tools (Local LLM, Pulpie, Architecture Fitness).

Supports granular and all-in-one installation for:
  - Google Antigravity (~/.gemini/)
  - OpenAI Codex (~/.codex/)

Usage:
  # Install all tools to all agents:
  python3 install.py --all

  # Install all tools to a specific agent:
  python3 install.py --agent antigravity --all
  python3 install.py --agent codex --all

  # Install a specific tool to a specific agent:
  python3 install.py --tool pulpie --agent codex
  python3 install.py --tool refactoring --agent antigravity
  python3 install.py local_llm --agent all

  # Check status across all agents:
  python3 install.py --status

  # Uninstall:
  python3 install.py --uninstall --tool pulpie --agent codex
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MONOREPO_ROOT = Path(__file__).resolve().parent
PATH_ENV = f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Antigravity paths
GEMINI_CONFIG_DIR = Path.home() / ".gemini" / "config"
GEMINI_MCP_CONFIG = GEMINI_CONFIG_DIR / "mcp_config.json"
GEMINI_SETTINGS_FILE = Path.home() / ".gemini" / "settings.json"
GEMINI_SKILLS_DIR = GEMINI_CONFIG_DIR / "skills"
GEMINI_RULES_DIR = GEMINI_CONFIG_DIR / "rules"
GEMINI_MCP_ROOTS = [
    Path.home() / ".gemini" / "antigravity" / "mcp",
    Path.home() / ".gemini" / "antigravity-ide" / "mcp",
    Path.home() / ".gemini" / "antigravity-cli" / "mcp",
]

# Codex paths
CODEX_HOME_DIR = Path.home() / ".codex"
CODEX_CONFIG_FILE = CODEX_HOME_DIR / "config.toml"
CODEX_SKILLS_DIR = CODEX_HOME_DIR / "skills"
CODEX_AGENTS_FILE = CODEX_HOME_DIR / "AGENTS.md"


@dataclass
class ToolDefinition:
    key: str  # internal key: local_llm, pulpie, refactoring
    mcp_name: str  # mcp server name: local_worker, pulpie, architecture_fitness
    subpath: str  # directory name: local_llm, pulpie, refactoring
    python_relpath: str
    src_relpath: str
    module_name: str
    env_vars: Dict[str, str] = field(default_factory=dict)
    skills_relpaths: List[str] = field(default_factory=list)
    rules_relpaths: List[str] = field(default_factory=list)
    instructions: str = ""
    schemas: Dict[str, Any] = field(default_factory=dict)
    codex_agents_guidance: str = ""

    @property
    def dir_path(self) -> Path:
        return MONOREPO_ROOT / self.subpath

    @property
    def python_path(self) -> Path:
        return self.dir_path / self.python_relpath

    @property
    def src_path(self) -> Path:
        return self.dir_path / self.src_relpath


# ---------------------------------------------------------------------------
# Tool Catalog
# ---------------------------------------------------------------------------


def get_tools_catalog() -> Dict[str, ToolDefinition]:
    return {
        "local_llm": ToolDefinition(
            key="local_llm",
            mcp_name="local_worker",
            subpath="local_llm",
            python_relpath=".venv/bin/python",
            src_relpath="src",
            module_name="local_worker.mcp_server",
            env_vars={
                "PYTHONPATH": str(MONOREPO_ROOT / "local_llm" / "src"),
                "LOCAL_WORKER_PROFILES": str(MONOREPO_ROOT / "local_llm" / "worker_profiles.toml"),
                "LOCAL_WORKER_DB": str(Path.home() / ".local" / "share" / "local-worker" / "jobs.db"),
                "LMS_BASE_URL": "http://localhost:1234",
                "LMS_CLI": str(Path.home() / ".lmstudio" / "bin" / "lms"),
            },
            skills_relpaths=[".agents/skills/local-workers"],
            rules_relpaths=[".agents/rules/local_workers.md"],
            instructions=(
                "Local LLM worker pool. Use worker_submit to delegate tasks to local models, "
                "worker_status to retrieve results, and scheduler_status to check availability. "
                "Worker classes: 'cheap' (Qwen3.5-9B, parallel) or 'smart' (Qwen3.6-27B, high quality)."
            ),
            schemas={
                "worker_submit": {
                    "name": "worker_submit",
                    "description": (
                        "Submit a task to a local LLM worker. Returns a job_id immediately — "
                        "use worker_status to poll for the result. Use worker_class='cheap' for "
                        "fast/parallel tasks (Qwen3.5-9B, batches up to 2 concurrent); use 'smart' "
                        "for complex reasoning (Qwen3.6-27B, sequential). The scheduler manages GPU "
                        "allocation and model switching automatically. Do NOT specify a model name or "
                        "GPU — use worker_class only."
                    ),
                    "parameters": {
                        "type": "object",
                        "title": "worker_submitArguments",
                        "properties": {
                            "prompt": {"type": "string", "title": "Prompt"},
                            "worker_class": {"type": "string", "title": "Worker Class"},
                            "context_hint": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Context Hint"},
                            "max_output_tokens": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None, "title": "Max Output Tokens"},
                            "priority": {"type": "integer", "default": 5, "title": "Priority"},
                            "system_prompt": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "System Prompt"},
                            "timeout_seconds": {"anyOf": [{"type": "number"}, {"type": "null"}], "default": None, "title": "Timeout Seconds"},
                        },
                        "required": ["worker_class", "prompt"],
                    },
                },
                "worker_status": {
                    "name": "worker_status",
                    "description": (
                        "Get the current status and result of a submitted job. Poll until status is not "
                        "'queued' or 'running'. On 'context_exhausted', check handoff_summary for compact "
                        "findings. On 'completed', check result_text."
                    ),
                    "parameters": {
                        "type": "object",
                        "title": "worker_statusArguments",
                        "properties": {"job_id": {"type": "string", "title": "Job Id"}},
                        "required": ["job_id"],
                    },
                },
                "worker_cancel": {
                    "name": "worker_cancel",
                    "description": "Cancel a queued or running job by job_id.",
                    "parameters": {
                        "type": "object",
                        "title": "worker_cancelArguments",
                        "properties": {"job_id": {"type": "string", "title": "Job Id"}},
                        "required": ["job_id"],
                    },
                },
                "worker_list": {
                    "name": "worker_list",
                    "description": "List recent jobs with optional filters. Use to inspect what is queued, running, or recently completed.",
                    "parameters": {
                        "type": "object",
                        "title": "worker_listArguments",
                        "properties": {
                            "limit": {"type": "integer", "default": 20, "title": "Limit"},
                            "status": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Status"},
                            "worker_class": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Worker Class"},
                        },
                    },
                },
                "scheduler_status": {
                    "name": "scheduler_status",
                    "description": (
                        "Get the current scheduler state: mode (idle/cheap_ready/smart_ready/etc.), "
                        "loaded model, queue depths, running job count, free VRAM MB, and uptime. "
                        "Check lm_studio_reachable before submitting important jobs."
                    ),
                    "parameters": {"type": "object", "title": "scheduler_statusArguments", "properties": {}},
                },
            },
            codex_agents_guidance="""
---

## Local LLM Worker Pool
You have access to a local LLM worker pool via the `local_worker` MCP server.
Workers run locally via LM Studio:
- `cheap` (Qwen3.5-9B): Fast extraction, classification, code inspection, candidate generation.
- `smart` (Qwen3.6-27B): Complex reasoning, difficult code analysis, high-stakes tasks.

### Available Tools
- `worker_submit(worker_class, prompt, context_hint=None)`: Submits a job asynchronously and returns a `job_id`.
- `worker_status(job_id)`: Checks job progress and retrieves results.
- `scheduler_status()`: Inspects queue depth, GPU VRAM headroom, and worker availability.
- `worker_cancel(job_id)`: Cancels queued or running job.
- `worker_list(limit=20)`: Lists recent jobs.
""",
        ),
        "pulpie": ToolDefinition(
            key="pulpie",
            mcp_name="pulpie",
            subpath="pulpie",
            python_relpath=".venv/bin/python",
            src_relpath="src",
            module_name="pulpie_service.mcp_server",
            env_vars={
                "PYTHONPATH": str(MONOREPO_ROOT / "pulpie" / "src"),
            },
            skills_relpaths=[".agents/skills/pulpie-extractor"],
            rules_relpaths=[".agents/rules/pulpie_preprocessing.md"],
            instructions=(
                "Pulpie is a local web-content extraction and preprocessing service. "
                "It removes web boilerplate (navigation, headers, footers, ads) while preserving "
                "document structure (headings, tables, code blocks, math formulas, links). "
                "Use clean_html or clean_web_page before passing web content into downstream LLMs."
            ),
            schemas={
                "clean_html": {
                    "name": "clean_html",
                    "description": (
                        "Clean raw HTML using Pulpie Orange Small. Removes headers, footers, navigation, "
                        "sidebars, and ads while preserving headings, paragraphs, lists, tables, code blocks, "
                        "links, and formulas. Returns clean semantic Markdown or HTML along with compression "
                        "and token-saving metrics."
                    ),
                    "parameters": {
                        "type": "object",
                        "title": "clean_htmlArguments",
                        "properties": {
                            "html": {"type": "string", "title": "Html"},
                            "output_format": {"type": "string", "default": "markdown", "title": "Output Format"},
                            "fallback": {"type": "boolean", "default": True, "title": "Fallback"},
                        },
                        "required": ["html"],
                    },
                },
                "clean_web_page": {
                    "name": "clean_web_page",
                    "description": (
                        "Fetch a URL and clean its content using Pulpie. Convenience tool combining "
                        "HTTP fetching with Pulpie preprocessing. Returns cleaned semantic Markdown "
                        "with boilerplate removed and structured elements preserved."
                    ),
                    "parameters": {
                        "type": "object",
                        "title": "clean_web_pageArguments",
                        "properties": {
                            "url": {"type": "string", "title": "Url"},
                            "output_format": {"type": "string", "default": "markdown", "title": "Output Format"},
                            "timeout_seconds": {"type": "number", "default": 15.0, "title": "Timeout Seconds"},
                            "fallback": {"type": "boolean", "default": True, "title": "Fallback"},
                        },
                        "required": ["url"],
                    },
                },
                "pulpie_status": {
                    "name": "pulpie_status",
                    "description": (
                        "Check Pulpie service health, model status, GPU VRAM usage, and availability. "
                        "Pulpie runs independently from local LLM reasoning workers."
                    ),
                    "parameters": {"type": "object", "title": "pulpie_statusArguments", "properties": {}},
                },
                "pulpie_preload": {
                    "name": "pulpie_preload",
                    "description": (
                        "Explicitly preload the Pulpie model weights into memory (GPU or CPU) so "
                        "subsequent extraction requests experience zero cold-start latency."
                    ),
                    "parameters": {"type": "object", "title": "pulpie_preloadArguments", "properties": {}},
                },
            },
            codex_agents_guidance="""
---

## Web Content Preprocessing with Pulpie
You have access to a local web content preprocessing MCP service via the `pulpie` MCP server.

### Available Tools
- `clean_html(html, output_format="markdown", fallback=true)`: Cleans raw HTML string. Strips headers, navigation menus, ads, sidebars, cookie banners, tracking scripts, and footers while strictly preserving document headings, body text, tables, code blocks, math formulas, and links.
- `clean_web_page(url, output_format="markdown", timeout_seconds=15.0)`: Fetches a web page and returns cleaned Markdown or HTML in a single call.
- `pulpie_status()`: Returns service health, loaded model status, device (`cuda`/`cpu`), and VRAM allocations.
- `pulpie_preload()`: Preloads neural model weights to avoid first-run latency.

### Policy & Best Practices
1. **Preprocess Web Pages**: Whenever fetching raw HTML or reading web pages that contain noisy navigation, boilerplate, or advertising, preprocess them with `clean_html` or `clean_web_page` before placing the content into your context window or downstream reasoning.
2. **Resource Independence**: Pulpie runs a lightweight neural encoder (~420 MB VRAM or CPU) decoupled from LLM inference. It does not interfere with model slots or reasoning workers.
""",
        ),
        "refactoring": ToolDefinition(
            key="refactoring",
            mcp_name="architecture_fitness",
            subpath="refactoring",
            python_relpath=".venv/bin/python",
            src_relpath="src",
            module_name="architecture_fitness.mcp_server",
            env_vars={
                "PYTHONPATH": str(MONOREPO_ROOT / "refactoring" / "src"),
                "PATH": PATH_ENV,
            },
            skills_relpaths=[
                ".agents/skills/architecture-check",
                ".agents/skills/architecture-refactor",
                ".agents/skills/architecture-review",
            ],
            rules_relpaths=[".agents/rules/architecture_fitness.md"],
            instructions=(
                "Architecture Fitness provides local multidimensional architecture and complexity analysis "
                "using Lizard (cyclomatic complexity), jscpd (duplication detection), and Valknut (architecture/coupling). "
                "Use architecture_baseline to freeze a reference point, architecture_compare to inspect diff regressions, "
                "architecture_hotspots for targeted refactoring, and architecture_reuse_candidates to avoid redundant code."
            ),
            schemas={
                "architecture_baseline": {
                    "name": "architecture_baseline",
                    "description": "Establish or retrieve an architecture baseline for the current repository.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Absolute path to repository root"},
                            "name": {"type": "string", "description": "Optional baseline name"},
                            "profile": {"type": "string", "default": "fast", "description": "Performance profile"},
                        },
                        "required": ["repo_path"],
                    },
                },
                "architecture_measure": {
                    "name": "architecture_measure",
                    "description": "Run all relevant architecture measurements against the working tree.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Absolute path to repository root"},
                            "target_paths": {"type": "array", "items": {"type": "string"}, "description": "Optional subdirectories/files"},
                            "profile": {"type": "string", "default": "fast", "description": "Performance profile"},
                        },
                        "required": ["repo_path"],
                    },
                },
                "architecture_compare": {
                    "name": "architecture_compare",
                    "description": "Compare current working tree against baseline, distinguishing newly introduced problems from existing debt.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Absolute path to repository root"},
                            "baseline_name": {"type": "string", "description": "Optional baseline name or commit"},
                            "diff_aware": {"type": "boolean", "default": True, "description": "Whether to correlate with git diff"},
                            "profile": {"type": "string", "default": "fast", "description": "Performance profile"},
                        },
                        "required": ["repo_path"],
                    },
                },
                "architecture_hotspots": {
                    "name": "architecture_hotspots",
                    "description": "Identify ranked structural hotspots (high CCN, duplicate clusters, cycles).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Absolute path to repository root"},
                            "top_n": {"type": "integer", "default": 10, "description": "Max hotspots to return"},
                            "criteria": {"type": "string", "description": "Filter by complexity, duplication, cycle"},
                            "profile": {"type": "string", "default": "fast", "description": "Performance profile"},
                        },
                        "required": ["repo_path"],
                    },
                },
                "architecture_reuse_candidates": {
                    "name": "architecture_reuse_candidates",
                    "description": "Search repository for existing mechanisms/symbols that may provide equivalent functionality before adding new code.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Absolute path to repository root"},
                            "query": {"type": "string", "description": "Description of functionality or proposed symbol name"},
                            "context": {"type": "string", "description": "Optional parameters or domain context"},
                            "top_n": {"type": "integer", "default": 5, "description": "Max candidates to return"},
                        },
                        "required": ["repo_path", "query"],
                    },
                },
            },
            codex_agents_guidance="""
---

## Architecture Fitness & Complexity Control
You have access to local multidimensional architecture and complexity analysis tools via the `architecture_fitness` MCP server.

### Available Tools
- `architecture_baseline(repo_path, name=None, profile="fast")`: Establish or retrieve an architecture baseline for a repository.
- `architecture_measure(repo_path, target_paths=None, profile="fast")`: Run all architecture measurements (Lizard CCN/NLOC, jscpd duplication, Valknut structural metrics) against the working tree.
- `architecture_compare(repo_path, baseline_name=None, diff_aware=true, profile="fast")`: Compare current working tree against baseline, isolating newly introduced regressions from pre-existing technical debt.
- `architecture_hotspots(repo_path, top_n=10, criteria=None, profile="fast")`: Identify ranked structural hotspots (CCN > 15, duplicate clusters, dependency cycles).
- `architecture_reuse_candidates(repo_path, query, context=None, top_n=5)`: Search the repository for pre-existing symbols or mechanisms before adding new code.

### Policy & Rules of Engagement
1. **Benefit of the Doubt**: New mechanisms require justification; existing mechanisms get the benefit of the doubt. Before writing new functions, utilities, or abstractions, call `architecture_reuse_candidates` to check if similar functionality already exists.
2. **Measure Before & After**:
   - Establish a baseline with `architecture_baseline` before implementing significant features or refactoring.
   - Run `architecture_compare` after changes. If it reports `ARCHITECTURE RESULT: REGRESSION`, revise the implementation to eliminate accidental complexity.
3. **Anti-Gaming Discipline**: Never optimize metrics artificially. Seek genuine structural Pareto improvements.
""",
        ),
    }


# Normalize aliases
ALIASES = {
    "local_worker": "local_llm",
    "local-worker": "local_llm",
    "local-workers": "local_llm",
    "local": "local_llm",
    "architecture_fitness": "refactoring",
    "architecture-fitness": "refactoring",
    "architecture": "refactoring",
}


def resolve_tool_key(name: str) -> Optional[str]:
    name_clean = name.strip().lower().replace("-", "_")
    catalog = get_tools_catalog()
    if name_clean in catalog:
        return name_clean
    alias = ALIASES.get(name_clean) or ALIASES.get(name.strip().lower())
    if alias and alias in catalog:
        return alias
    return None


# ---------------------------------------------------------------------------
# Antigravity Operations
# ---------------------------------------------------------------------------


def install_antigravity(tool: ToolDefinition) -> None:
    print(f"[Antigravity] Installing '{tool.key}' ({tool.mcp_name})...")

    # 1. Update ~/.gemini/config/mcp_config.json
    config = {}
    if GEMINI_MCP_CONFIG.exists():
        try:
            with open(GEMINI_MCP_CONFIG, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
    servers = config.setdefault("mcpServers", {})
    servers[tool.mcp_name] = {
        "command": str(tool.python_path),
        "args": ["-m", tool.module_name],
        "env": tool.env_vars,
    }
    GEMINI_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(GEMINI_MCP_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"  * Updated {GEMINI_MCP_CONFIG} -> {tool.mcp_name}")

    if GEMINI_SETTINGS_FILE.exists():
        try:
            with open(GEMINI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
            s_servers = settings_data.setdefault("mcpServers", {})
            if tool.mcp_name in s_servers:
                s_servers[tool.mcp_name] = {
                    "command": str(tool.python_path),
                    "args": ["-m", tool.module_name],
                    "env": tool.env_vars,
                }
                with open(GEMINI_SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings_data, f, indent=2)
                print(f"  * Updated {GEMINI_SETTINGS_FILE} -> {tool.mcp_name}")
        except Exception as e:
            print(f"  ! Warning: could not update {GEMINI_SETTINGS_FILE}: {e}")

    # 2. Generate tool schemas in ~/.gemini/antigravity*/mcp/<mcp_name>/
    for root_dir in GEMINI_MCP_ROOTS:
        dest_dir = root_dir / tool.mcp_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        if tool.instructions:
            with open(dest_dir / "instructions.md", "w", encoding="utf-8") as f:
                f.write(tool.instructions)
        for schema_name, schema_content in tool.schemas.items():
            with open(dest_dir / f"{schema_name}.json", "w", encoding="utf-8") as f:
                json.dump(schema_content, f, indent=2)
    print(f"  * Generated schemas across {len(GEMINI_MCP_ROOTS)} Antigravity MCP root locations")

    # 3. Symlink skills
    GEMINI_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for skill_rel in tool.skills_relpaths:
        src = tool.dir_path / skill_rel
        if src.exists():
            target = GEMINI_SKILLS_DIR / src.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(src)
            print(f"  * Linked skill: {target} -> {src}")

    # 4. Symlink rules
    GEMINI_RULES_DIR.mkdir(parents=True, exist_ok=True)
    for rule_rel in tool.rules_relpaths:
        src = tool.dir_path / rule_rel
        if src.exists():
            target = GEMINI_RULES_DIR / src.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(src)
            print(f"  * Linked rule: {target} -> {src}")


def uninstall_antigravity(tool: ToolDefinition) -> None:
    print(f"[Antigravity] Uninstalling '{tool.key}' ({tool.mcp_name})...")

    # 1. Remove from mcp_config.json
    if GEMINI_MCP_CONFIG.exists():
        try:
            with open(GEMINI_MCP_CONFIG, "r", encoding="utf-8") as f:
                config = json.load(f)
            servers = config.get("mcpServers", {})
            if tool.mcp_name in servers:
                del servers[tool.mcp_name]
                with open(GEMINI_MCP_CONFIG, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                print(f"  * Removed {tool.mcp_name} from {GEMINI_MCP_CONFIG}")
        except Exception as e:
            print(f"  ! Error updating {GEMINI_MCP_CONFIG}: {e}")

    if GEMINI_SETTINGS_FILE.exists():
        try:
            with open(GEMINI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
            s_servers = settings_data.get("mcpServers", {})
            if tool.mcp_name in s_servers:
                del s_servers[tool.mcp_name]
                with open(GEMINI_SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings_data, f, indent=2)
                print(f"  * Removed {tool.mcp_name} from {GEMINI_SETTINGS_FILE}")
        except Exception as e:
            pass

    # 2. Remove schemas
    for root_dir in GEMINI_MCP_ROOTS:
        dest_dir = root_dir / tool.mcp_name
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
            print(f"  * Removed schema dir {dest_dir}")

    # 3. Remove skill symlinks
    for skill_rel in tool.skills_relpaths:
        skill_name = Path(skill_rel).name
        target = GEMINI_SKILLS_DIR / skill_name
        if target.is_symlink() or target.exists():
            target.unlink()
            print(f"  * Removed skill link {target}")

    # 4. Remove rule symlinks
    for rule_rel in tool.rules_relpaths:
        rule_name = Path(rule_rel).name
        target = GEMINI_RULES_DIR / rule_name
        if target.is_symlink() or target.exists():
            target.unlink()
            print(f"  * Removed rule link {target}")


# ---------------------------------------------------------------------------
# Codex Operations
# ---------------------------------------------------------------------------


def install_codex(tool: ToolDefinition) -> None:
    print(f"[Codex] Installing '{tool.key}' ({tool.mcp_name})...")

    # 1. Project-level config inside component directory
    proj_codex_dir = tool.dir_path / ".codex"
    proj_codex_dir.mkdir(parents=True, exist_ok=True)
    proj_lines = [
        f"# Codex Project Configuration for {tool.mcp_name}",
        f"[mcp_servers.{tool.mcp_name}]",
        f'command = "{tool.python_path}"',
        f'args = ["-m", "{tool.module_name}"]',
        f"",
        f"[mcp_servers.{tool.mcp_name}.env]",
    ]
    for k, v in tool.env_vars.items():
        proj_lines.append(f'{k} = "{v}"')
    proj_lines.append("")
    with open(proj_codex_dir / "config.toml", "w", encoding="utf-8") as f:
        f.write("\n".join(proj_lines))

    # 2. Global Codex registration via CLI if available, else ~/.codex/config.toml
    codex_bin = shutil.which("codex")
    registered_via_cli = False
    if codex_bin:
        # Remove old if exists
        subprocess.run([codex_bin, "mcp", "remove", tool.mcp_name], capture_output=True, check=False)
        cmd = [codex_bin, "mcp", "add", tool.mcp_name]
        for k, v in tool.env_vars.items():
            cmd.extend(["--env", f"{k}={v}"])
        cmd.extend(["--", str(tool.python_path), "-m", tool.module_name])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                print(f"  * Registered via codex CLI: {tool.mcp_name}")
                registered_via_cli = True
            else:
                print(f"  ! codex mcp add returned code {res.returncode}: {res.stderr.strip()}")
        except Exception as e:
            print(f"  ! Failed running codex CLI: {e}")

    if not registered_via_cli:
        # Fallback to direct ~/.codex/config.toml modification
        _write_codex_toml(tool)

    # 3. Symlink skills to ~/.codex/skills/
    CODEX_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for skill_rel in tool.skills_relpaths:
        src = tool.dir_path / skill_rel
        if src.exists():
            target = CODEX_SKILLS_DIR / src.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(src)
            print(f"  * Linked skill: {target} -> {src}")

    # 4. Global Codex AGENTS.md instructions
    if tool.codex_agents_guidance:
        CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
        existing = ""
        if CODEX_AGENTS_FILE.exists():
            with open(CODEX_AGENTS_FILE, "r", encoding="utf-8") as f:
                existing = f.read()

        header = tool.codex_agents_guidance.strip().splitlines()[1]  # e.g. "## Web Content Preprocessing"
        if header not in existing:
            with open(CODEX_AGENTS_FILE, "a", encoding="utf-8") as f:
                if not existing.strip():
                    f.write("# Global Agent Instructions\n")
                f.write(tool.codex_agents_guidance)
            print(f"  * Added guidance to {CODEX_AGENTS_FILE}")
        else:
            print(f"  * Guidance already present in {CODEX_AGENTS_FILE}")


def uninstall_codex(tool: ToolDefinition) -> None:
    print(f"[Codex] Uninstalling '{tool.key}' ({tool.mcp_name})...")

    # 1. Remove via CLI if available
    codex_bin = shutil.which("codex")
    if codex_bin:
        subprocess.run([codex_bin, "mcp", "remove", tool.mcp_name], capture_output=True, check=False)
        print(f"  * Removed {tool.mcp_name} via codex CLI")

    # 2. Clean from ~/.codex/config.toml
    _remove_codex_toml(tool)

    # 3. Remove skill symlinks
    for skill_rel in tool.skills_relpaths:
        skill_name = Path(skill_rel).name
        target = CODEX_SKILLS_DIR / skill_name
        if target.is_symlink() or target.exists():
            target.unlink()
            print(f"  * Removed skill link {target}")


def _write_codex_toml(tool: ToolDefinition) -> None:
    CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
    section_tag = f"[mcp_servers.{tool.mcp_name}]"
    lines = [
        "",
        section_tag,
        f'command = "{tool.python_path}"',
        f'args = ["-m", "{tool.module_name}"]',
        "",
        f"[mcp_servers.{tool.mcp_name}.env]",
    ]
    for k, v in tool.env_vars.items():
        lines.append(f'{k} = "{v}"')
    lines.append("")
    snippet = "\n".join(lines)

    if CODEX_CONFIG_FILE.exists():
        with open(CODEX_CONFIG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if section_tag not in content:
            with open(CODEX_CONFIG_FILE, "a", encoding="utf-8") as f:
                f.write(snippet)
            print(f"  * Appended {tool.mcp_name} to {CODEX_CONFIG_FILE}")
        else:
            print(f"  * Server already in {CODEX_CONFIG_FILE}")
    else:
        with open(CODEX_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(snippet)
        print(f"  * Created {CODEX_CONFIG_FILE}")


def _remove_codex_toml(tool: ToolDefinition) -> None:
    if not CODEX_CONFIG_FILE.exists():
        return
    with open(CODEX_CONFIG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    section_prefix = f"[mcp_servers.{tool.mcp_name}]"
    env_prefix = f"[mcp_servers.{tool.mcp_name}.env]"

    new_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == section_prefix or stripped == env_prefix:
            skip = True
            continue
        if skip and stripped.startswith("[") and not stripped.startswith(f"[mcp_servers.{tool.mcp_name}"):
            skip = False
        if not skip:
            new_lines.append(line)

    with open(CODEX_CONFIG_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"  * Cleaned section from {CODEX_CONFIG_FILE}")


# ---------------------------------------------------------------------------
# Status Inspection
# ---------------------------------------------------------------------------


def print_status() -> None:
    catalog = get_tools_catalog()
    print("================================================================================")
    print("                      AGENT-TOOLS INSTALLATION STATUS                           ")
    print("================================================================================")
    print(f"Monorepo Root: {MONOREPO_ROOT}\n")

    # Antigravity config
    agy_servers = {}
    if GEMINI_MCP_CONFIG.exists():
        try:
            with open(GEMINI_MCP_CONFIG, "r", encoding="utf-8") as f:
                agy_servers = json.load(f).get("mcpServers", {})
        except Exception:
            pass

    # Codex config
    cdx_servers = {}
    if CODEX_CONFIG_FILE.exists():
        try:
            with open(CODEX_CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            for key in catalog:
                mcp = catalog[key].mcp_name
                if f"[mcp_servers.{mcp}]" in content:
                    cdx_servers[mcp] = True
        except Exception:
            pass

    for key, tool in catalog.items():
        print(f"--- [{key.upper()}] (MCP: {tool.mcp_name}) ---")
        venv_ok = tool.python_path.exists()
        print(f"  Subdirectory:    {tool.dir_path} ({'EXISTS' if tool.dir_path.exists() else 'MISSING'})")
        print(f"  Python venv:     {tool.python_path} ({'READY' if venv_ok else 'MISSING'})")

        # Antigravity status
        agy_reg = tool.mcp_name in agy_servers
        agy_cmd = agy_servers.get(tool.mcp_name, {}).get("command") if agy_reg else None
        agy_path_match = agy_cmd == str(tool.python_path) if agy_cmd else False
        agy_skills_ok = all((GEMINI_SKILLS_DIR / Path(s).name).is_symlink() for s in tool.skills_relpaths)
        agy_rules_ok = all((GEMINI_RULES_DIR / Path(r).name).is_symlink() for r in tool.rules_relpaths)
        print(
            f"  Antigravity:     Registered={'YES' if agy_reg else 'NO'} | "
            f"Path={'CORRECT' if agy_path_match else ('OUTDATED' if agy_reg else 'N/A')} | "
            f"Skills={'OK' if agy_skills_ok else 'MISSING'} | "
            f"Rules={'OK' if agy_rules_ok else 'MISSING'}"
        )

        # Codex status
        cdx_reg = tool.mcp_name in cdx_servers
        cdx_skills_ok = all((CODEX_SKILLS_DIR / Path(s).name).is_symlink() for s in tool.skills_relpaths)
        print(
            f"  Codex:           Registered={'YES' if cdx_reg else 'NO'} | "
            f"Skills={'OK' if cdx_skills_ok else 'MISSING'}"
        )
        print()


# ---------------------------------------------------------------------------
# CLI Parser
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Installer for Agent-Tools (Google Antigravity & OpenAI Codex)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "tool_pos",
        nargs="?",
        default=None,
        help="Optional positional tool name: local_llm, pulpie, refactoring (or 'all')",
    )
    parser.add_argument(
        "--tool",
        "-t",
        choices=["local_llm", "pulpie", "refactoring", "all"],
        default=None,
        help="Tool to install or manage",
    )
    parser.add_argument(
        "--agent",
        "-a",
        choices=["antigravity", "codex", "all"],
        default="all",
        help="Target agent platform (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install all tools across the selected agent(s)",
    )
    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Display current installation status across all tools and agents",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall the specified tool(s) from target agent(s)",
    )

    args = parser.parse_args()

    if args.status:
        print_status()
        return

    catalog = get_tools_catalog()

    # Determine tool target
    raw_tool = args.tool or args.tool_pos
    if args.all or raw_tool in ("all", "*"):
        target_tools = list(catalog.values())
    elif raw_tool:
        resolved = resolve_tool_key(raw_tool)
        if not resolved or resolved not in catalog:
            print(f"Error: Unknown tool '{raw_tool}'. Available: {list(catalog.keys())}")
            sys.exit(1)
        target_tools = [catalog[resolved]]
    else:
        # Default with no arguments: show help and status
        print_status()
        print("Tip: Run './install.py --all' to install all tools to both Antigravity and Codex.")
        print("     Run './install.py --help' for full options.\n")
        return

    agents = ["antigravity", "codex"] if args.agent == "all" else [args.agent]

    action_label = "Uninstalling" if args.uninstall else "Installing"
    tools_label = ", ".join(t.key for t in target_tools)
    agents_label = ", ".join(agents)
    print(f"\n>>> {action_label} [{tools_label}] for agent(s): [{agents_label}] <<<\n")

    for tool in target_tools:
        if "antigravity" in agents:
            if args.uninstall:
                uninstall_antigravity(tool)
            else:
                install_antigravity(tool)

        if "codex" in agents:
            if args.uninstall:
                uninstall_codex(tool)
            else:
                install_codex(tool)

    print("\n[Done] Operation completed successfully.")
    print("Run './install.py --status' anytime to check installation health.\n")


if __name__ == "__main__":
    main()
