"""Register architecture_fitness MCP server, tool schemas, and skills in Gemini/Antigravity."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
SRC_PATH = REPO_ROOT / "src"

GEMINI_CONFIG_DIR = Path.home() / ".gemini" / "config"
MCP_CONFIG_FILE = GEMINI_CONFIG_DIR / "mcp_config.json"
IDE_MCP_DIR = Path.home() / ".gemini" / "antigravity-ide" / "mcp" / "architecture_fitness"

SKILLS_SOURCE = REPO_ROOT / ".agents" / "skills"
RULES_SOURCE = REPO_ROOT / ".agents" / "rules"

GLOBAL_SKILLS_DIR = GEMINI_CONFIG_DIR / "skills"
GLOBAL_RULES_DIR = GEMINI_CONFIG_DIR / "rules"


def register_mcp_server() -> None:
    print("Registering architecture_fitness in mcp_config.json...")
    config = {}
    if MCP_CONFIG_FILE.exists():
        try:
            with open(MCP_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    servers = config.setdefault("mcpServers", {})
    servers["architecture_fitness"] = {
        "command": str(VENV_PYTHON),
        "args": ["-m", "architecture_fitness.mcp_server"],
        "env": {
            "PYTHONPATH": str(SRC_PATH),
            "PATH": f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin",
        },
    }

    with open(MCP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Updated {MCP_CONFIG_FILE}")


def write_tool_schemas() -> None:
    print(f"Generating tool schemas in {IDE_MCP_DIR}...")
    IDE_MCP_DIR.mkdir(parents=True, exist_ok=True)

    instructions = (
        "Architecture Fitness provides local multidimensional architecture and complexity analysis "
        "using Lizard (cyclomatic complexity), jscpd (duplication detection), and Valknut (architecture/coupling). "
        "Use architecture_baseline to freeze a reference point, architecture_compare to inspect diff regressions, "
        "architecture_hotspots for targeted refactoring, and architecture_reuse_candidates to avoid redundant code."
    )
    with open(IDE_MCP_DIR / "instructions.md", "w", encoding="utf-8") as f:
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
        with open(IDE_MCP_DIR / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
    print(f"Tool schemas created in {IDE_MCP_DIR}")


def symlink_customizations() -> None:
    print("Creating global skill and rule symlinks...")
    GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_RULES_DIR.mkdir(parents=True, exist_ok=True)

    for skill_dir in SKILLS_SOURCE.iterdir():
        if skill_dir.is_dir():
            target = GLOBAL_SKILLS_DIR / skill_dir.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(skill_dir)
            print(f"Linked skill: {target} -> {skill_dir}")

    for rule_file in RULES_SOURCE.glob("*.md"):
        target = GLOBAL_RULES_DIR / rule_file.name
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(rule_file)
        print(f"Linked rule: {target} -> {rule_file}")


def main() -> None:
    register_mcp_server()
    write_tool_schemas()
    symlink_customizations()
    print("\nRegistration complete! Restart or reload Antigravity to activate.")


if __name__ == "__main__":
    main()
