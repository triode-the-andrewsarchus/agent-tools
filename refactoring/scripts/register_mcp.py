"""Register architecture_fitness MCP server, tool schemas, and skills in Antigravity and Codex."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
SRC_PATH = REPO_ROOT / "src"

# Antigravity / Gemini paths
GEMINI_CONFIG_DIR = Path.home() / ".gemini" / "config"
GEMINI_MCP_CONFIG = GEMINI_CONFIG_DIR / "mcp_config.json"
GEMINI_IDE_MCP_DIR = Path.home() / ".gemini" / "antigravity-ide" / "mcp" / "architecture_fitness"
GEMINI_SKILLS_DIR = GEMINI_CONFIG_DIR / "skills"
GEMINI_RULES_DIR = GEMINI_CONFIG_DIR / "rules"

# Codex paths
CODEX_HOME_DIR = Path.home() / ".codex"
CODEX_CONFIG_FILE = CODEX_HOME_DIR / "config.toml"
CODEX_SKILLS_DIR = CODEX_HOME_DIR / "skills"
CODEX_AGENTS_FILE = CODEX_HOME_DIR / "AGENTS.md"
PROJECT_CODEX_DIR = REPO_ROOT / ".codex"
PROJECT_CODEX_CONFIG = PROJECT_CODEX_DIR / "config.toml"

# Source skills and rules
SKILLS_SOURCE = REPO_ROOT / ".agents" / "skills"
RULES_SOURCE = REPO_ROOT / ".agents" / "rules"

PATH_ENV = f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin"


# ---------------------------------------------------------------------------
# Antigravity Registration
# ---------------------------------------------------------------------------


def register_antigravity_mcp() -> None:
    print("[Antigravity] Registering architecture_fitness in mcp_config.json...")
    config = {}
    if GEMINI_MCP_CONFIG.exists():
        try:
            with open(GEMINI_MCP_CONFIG, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    servers = config.setdefault("mcpServers", {})
    servers["architecture_fitness"] = {
        "command": str(VENV_PYTHON),
        "args": ["-m", "architecture_fitness.mcp_server"],
        "env": {
            "PYTHONPATH": str(SRC_PATH),
            "PATH": PATH_ENV,
        },
    }

    GEMINI_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(GEMINI_MCP_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"[Antigravity] Updated {GEMINI_MCP_CONFIG}")


def write_antigravity_tool_schemas() -> None:
    print(f"[Antigravity] Generating tool schemas in {GEMINI_IDE_MCP_DIR}...")
    GEMINI_IDE_MCP_DIR.mkdir(parents=True, exist_ok=True)

    instructions = (
        "Architecture Fitness provides local multidimensional architecture and complexity analysis "
        "using Lizard (cyclomatic complexity), jscpd (duplication detection), and Valknut (architecture/coupling). "
        "Use architecture_baseline to freeze a reference point, architecture_compare to inspect diff regressions, "
        "architecture_hotspots for targeted refactoring, and architecture_reuse_candidates to avoid redundant code."
    )
    with open(GEMINI_IDE_MCP_DIR / "instructions.md", "w", encoding="utf-8") as f:
        f.write(instructions)

    schemas = {
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
    }

    for name, schema in schemas.items():
        with open(GEMINI_IDE_MCP_DIR / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
    print(f"[Antigravity] Tool schemas created in {GEMINI_IDE_MCP_DIR}")


def symlink_antigravity_customizations() -> None:
    print("[Antigravity] Creating global skill and rule symlinks...")
    GEMINI_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    GEMINI_RULES_DIR.mkdir(parents=True, exist_ok=True)

    if SKILLS_SOURCE.exists():
        for skill_dir in SKILLS_SOURCE.iterdir():
            if skill_dir.is_dir():
                target = GEMINI_SKILLS_DIR / skill_dir.name
                if target.is_symlink() or target.exists():
                    target.unlink()
                target.symlink_to(skill_dir)
                print(f"[Antigravity] Linked skill: {target} -> {skill_dir}")

    if RULES_SOURCE.exists():
        for rule_file in RULES_SOURCE.glob("*.md"):
            target = GEMINI_RULES_DIR / rule_file.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(rule_file)
            print(f"[Antigravity] Linked rule: {target} -> {rule_file}")


# ---------------------------------------------------------------------------
# Codex Registration
# ---------------------------------------------------------------------------


def register_codex_mcp_server() -> None:
    print("[Codex] Registering architecture_fitness MCP server in Codex...")

    # 1. Project-level .codex/config.toml
    PROJECT_CODEX_DIR.mkdir(parents=True, exist_ok=True)
    project_config_content = f"""# Codex Project Configuration for Architecture Fitness

[mcp_servers.architecture_fitness]
command = "{VENV_PYTHON}"
args = ["-m", "architecture_fitness.mcp_server"]

[mcp_servers.architecture_fitness.env]
PYTHONPATH = "{SRC_PATH}"
PATH = "{PATH_ENV}"
"""
    with open(PROJECT_CODEX_CONFIG, "w", encoding="utf-8") as f:
        f.write(project_config_content)
    print(f"[Codex] Wrote project config to {PROJECT_CODEX_CONFIG}")

    # 2. Global Codex registration
    codex_bin = shutil.which("codex")
    if codex_bin:
        cmd = [
            codex_bin,
            "mcp",
            "add",
            "architecture_fitness",
            "--env",
            f"PYTHONPATH={SRC_PATH}",
            "--env",
            f"PATH={PATH_ENV}",
            "--",
            str(VENV_PYTHON),
            "-m",
            "architecture_fitness.mcp_server",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                print(f"[Codex] Registered globally via codex CLI: {res.stdout.strip()}")
                return
            else:
                print(f"[Codex] codex mcp add returned code {res.returncode}: {res.stderr.strip()}")
        except Exception as e:
            print(f"[Codex] Failed running codex CLI: {e}")

    # Fallback to direct ~/.codex/config.toml manipulation
    CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
    toml_snippet = f"""
[mcp_servers.architecture_fitness]
command = "{VENV_PYTHON}"
args = ["-m", "architecture_fitness.mcp_server"]

[mcp_servers.architecture_fitness.env]
PATH = "{PATH_ENV}"
PYTHONPATH = "{SRC_PATH}"
"""
    if CODEX_CONFIG_FILE.exists():
        with open(CODEX_CONFIG_FILE, "r", encoding="utf-8") as f:
            existing = f.read()
        if "[mcp_servers.architecture_fitness]" not in existing:
            with open(CODEX_CONFIG_FILE, "a", encoding="utf-8") as f:
                f.write(toml_snippet)
            print(f"[Codex] Appended server to {CODEX_CONFIG_FILE}")
        else:
            print(f"[Codex] Server already configured in {CODEX_CONFIG_FILE}")
    else:
        with open(CODEX_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(toml_snippet)
        print(f"[Codex] Created {CODEX_CONFIG_FILE}")


def symlink_codex_skills() -> None:
    print("[Codex] Linking skills into ~/.codex/skills/...")
    CODEX_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if SKILLS_SOURCE.exists():
        for skill_dir in SKILLS_SOURCE.iterdir():
            if skill_dir.is_dir():
                target = CODEX_SKILLS_DIR / skill_dir.name
                if target.is_symlink() or target.exists():
                    target.unlink()
                target.symlink_to(skill_dir)
                print(f"[Codex] Linked skill: {target} -> {skill_dir}")


def update_codex_agents_md() -> None:
    print("[Codex] Ensuring architecture fitness instructions in ~/.codex/AGENTS.md...")
    CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)

    section = """
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
   - Run `architecture_compare` after changes. If it reports `ARCHITECTURE RESULT: REGRESSION` (e.g. cyclomatic complexity spikes, new clone groups, or dependency cycles), revise the implementation to eliminate accidental complexity.
3. **Anti-Gaming Discipline**: Never optimize metrics artificially (e.g. moving code across files without simplifying logic, creating arbitrary one-line wrappers, or deleting necessary features). Seek genuine structural Pareto improvements.
"""
    if CODEX_AGENTS_FILE.exists():
        with open(CODEX_AGENTS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if "## Architecture Fitness & Complexity Control" not in content:
            with open(CODEX_AGENTS_FILE, "a", encoding="utf-8") as f:
                f.write(section)
            print(f"[Codex] Appended guidance to {CODEX_AGENTS_FILE}")
        else:
            print(f"[Codex] Guidance already present in {CODEX_AGENTS_FILE}")
    else:
        with open(CODEX_AGENTS_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Global Agent Instructions\n{section}")
        print(f"[Codex] Created {CODEX_AGENTS_FILE} with guidance")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Register Architecture Fitness MCP in Antigravity and Codex")
    parser.add_argument("--antigravity-only", action="store_true", help="Register only for Gemini / Antigravity")
    parser.add_argument("--codex-only", action="store_true", help="Register only for OpenAI Codex")
    args = parser.parse_args()

    run_antigravity = not args.codex_only
    run_codex = not args.antigravity_only

    if run_antigravity:
        print("=== Registering in Antigravity ===")
        register_antigravity_mcp()
        write_antigravity_tool_schemas()
        symlink_antigravity_customizations()
        print()

    if run_codex:
        print("=== Registering in Codex ===")
        register_codex_mcp_server()
        symlink_codex_skills()
        update_codex_agents_md()
        print()

    print("Setup complete! Both Antigravity and Codex (CLI & IDE extension) are now configured.")


if __name__ == "__main__":
    main()
