#!/usr/bin/env python3
"""Register id_tokenizer MCP server, tool schemas, and skills in Antigravity and Codex."""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root_installer = Path(__file__).resolve().parent.parent.parent / "install.py"
    cmd = [sys.executable, str(root_installer), "id_tokenizer"] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
