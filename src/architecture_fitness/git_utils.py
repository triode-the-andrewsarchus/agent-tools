"""Git utilities for repository inspection and diff-aware analysis."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class GitUtils:
    @staticmethod
    def is_git_repo(repo_path: Path | str) -> bool:
        root = Path(repo_path).resolve()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    @staticmethod
    def get_head_commit(repo_path: Path | str) -> Optional[str]:
        root = Path(repo_path).resolve()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def get_current_branch(repo_path: Path | str) -> Optional[str]:
        root = Path(repo_path).resolve()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
                return branch if branch != "HEAD" else None
        except Exception:
            pass
        return None

    @staticmethod
    def get_changed_files(repo_path: Path | str, base_ref: Optional[str] = None) -> List[str]:
        """Get list of changed, added, or untracked files relative to repo root."""
        root = Path(repo_path).resolve()
        if not GitUtils.is_git_repo(root):
            return []

        changed: Set[str] = set()

        try:
            if base_ref:
                # Diff against base_ref
                res = subprocess.run(
                    ["git", "diff", "--name-only", base_ref],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if line.strip():
                            changed.add(line.strip())

            # Always check git status for unstaged / untracked files
            res_status = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if res_status.returncode == 0:
                for line in res_status.stdout.splitlines():
                    line = line.strip()
                    if len(line) >= 3:
                        # format: XY filename or XY orig -> new
                        path_part = line[3:].strip()
                        if " -> " in path_part:
                            path_part = path_part.split(" -> ")[1].strip()
                        if not path_part.startswith(".fitness/") and not path_part.startswith(".valknut/"):
                            changed.add(path_part)
        except Exception:
            pass

        return sorted([f for f in changed if not f.startswith(".fitness/") and not f.startswith(".valknut/")])

    @staticmethod
    def get_diff_ranges(repo_path: Path | str, base_ref: Optional[str] = None) -> Dict[str, List[Tuple[int, int]]]:
        """
        Get modified line ranges for each changed file.
        Returns a dict mapping relative file path to list of (start_line, end_line) tuples.
        """
        root = Path(repo_path).resolve()
        if not GitUtils.is_git_repo(root):
            return {}

        ranges: Dict[str, List[Tuple[int, int]]] = {}
        cmd = ["git", "diff", "-U0"]
        if base_ref:
            cmd.append(base_ref)

        try:
            res = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                current_file = None
                for line in res.stdout.splitlines():
                    if line.startswith("+++ b/"):
                        current_file = line[6:].strip()
                        if current_file not in ranges:
                            ranges[current_file] = []
                    elif line.startswith("@@ ") and current_file:
                        # e.g., @@ -10,3 +12,5 @@ or @@ -5 +6 @@
                        m = re.search(r"\+(\d+)(?:,(\d+))?", line)
                        if m:
                            start = int(m.group(1))
                            count = int(m.group(2)) if m.group(2) else 1
                            end = start + max(count - 1, 0)
                            ranges[current_file].append((start, end))
        except Exception:
            pass

        # Also add untracked new files as spanning (1, 999999)
        try:
            res_status = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if res_status.returncode == 0:
                for line in res_status.stdout.splitlines():
                    if line.startswith("?? "):
                        untracked = line[3:].strip()
                        if untracked not in ranges:
                            ranges[untracked] = [(1, 999999)]
        except Exception:
            pass

        return ranges
