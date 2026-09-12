"""Normalizer layer unifying Lizard, jscpd, and Valknut into an ArchitectureVector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import FitnessConfig
from .models import (
    ArchitectureVector,
    DuplicateClone,
    FunctionMetric,
    Hotspot,
    MeasurementReport,
    StructuralFinding,
    ToolStatus,
)


class ArchitectureNormalizer:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def normalize(
        self,
        repo_path: Path | str,
        lizard_res: Tuple[ToolStatus, List[FunctionMetric], Dict[str, Any]],
        jscpd_res: Tuple[ToolStatus, List[DuplicateClone], Dict[str, Any]],
        valknut_res: Tuple[ToolStatus, List[StructuralFinding], Dict[str, Any]],
        git_commit: Optional[str] = None,
        git_branch: Optional[str] = None,
    ) -> MeasurementReport:
        root = Path(repo_path).resolve()
        now_iso = datetime.now(timezone.utc).isoformat()

        lizard_status, functions, lizard_data = lizard_res
        jscpd_status, duplicates, jscpd_data = jscpd_res
        valknut_status, findings, valknut_data = valknut_res

        # 1. Compute Base & Complexity Metrics
        lines_of_code = 0
        functions_count = len(functions)
        files_count = 0
        total_ccn = 0
        avg_ccn = 0.0
        max_ccn = 0
        high_ccn_count = 0

        if lizard_status.available and not lizard_status.error:
            total_nloc = lizard_data.get("total_nloc", 0)
            lines_of_code = total_nloc
            files_count = lizard_data.get("files_count", 0)
            total_ccn = lizard_data.get("total_ccn", 0)
            avg_ccn = lizard_data.get("avg_ccn", 0.0)
            max_ccn = lizard_data.get("max_ccn", 0)
            high_ccn_count = lizard_data.get("high_ccn_count", 0)
        elif valknut_status.available and not valknut_status.error:
            # Fallback size metrics from Valknut if Lizard failed
            summary = valknut_data.get("summary", {})
            lines_of_code = summary.get("total_lines_of_code", 0)
            files_count = summary.get("total_files", 0)
            functions_count = summary.get("total_entities", 0)
            complexity_pass = valknut_data.get("passes", {}).get("complexity", {})
            avg_ccn = complexity_pass.get("average_cyclomatic_complexity", 0.0)

        # 2. Compute Duplication Metrics
        duplication_percentage = 0.0
        duplicated_lines = 0
        clone_groups_count = len(duplicates)

        if jscpd_status.available and not jscpd_status.error:
            stats = jscpd_data.get("total", {})
            duplication_percentage = round(stats.get("percentage", 0.0), 2)
            duplicated_lines = stats.get("duplicatedLines", 0)
            clone_groups_count = stats.get("clones", len(duplicates))
        elif valknut_status.available and not valknut_status.error:
            # Check Valknut LSH clone pass
            lsh = valknut_data.get("passes", {}).get("lsh", {})
            if lsh.get("enabled"):
                clone_groups_count = lsh.get("duplicate_count", 0)

        # 3. Compute Valknut Structural & Health Metrics
        cognitive_complexity_avg = None
        maintainability_index_avg = None
        technical_debt_ratio = None
        overall_health_score = None
        dependency_cycles_count = None
        chokepoints_count = None
        structure_issues_count = None

        if valknut_status.available and not valknut_status.error:
            health = valknut_data.get("health_metrics", {})
            overall_health_score = health.get("overall_health_score")
            technical_debt_ratio = health.get("technical_debt_ratio")

            passes = valknut_data.get("passes", {})
            cpass = passes.get("complexity", {})
            cognitive_complexity_avg = cpass.get("average_cognitive_complexity")
            maintainability_index_avg = cpass.get("average_maintainability_index")

            ipass = passes.get("impact", {})
            dependency_cycles_count = len(ipass.get("dependency_cycles", []))
            chokepoints_count = len(ipass.get("chokepoints", []))

            spass = passes.get("structure", {})
            structure_issues_count = spass.get("issues_count", 0)

        vector = ArchitectureVector(
            lines_of_code=lines_of_code,
            functions_count=functions_count,
            files_count=files_count,
            total_cyclomatic_complexity=total_ccn,
            avg_cyclomatic_complexity=avg_ccn,
            max_cyclomatic_complexity=max_ccn,
            high_complexity_functions_count=high_ccn_count,
            duplication_percentage=duplication_percentage,
            duplicated_lines=duplicated_lines,
            clone_groups_count=clone_groups_count,
            cognitive_complexity_avg=cognitive_complexity_avg,
            maintainability_index_avg=maintainability_index_avg,
            technical_debt_ratio=technical_debt_ratio,
            overall_health_score=overall_health_score,
            dependency_cycles_count=dependency_cycles_count,
            chokepoints_count=chokepoints_count,
            structure_issues_count=structure_issues_count,
            lizard_available=bool(lizard_status.available and not lizard_status.error),
            jscpd_available=bool(jscpd_status.available and not jscpd_status.error),
            valknut_available=bool(valknut_status.available and not valknut_status.error),
        )

        # 4. Generate Hotspots
        hotspots = self._extract_hotspots(functions, duplicates, findings, valknut_data)

        tools = {
            "lizard": lizard_status,
            "jscpd": jscpd_status,
            "valknut": valknut_status,
        }

        raw_summaries = {
            "lizard": lizard_data,
            "jscpd": jscpd_data.get("total", {}),
            "valknut_summary": valknut_data.get("summary", {}),
            "valknut_health": valknut_data.get("health_metrics", {}),
        }

        return MeasurementReport(
            repo_path=str(root),
            timestamp=now_iso,
            git_commit=git_commit,
            git_branch=git_branch,
            tools=tools,
            vector=vector,
            functions=functions,
            duplicates=duplicates,
            findings=findings,
            hotspots=hotspots,
            raw_summaries=raw_summaries,
        )

    def _extract_hotspots(
        self,
        functions: List[FunctionMetric],
        duplicates: List[DuplicateClone],
        findings: List[StructuralFinding],
        valknut_data: Dict[str, Any],
    ) -> List[Hotspot]:
        hotspots: List[Hotspot] = []

        # A. High-complexity functions
        sorted_funcs = sorted(functions, key=lambda f: f.cyclomatic_complexity, reverse=True)
        for f in sorted_funcs[:15]:
            if f.cyclomatic_complexity >= 10:
                sev = "CRITICAL" if f.cyclomatic_complexity >= 25 else ("HIGH" if f.cyclomatic_complexity >= 15 else "MEDIUM")
                score = round(f.cyclomatic_complexity * 1.5 + f.nloc * 0.2, 1)
                hotspots.append(Hotspot(
                    id=f"complexity:{f.file_path}:{f.name}",
                    kind="high_complexity",
                    location=f"{f.file_path}:{f.name} (L{f.start_line}-{f.end_line})",
                    severity=sev,
                    score=score,
                    title=f"Function '{f.name}' has high cyclomatic complexity ({f.cyclomatic_complexity})",
                    description=f"{f.long_name} in {f.file_path} has CCN={f.cyclomatic_complexity}, NLOC={f.nloc}, params={f.parameter_count}.",
                    details={
                        "cyclomatic_complexity": f.cyclomatic_complexity,
                        "nloc": f.nloc,
                        "parameter_count": f.parameter_count,
                        "start_line": f.start_line,
                        "end_line": f.end_line,
                    },
                    recommendation="Decompose conditional branches, extract subroutines, or use polymorphism/table-driven dispatch.",
                ))

        # B. Duplicate code clusters
        sorted_dupes = sorted(duplicates, key=lambda d: d.lines, reverse=True)
        for d in sorted_dupes[:10]:
            score = round(d.lines * 1.0 + d.tokens * 0.05, 1)
            hotspots.append(Hotspot(
                id=f"duplication:{d.first_file.name}:{d.second_file.name}:{d.first_file.start}",
                kind="duplication",
                location=f"{d.first_file.name}:{d.first_file.start}-{d.first_file.end} <=> {d.second_file.name}:{d.second_file.start}-{d.second_file.end}",
                severity="HIGH" if d.lines >= 25 else "MEDIUM",
                score=score,
                title=f"Duplicate code block ({d.lines} lines, {d.tokens} tokens)",
                description=f"Identical logic repeated between {d.first_file.name} and {d.second_file.name}.",
                details={
                    "lines": d.lines,
                    "tokens": d.tokens,
                    "first_file": d.first_file.model_dump(),
                    "second_file": d.second_file.model_dump(),
                },
                recommendation="Extract common logic into a shared helper function or reuse existing module.",
            ))

        # C. Structural findings (Cycles, Chokepoints)
        for finding in findings:
            if finding.kind == "dependency_cycle":
                hotspots.append(Hotspot(
                    id=f"cycle:{finding.location}",
                    kind="dependency_cycle",
                    location=finding.location,
                    severity="CRITICAL",
                    score=100.0,
                    title="Circular Dependency Cycle",
                    description=f"Dependency cycle detected: {finding.location}",
                    details=finding.details,
                    recommendation="Invert dependency, introduce an interface, or break cycle into an event/shared abstraction.",
                ))
            elif finding.kind == "chokepoint":
                hotspots.append(Hotspot(
                    id=f"chokepoint:{finding.location}",
                    kind="chokepoint",
                    location=finding.location,
                    severity="HIGH",
                    score=70.0,
                    title="Architectural Chokepoint",
                    description=f"Central coupling chokepoint detected at {finding.location}",
                    details=finding.details,
                    recommendation="Decouple direct dependencies, extract focused sub-interfaces.",
                ))

        # Sort all hotspots by score descending
        hotspots.sort(key=lambda h: h.score, reverse=True)
        return hotspots
