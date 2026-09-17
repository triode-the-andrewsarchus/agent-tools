"""Runner for Valknut architecture & complexity analyzer."""

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
from ..models import StructuralFinding, ToolStatus


class ValknutRunner:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def _get_executable(self) -> Optional[List[str]]:
        exe = shutil.which("valknut")
        if exe:
            return [exe]
        npx = shutil.which("npx")
        if npx:
            return [npx, "-y", "@sibyllinesoft/valknut"]
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

    def run(self, repo_path: Path | str, target_paths: Optional[List[str]] = None, profile: Optional[str] = None) -> Tuple[ToolStatus, List[StructuralFinding], Dict[str, Any]]:
        t0 = time.perf_counter()
        root = Path(repo_path).resolve()
        cmd_prefix = self._get_executable()

        if not cmd_prefix:
            status = ToolStatus(
                name="valknut",
                available=False,
                version=None,
                duration_seconds=0.0,
                error="Valknut is not installed and npx is unavailable. Install via 'npm install -g @sibyllinesoft/valknut'.",
            )
            return status, [], {}

        ver = self.get_version()
        version = ver if isinstance(ver, str) else (str(ver) if ver is not None and not hasattr(ver, "_mock_return_value") else None)
        chosen_profile = profile or self.config.profile or "fast"
        targets = [str(Path(p) if Path(p).is_absolute() else root / p) for p in target_paths] if target_paths else [str(root)]

        with tempfile.TemporaryDirectory(prefix="valknut_") as tmp_dir:
            cmd = cmd_prefix + ["analyze"] + targets + [
                "--format", "json",
                "--out", tmp_dir,
                "--no-coverage",
                "--profile", chosen_profile,
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

                duration = round(time.perf_counter() - t0, 3)
                report_path = Path(tmp_dir) / "analysis-results.json"

                if not report_path.exists():
                    status = ToolStatus(
                        name="valknut",
                        available=True,
                        version=version,
                        duration_seconds=duration,
                        error=f"Valknut produced no analysis-results.json (exit code {proc.returncode}): {proc.stderr[:300]}",
                    )
                    return status, [], {}

                with open(report_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                findings: List[StructuralFinding] = []

                # Extract impact findings (cycles, chokepoints)
                passes = data.get("passes", {})
                impact = passes.get("impact", {})
                cycles = impact.get("dependency_cycles", [])
                for cycle in cycles:
                    findings.append(StructuralFinding(
                        analyzer="valknut",
                        kind="dependency_cycle",
                        severity="High",
                        location=" -> ".join(cycle) if isinstance(cycle, list) else str(cycle),
                        description="Circular dependency detected",
                        details={"cycle": cycle},
                    ))

                chokepoints = impact.get("chokepoints", [])
                for cp in chokepoints:
                    findings.append(StructuralFinding(
                        analyzer="valknut",
                        kind="chokepoint",
                        severity="Medium",
                        location=str(cp),
                        description="Structural chokepoint detected",
                        details={"chokepoint": cp},
                    ))

                # Extract structure recommendations
                structure = passes.get("structure", {})
                for split_rec in structure.get("file_splitting_recommendations", []):
                    findings.append(StructuralFinding(
                        analyzer="valknut",
                        kind="file_splitting_needed",
                        severity="Medium",
                        location=split_rec.get("file", ""),
                        description=split_rec.get("reason", "File recommended for splitting"),
                        details=split_rec,
                    ))

                # Complexity pass critical/high issues
                complexity = passes.get("complexity", {})
                for entity in complexity.get("detailed_results", []):
                    sev = entity.get("severity", "Low")
                    if sev in ["Critical", "High"]:
                        findings.append(StructuralFinding(
                            analyzer="valknut",
                            kind="high_complexity_entity",
                            severity=sev,
                            location=f"{entity.get('file_path', '')}:{entity.get('entity_name', '')}",
                            description=f"Entity exceeds complexity thresholds (CCN: {entity.get('metrics', {}).get('cyclomatic_complexity')})",
                            details=entity.get("metrics", {}),
                        ))

                status = ToolStatus(
                    name="valknut",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                )

                return status, findings, data

            except subprocess.TimeoutExpired:
                duration = round(time.perf_counter() - t0, 3)
                status = ToolStatus(
                    name="valknut",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                    error="Valknut timed out after 180 seconds",
                )
                return status, [], {}
            except Exception as e:
                duration = round(time.perf_counter() - t0, 3)
                status = ToolStatus(
                    name="valknut",
                    available=True,
                    version=version,
                    duration_seconds=duration,
                    error=f"Error executing Valknut: {e}",
                )
                return status, [], {}
