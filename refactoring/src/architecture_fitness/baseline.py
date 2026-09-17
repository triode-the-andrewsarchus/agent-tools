"""Baseline management and local persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import FitnessConfig
from .git_utils import GitUtils
from .models import BaselineRecord, MeasurementReport


class BaselineManager:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def get_baseline_dir(self, repo_path: Path | str) -> Path:
        root = Path(repo_path).resolve()
        bdir = root / self.config.baseline_dir
        bdir.mkdir(parents=True, exist_ok=True)
        return bdir

    def save_baseline(
        self,
        report: MeasurementReport,
        name: Optional[str] = None,
    ) -> Tuple[BaselineRecord, Path]:
        root = Path(report.repo_path).resolve()
        bdir = self.get_baseline_dir(root)

        commit = report.git_commit or GitUtils.get_head_commit(root)
        baseline_name = name or (f"commit-{commit[:8]}" if commit else "initial")

        tool_versions = {
            t_name: t_status.version or "unknown"
            for t_name, t_status in report.tools.items()
        }

        record = BaselineRecord(
            id=baseline_name,
            name=baseline_name,
            timestamp=report.timestamp,
            repo_path=report.repo_path,
            git_commit=commit,
            git_branch=report.git_branch or GitUtils.get_current_branch(root),
            tool_versions=tool_versions,
            vector=report.vector,
            functions_count=len(report.functions),
            duplicates_count=len(report.duplicates),
            findings_count=len(report.findings),
            measurement_report_ref=f"{baseline_name}.json",
        )

        full_data = {
            "record": record.model_dump(),
            "report": report.model_dump(),
        }

        dest_file = bdir / f"{baseline_name}.json"
        with open(dest_file, "w", encoding="utf-8") as f:
            json.dump(full_data, f, indent=2)

        # Also maintain a 'latest.json' pointer
        latest_file = bdir / "latest.json"
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(full_data, f, indent=2)

        return record, dest_file

    def get_baseline(
        self,
        repo_path: Path | str,
        name_or_commit: Optional[str] = None,
    ) -> Optional[Tuple[BaselineRecord, MeasurementReport]]:
        root = Path(repo_path).resolve()
        bdir = self.get_baseline_dir(root)

        candidates: List[Path] = []
        if name_or_commit:
            candidates.append(bdir / f"{name_or_commit}.json")
            if not name_or_commit.endswith(".json"):
                candidates.append(bdir / f"commit-{name_or_commit[:8]}.json")
        else:
            # Try HEAD commit if in git repo
            head = GitUtils.get_head_commit(root)
            if head:
                candidates.append(bdir / f"commit-{head[:8]}.json")
            candidates.append(bdir / "latest.json")

        for c in candidates:
            if c.exists():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    rec = BaselineRecord.model_validate(data.get("record", {}))
                    rep = MeasurementReport.model_validate(data.get("report", {}))
                    return rec, rep
                except Exception:
                    continue

        return None

    def list_baselines(self, repo_path: Path | str) -> List[BaselineRecord]:
        root = Path(repo_path).resolve()
        bdir = self.get_baseline_dir(root)
        records: List[BaselineRecord] = []

        for p in bdir.glob("*.json"):
            if p.name == "latest.json":
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                records.append(BaselineRecord.model_validate(data.get("record", {})))
            except Exception:
                continue

        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records
