"""Service coordinator executing measurements, baselines, comparisons, and hotspot analysis."""

from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .baseline import BaselineManager
from .comparator import ArchitectureComparator
from .config import FitnessConfig
from .git_utils import GitUtils
from .models import (
    BaselineRecord,
    ComparisonResult,
    Hotspot,
    MeasurementReport,
    ReuseCandidate,
)
from .normalizer import ArchitectureNormalizer
from .reuse_finder import ReuseFinder
from .runners.jscpd_runner import JscpdRunner
from .runners.lizard_runner import LizardRunner
from .runners.valknut_runner import ValknutRunner


class ArchitectureFitnessService:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()
        self.baseline_mgr = BaselineManager(self.config)
        self.normalizer = ArchitectureNormalizer(self.config)
        self.comparator = ArchitectureComparator(self.config)
        self.reuse_finder = ReuseFinder(self.config)

    def measure(
        self,
        repo_path: Path | str,
        target_paths: Optional[List[str]] = None,
        profile: Optional[str] = None,
    ) -> MeasurementReport:
        root = Path(repo_path).resolve()
        config = FitnessConfig.load(root)
        normalizer = ArchitectureNormalizer(config)

        lizard_runner = LizardRunner(config)
        jscpd_runner = JscpdRunner(config)
        valknut_runner = ValknutRunner(config)

        # Run analyzers concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            fut_lizard = executor.submit(lizard_runner.run, root, target_paths=target_paths)
            fut_jscpd = executor.submit(jscpd_runner.run, root, target_paths=target_paths)
            fut_valknut = executor.submit(valknut_runner.run, root, target_paths=target_paths, profile=profile)

            lizard_res = fut_lizard.result()
            jscpd_res = fut_jscpd.result()
            valknut_res = fut_valknut.result()

        git_commit = GitUtils.get_head_commit(root)
        git_branch = GitUtils.get_current_branch(root)

        return normalizer.normalize(
            repo_path=root,
            lizard_res=lizard_res,
            jscpd_res=jscpd_res,
            valknut_res=valknut_res,
            git_commit=git_commit,
            git_branch=git_branch,
        )

    def create_baseline(
        self,
        repo_path: Path | str,
        name: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> Tuple[BaselineRecord, MeasurementReport]:
        root = Path(repo_path).resolve()
        report = self.measure(root, profile=profile)
        record, _ = self.baseline_mgr.save_baseline(report, name=name)
        return record, report

    def compare(
        self,
        repo_path: Path | str,
        baseline_name: Optional[str] = None,
        diff_aware: bool = True,
        profile: Optional[str] = None,
    ) -> ComparisonResult:
        root = Path(repo_path).resolve()
        baseline_pair = self.baseline_mgr.get_baseline(root, name_or_commit=baseline_name)

        if not baseline_pair:
            # Create an initial baseline if none exists
            record, baseline_report = self.create_baseline(root, name="initial", profile=profile)
            baseline_id = record.id
        else:
            record, baseline_report = baseline_pair
            baseline_id = record.id

        current_report = self.measure(root, profile=profile)
        return self.comparator.compare(
            baseline_report=baseline_report,
            current_report=current_report,
            diff_aware=diff_aware,
            baseline_id=baseline_id,
        )

    def hotspots(
        self,
        repo_path: Path | str,
        top_n: int = 10,
        criteria: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> List[Hotspot]:
        root = Path(repo_path).resolve()
        report = self.measure(root, profile=profile)
        hotspots = report.hotspots

        if criteria:
            c = criteria.lower()
            hotspots = [h for h in hotspots if c in h.kind.lower() or c in h.severity.lower()]

        return hotspots[:top_n]

    def reuse_candidates(
        self,
        repo_path: Path | str,
        query: str,
        context: Optional[str] = None,
        top_n: int = 5,
    ) -> List[ReuseCandidate]:
        root = Path(repo_path).resolve()
        return self.reuse_finder.find_candidates(
            repo_path=root,
            query=query,
            context=context,
            top_n=top_n,
        )
