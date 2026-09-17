"""Runner for jscpd duplicate code detector."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import FitnessConfig
from ..models import DuplicateClone, DuplicateLocation, ToolStatus


class JscpdRunner:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def _get_executable(self) -> Optional[List[str]]:
        exe = shutil.which("jscpd")
        if exe:
            return [exe]
        npx = shutil.which("npx")
        if npx:
            return [npx, "-y", "jscpd"]
        return None

    def get_version(self) -> Optional[str]:
        cmd_prefix = self._get_executable()
        if not cmd_prefix:
            return None
        try:
            out = subprocess.check_output(cmd_prefix + ["--version"], text=True, stderr=subprocess.STDOUT)
            return out.strip()
        except Exception:
            return None

    def is_available(self) -> bool:
        return self._get_executable() is not None

    def run(self, repo_path: Path | str, target_paths: Optional[List[str]] = None) -> Tuple[ToolStatus, List[DuplicateClone], Dict[str, Any]]:
        t0 = time.perf_counter()
        root = Path(repo_path).resolve()
        cmd_prefix = self._get_executable()

        if not cmd_prefix:
            status = ToolStatus(
                name="jscpd",
                available=False,
                version=None,
                duration_seconds=0.0,
                error="jscpd is not installed and npx is unavailable. Install via 'npm install -g jscpd'.",
            )
            return status, [], {}

        ver = self.get_version()
        version = ver if isinstance(ver, str) else (str(ver) if ver is not None and not hasattr(ver, "_mock_return_value") else None)
        targets = [str(Path(p) if Path(p).is_absolute() else root / p) for p in target_paths] if target_paths else [str(root)]

        # Prepare ignore patterns
        ignore_patterns = list(self.config.exclude_paths)
        # Add output and temporary directories
        ignore_patterns.extend([".fitness/**", ".valknut/**", "**/temp/**"])
        ignore_arg = ",".join(ignore_patterns)

        with tempfile.TemporaryDirectory(prefix="jscpd_") as tmp_dir:
            cmd = cmd_prefix + targets + [
                "-r", "json",
                "-o", tmp_dir,
                "--silent",
                "--no-colors",
                "--exit-code", "0",
                "--ignore", ignore_arg,
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                duration = round(time.perf_counter() - t0, 3)
                report_path = Path(tmp_dir) / "jscpd-report.json"

                if not report_path.exists():
                    # If exit code was 0 but no duplicates found, check if it ran cleanly
                    if proc.returncode == 0:
                        status = ToolStatus(
                            name="jscpd",
                            available=True,
                            version=version,
                            duration_seconds=duration,
                        )
                        return status, [], {"total": {"percentage": 0.0, "clones": 0, "duplicatedLines": 0}}
                    else:
                        status = ToolStatus(
                            name="jscpd",
                            available=True,
                            version=version,
                            duration_seconds=duration,
                            error=f"jscpd exited with code {proc.returncode}: {proc.stderr}",
                        )
                        return status, [], {}

                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)

                duplicates: List[DuplicateClone] = []
                for item in report.get("duplicates", []):
                    ff = item.get("firstFile", {})
                    sf = item.get("secondFile", {})

                    f1_name = ff.get("name", "")
                    f2_name = sf.get("name", "")

                    # Make relative to root if needed
                    try:
                        p1 = Path(f1_name)
                        if p1.is_absolute():
                            f1_name = p1.relative_to(root).as_posix()
                    except ValueError:
                        pass

                    try:
                        p2 = Path(f2_name)
                        if p2.is_absolute():
                            f2_name = p2.relative_to(root).as_posix()
                    except ValueError:
                        pass

                    first_loc = DuplicateLocation(
                        name=f1_name,
                        start=ff.get("start", 0),
                        end=ff.get("end", 0),
                        lines=ff.get("end", 0) - ff.get("start", 0) + 1,
                    )
                    second_loc = DuplicateLocation(
                        name=f2_name,
                        start=sf.get("start", 0),
                        end=sf.get("end", 0),
                        lines=sf.get("end", 0) - sf.get("start", 0) + 1,
                    )

                    clone = DuplicateClone(
                        format=item.get("format", ""),
                        lines=item.get("lines", 0),
                        tokens=item.get("tokens", 0),
                        first_file=first_loc,
                        second_file=second_loc,
                        fragment=item.get("fragment"),
                    )
                    duplicates.append(clone)

                stats = report.get("statistics", {})
                status = ToolStatus(
                    name="jscpd",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                )

                return status, duplicates, stats

            except subprocess.TimeoutExpired:
                duration = round(time.perf_counter() - t0, 3)
                status = ToolStatus(
                    name="jscpd",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                    error="jscpd timed out after 120 seconds",
                )
                return status, [], {}
            except Exception as e:
                duration = round(time.perf_counter() - t0, 3)
                status = ToolStatus(
                    name="jscpd",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                    error=f"Error executing jscpd: {e}",
                )
                return status, [], {}
