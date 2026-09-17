"""Architecture comparator computing multidimensional deltas and diff-aware problem attribution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import FitnessConfig
from .git_utils import GitUtils
from .models import (
    ArchitectureVector,
    ComparisonResult,
    DeltaClassification,
    FunctionMetric,
    MeasurementReport,
    MetricDelta,
    VectorDelta,
)


class ArchitectureComparator:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def compare(
        self,
        baseline_report: MeasurementReport,
        current_report: MeasurementReport,
        diff_aware: bool = True,
        baseline_id: str = "baseline",
    ) -> ComparisonResult:
        base_vec = baseline_report.vector
        curr_vec = current_report.vector

        # 1. Tool availability warnings
        warnings = self._check_tool_availability(base_vec, curr_vec)

        # 2. Metric Deltas
        metrics, regressions, improvements = self._compute_metrics_delta(base_vec, curr_vec)

        # 3. Diff-Aware Problem Attribution
        root = Path(current_report.repo_path).resolve()
        changed_files = GitUtils.get_changed_files(root, base_ref=baseline_report.git_commit) if diff_aware else []
        diff_ranges = GitUtils.get_diff_ranges(root, base_ref=baseline_report.git_commit) if diff_aware else {}

        new_func_probs, exist_func_debt, resolved_func_probs = self._attribute_function_problems(
            baseline_report, current_report, changed_files, diff_ranges, diff_aware
        )
        new_clone_probs, exist_clone_debt = self._attribute_clone_problems(current_report, changed_files)
        new_struct_probs, exist_struct_debt, resolved_struct_probs = self._attribute_structural_problems(
            baseline_report, current_report
        )

        new_problems = new_func_probs + new_clone_probs + new_struct_probs
        existing_debt = exist_func_debt + exist_clone_debt + exist_struct_debt
        resolved_problems = resolved_func_probs + resolved_struct_probs

        # 4. Classification
        classification = self._determine_classification(
            curr_vec, base_vec, regressions, new_problems, resolved_problems, metrics
        )

        vector_delta = VectorDelta(
            classification=classification,
            metrics=metrics,
            regressions=regressions,
            improvements=improvements,
            warnings=warnings,
        )

        # 5. Summary Header
        summary_header, suggested_action = self._format_summary_header(
            classification, base_vec, curr_vec, metrics, regressions, new_problems, resolved_problems, improvements, warnings
        )

        return ComparisonResult(
            classification=classification,
            summary_header=summary_header,
            baseline_id=baseline_id,
            baseline_commit=baseline_report.git_commit,
            current_commit=current_report.git_commit,
            diff_aware=diff_aware,
            vector_delta=vector_delta,
            new_problems=new_problems,
            existing_debt=existing_debt[:15],
            resolved_problems=resolved_problems,
            affected_files=changed_files,
            suggested_action=suggested_action,
        )

    def _check_tool_availability(self, base_vec: ArchitectureVector, curr_vec: ArchitectureVector) -> List[str]:
        warnings: List[str] = []
        if base_vec.valknut_available and not curr_vec.valknut_available:
            warnings.append("Valknut analyzer failed or was unavailable during current measurement; structural metrics cannot be compared.")
        if base_vec.jscpd_available and not curr_vec.jscpd_available:
            warnings.append("jscpd analyzer failed or was unavailable during current measurement; duplication metrics cannot be compared.")
        if base_vec.lizard_available and not curr_vec.lizard_available:
            warnings.append("Lizard analyzer failed or was unavailable during current measurement; complexity metrics cannot be compared.")
        return warnings

    def _compute_metrics_delta(
        self, base_vec: ArchitectureVector, curr_vec: ArchitectureVector
    ) -> Tuple[Dict[str, MetricDelta], List[str], List[str]]:
        metrics: Dict[str, MetricDelta] = {}
        regressions: List[str] = []
        improvements: List[str] = []

        # Lines of code
        loc_delta = curr_vec.lines_of_code - base_vec.lines_of_code
        metrics["lines_of_code"] = MetricDelta(
            metric="lines_of_code",
            baseline_value=base_vec.lines_of_code,
            current_value=curr_vec.lines_of_code,
            delta=loc_delta,
            delta_str=f"{loc_delta:+d}",
            classification=DeltaClassification.NEUTRAL,
        )

        # Files
        files_delta = curr_vec.files_count - base_vec.files_count
        metrics["files_count"] = MetricDelta(
            metric="files_count",
            baseline_value=base_vec.files_count,
            current_value=curr_vec.files_count,
            delta=files_delta,
            delta_str=f"{files_delta:+d}",
            classification=DeltaClassification.NEUTRAL,
        )

        # Functions
        func_delta = curr_vec.functions_count - base_vec.functions_count
        metrics["functions_count"] = MetricDelta(
            metric="functions_count",
            baseline_value=base_vec.functions_count,
            current_value=curr_vec.functions_count,
            delta=func_delta,
            delta_str=f"{func_delta:+d}",
            classification=DeltaClassification.NEUTRAL,
        )

        # Total Cyclomatic Complexity
        ccn_delta = curr_vec.total_cyclomatic_complexity - base_vec.total_cyclomatic_complexity
        metrics["total_cyclomatic_complexity"] = MetricDelta(
            metric="total_cyclomatic_complexity",
            baseline_value=base_vec.total_cyclomatic_complexity,
            current_value=curr_vec.total_cyclomatic_complexity,
            delta=ccn_delta,
            delta_str=f"{ccn_delta:+d}",
            classification=DeltaClassification.REGRESSION if ccn_delta > self.config.thresholds.max_complexity_delta else (
                DeltaClassification.IMPROVED if ccn_delta < -1 else DeltaClassification.NEUTRAL
            ),
        )

        # Average Cyclomatic Complexity
        avg_ccn_delta = round(curr_vec.avg_cyclomatic_complexity - base_vec.avg_cyclomatic_complexity, 2)
        is_avg_ccn_reg = (avg_ccn_delta >= 2.0) or (avg_ccn_delta >= 1.0 and curr_vec.avg_cyclomatic_complexity > 5.0)
        is_avg_ccn_imp = avg_ccn_delta <= -1.0 and curr_vec.total_cyclomatic_complexity < base_vec.total_cyclomatic_complexity
        metrics["avg_cyclomatic_complexity"] = MetricDelta(
            metric="avg_cyclomatic_complexity",
            baseline_value=base_vec.avg_cyclomatic_complexity,
            current_value=curr_vec.avg_cyclomatic_complexity,
            delta=avg_ccn_delta,
            delta_str=f"{avg_ccn_delta:+.2f}",
            classification=DeltaClassification.REGRESSION if is_avg_ccn_reg else (
                DeltaClassification.IMPROVED if is_avg_ccn_imp else DeltaClassification.NEUTRAL
            ),
            is_regression=is_avg_ccn_reg,
            is_improvement=is_avg_ccn_imp,
        )
        if is_avg_ccn_reg:
            regressions.append(f"Average complexity increased by {avg_ccn_delta:+.2f} ({base_vec.avg_cyclomatic_complexity} -> {curr_vec.avg_cyclomatic_complexity})")
        elif is_avg_ccn_imp:
            improvements.append(f"Average complexity improved by {avg_ccn_delta:+.2f} ({base_vec.avg_cyclomatic_complexity} -> {curr_vec.avg_cyclomatic_complexity})")

        # Max Cyclomatic Complexity
        max_ccn_delta = curr_vec.max_cyclomatic_complexity - base_vec.max_cyclomatic_complexity
        is_max_ccn_reg = max_ccn_delta > 3 or (curr_vec.max_cyclomatic_complexity > self.config.thresholds.max_function_ccn and max_ccn_delta > 0)
        is_max_ccn_imp = max_ccn_delta <= -3
        metrics["max_cyclomatic_complexity"] = MetricDelta(
            metric="max_cyclomatic_complexity",
            baseline_value=base_vec.max_cyclomatic_complexity,
            current_value=curr_vec.max_cyclomatic_complexity,
            delta=max_ccn_delta,
            delta_str=f"{max_ccn_delta:+d}",
            classification=DeltaClassification.REGRESSION if is_max_ccn_reg else (
                DeltaClassification.IMPROVED if is_max_ccn_imp else DeltaClassification.NEUTRAL
            ),
            is_regression=is_max_ccn_reg,
            is_improvement=is_max_ccn_imp,
        )
        if is_max_ccn_reg:
            regressions.append(f"Maximum function complexity spiked by {max_ccn_delta:+d} ({base_vec.max_cyclomatic_complexity} -> {curr_vec.max_cyclomatic_complexity})")
        elif is_max_ccn_imp:
            improvements.append(f"Maximum function complexity reduced by {max_ccn_delta:+d} ({base_vec.max_cyclomatic_complexity} -> {curr_vec.max_cyclomatic_complexity})")

        # Duplication Percentage
        if base_vec.jscpd_available and curr_vec.jscpd_available:
            dupe_delta = round(curr_vec.duplication_percentage - base_vec.duplication_percentage, 2)
            is_dupe_reg = dupe_delta >= self.config.thresholds.max_duplication_percentage_delta
            is_dupe_imp = dupe_delta <= -self.config.thresholds.max_duplication_percentage_delta
            metrics["duplication_percentage"] = MetricDelta(
                metric="duplication_percentage",
                baseline_value=base_vec.duplication_percentage,
                current_value=curr_vec.duplication_percentage,
                delta=dupe_delta,
                delta_str=f"{dupe_delta:+.2f}%",
                classification=DeltaClassification.REGRESSION if is_dupe_reg else (
                    DeltaClassification.IMPROVED if is_dupe_imp else DeltaClassification.NEUTRAL
                ),
                is_regression=is_dupe_reg,
                is_improvement=is_dupe_imp,
            )
            if is_dupe_reg:
                regressions.append(f"Code duplication increased by {dupe_delta:+.2f}% ({base_vec.duplication_percentage}% -> {curr_vec.duplication_percentage}%)")
            elif is_dupe_imp:
                improvements.append(f"Code duplication reduced by {dupe_delta:+.2f}% ({base_vec.duplication_percentage}% -> {curr_vec.duplication_percentage}%)")
        else:
            metrics["duplication_percentage"] = MetricDelta(
                metric="duplication_percentage",
                baseline_value=base_vec.duplication_percentage if base_vec.jscpd_available else None,
                current_value=curr_vec.duplication_percentage if curr_vec.jscpd_available else None,
                delta=None,
                delta_str="N/A",
                classification=DeltaClassification.UNKNOWN,
            )

        # Clone Groups
        clone_delta = curr_vec.clone_groups_count - base_vec.clone_groups_count
        is_clone_reg = clone_delta > self.config.thresholds.new_clone_groups_allowed
        is_clone_imp = clone_delta < 0
        metrics["clone_groups_count"] = MetricDelta(
            metric="clone_groups_count",
            baseline_value=base_vec.clone_groups_count,
            current_value=curr_vec.clone_groups_count,
            delta=clone_delta,
            delta_str=f"{clone_delta:+d}",
            classification=DeltaClassification.REGRESSION if is_clone_reg else (
                DeltaClassification.IMPROVED if is_clone_imp else DeltaClassification.NEUTRAL
            ),
            is_regression=is_clone_reg,
            is_improvement=is_clone_imp,
        )
        if is_clone_reg:
            regressions.append(f"New clone groups detected: {clone_delta:+d} ({base_vec.clone_groups_count} -> {curr_vec.clone_groups_count})")
        elif is_clone_imp:
            improvements.append(f"Clone groups eliminated: {clone_delta:+d} ({base_vec.clone_groups_count} -> {curr_vec.clone_groups_count})")

        # Dependency Cycles
        if base_vec.dependency_cycles_count is not None and curr_vec.dependency_cycles_count is not None:
            cycle_delta = curr_vec.dependency_cycles_count - base_vec.dependency_cycles_count
            is_cycle_reg = cycle_delta > 0
            is_cycle_imp = cycle_delta < 0
            metrics["dependency_cycles_count"] = MetricDelta(
                metric="dependency_cycles_count",
                baseline_value=base_vec.dependency_cycles_count,
                current_value=curr_vec.dependency_cycles_count,
                delta=cycle_delta,
                delta_str=f"{cycle_delta:+d}",
                classification=DeltaClassification.REGRESSION if is_cycle_reg else (
                    DeltaClassification.IMPROVED if is_cycle_imp else DeltaClassification.NEUTRAL
                ),
                is_regression=is_cycle_reg,
                is_improvement=is_cycle_imp,
            )
            if is_cycle_reg:
                regressions.append(f"New circular dependencies introduced: {cycle_delta:+d}")
            elif is_cycle_imp:
                improvements.append(f"Circular dependencies resolved: {cycle_delta:+d}")

        # Valknut Overall Health Score
        if base_vec.overall_health_score is not None and curr_vec.overall_health_score is not None:
            health_delta = round(curr_vec.overall_health_score - base_vec.overall_health_score, 2)
            is_health_reg = health_delta <= -self.config.thresholds.max_health_drop
            is_health_imp = health_delta >= self.config.thresholds.max_health_drop
            metrics["overall_health_score"] = MetricDelta(
                metric="overall_health_score",
                baseline_value=base_vec.overall_health_score,
                current_value=curr_vec.overall_health_score,
                delta=health_delta,
                delta_str=f"{health_delta:+.2f}",
                classification=DeltaClassification.REGRESSION if is_health_reg else (
                    DeltaClassification.IMPROVED if is_health_imp else DeltaClassification.NEUTRAL
                ),
                is_regression=is_health_reg,
                is_improvement=is_health_imp,
            )
            if is_health_reg:
                regressions.append(f"Overall health score dropped by {health_delta:+.2f} ({base_vec.overall_health_score} -> {curr_vec.overall_health_score})")
            elif is_health_imp:
                improvements.append(f"Overall health score improved by {health_delta:+.2f} ({base_vec.overall_health_score} -> {curr_vec.overall_health_score})")

        return metrics, regressions, improvements

    def _attribute_function_problems(
        self,
        baseline_report: MeasurementReport,
        current_report: MeasurementReport,
        changed_files: List[str],
        diff_ranges: Dict[str, List[Tuple[int, int]]],
        diff_aware: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        new_problems: List[Dict[str, Any]] = []
        existing_debt: List[Dict[str, Any]] = []
        resolved_problems: List[Dict[str, Any]] = []

        baseline_func_map = {f"{f.file_path}:{f.name}": f for f in baseline_report.functions}

        for curr_f in current_report.functions:
            func_key = f"{curr_f.file_path}:{curr_f.name}"
            is_in_diff = curr_f.file_path in changed_files

            line_overlap = False
            if is_in_diff and curr_f.file_path in diff_ranges:
                for start, end in diff_ranges[curr_f.file_path]:
                    if not (curr_f.end_line < start or curr_f.start_line > end):
                        line_overlap = True
                        break
            elif is_in_diff and not diff_ranges.get(curr_f.file_path):
                line_overlap = True

            base_f = baseline_func_map.get(func_key)

            if curr_f.cyclomatic_complexity > self.config.thresholds.max_function_ccn:
                prob = {
                    "kind": "high_complexity_function",
                    "file": curr_f.file_path,
                    "function": curr_f.name,
                    "ccn": curr_f.cyclomatic_complexity,
                    "nloc": curr_f.nloc,
                    "start_line": curr_f.start_line,
                    "end_line": curr_f.end_line,
                }
                if base_f is None:
                    if line_overlap or not diff_aware:
                        new_problems.append({
                            **prob,
                            "origin": "new_function",
                            "message": f"New function '{curr_f.name}' introduced with excessive CCN={curr_f.cyclomatic_complexity}",
                        })
                    else:
                        existing_debt.append(prob)
                else:
                    if curr_f.cyclomatic_complexity > base_f.cyclomatic_complexity and line_overlap:
                        ccn_increase = curr_f.cyclomatic_complexity - base_f.cyclomatic_complexity
                        new_problems.append({
                            **prob,
                            "origin": "modified_function",
                            "ccn_delta": ccn_increase,
                            "message": f"Function '{curr_f.name}' complexity increased by +{ccn_increase} ({base_f.cyclomatic_complexity} -> {curr_f.cyclomatic_complexity}) in diff",
                        })
                    else:
                        existing_debt.append(prob)
            elif base_f and base_f.cyclomatic_complexity > self.config.thresholds.max_function_ccn:
                if line_overlap:
                    resolved_problems.append({
                        "kind": "complexity_resolved",
                        "file": curr_f.file_path,
                        "function": curr_f.name,
                        "old_ccn": base_f.cyclomatic_complexity,
                        "new_ccn": curr_f.cyclomatic_complexity,
                        "message": f"Function '{curr_f.name}' complexity reduced below threshold ({base_f.cyclomatic_complexity} -> {curr_f.cyclomatic_complexity})",
                    })

        return new_problems, existing_debt, resolved_problems

    def _attribute_clone_problems(
        self, current_report: MeasurementReport, changed_files: List[str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        new_problems: List[Dict[str, Any]] = []
        existing_debt: List[Dict[str, Any]] = []

        for clone in current_report.duplicates:
            f1_in_diff = clone.first_file.name in changed_files
            f2_in_diff = clone.second_file.name in changed_files

            clone_info = {
                "kind": "duplicate_clone",
                "first_file": clone.first_file.name,
                "second_file": clone.second_file.name,
                "lines": clone.lines,
                "tokens": clone.tokens,
            }

            if f1_in_diff or f2_in_diff:
                new_problems.append({
                    **clone_info,
                    "origin": "new_or_modified_clone",
                    "message": f"Duplicate logic ({clone.lines} lines) touching modified file {clone.first_file.name if f1_in_diff else clone.second_file.name}",
                })
            else:
                existing_debt.append(clone_info)

        return new_problems, existing_debt

    def _attribute_structural_problems(
        self, baseline_report: MeasurementReport, current_report: MeasurementReport
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        new_problems: List[Dict[str, Any]] = []
        existing_debt: List[Dict[str, Any]] = []
        resolved_problems: List[Dict[str, Any]] = []

        baseline_finding_locations = {f.location for f in baseline_report.findings}
        current_finding_locations = {f.location for f in current_report.findings}

        for finding in current_report.findings:
            if finding.location in baseline_finding_locations:
                existing_debt.append({
                    "kind": finding.kind,
                    "location": finding.location,
                    "message": f"Existing {finding.kind}: {finding.location}",
                })
            else:
                new_problems.append({
                    "kind": finding.kind,
                    "location": finding.location,
                    "message": f"New {finding.kind} introduced: {finding.location}",
                })

        for base_finding in baseline_report.findings:
            if base_finding.location not in current_finding_locations:
                resolved_problems.append({
                    "kind": f"{base_finding.kind}_resolved",
                    "location": base_finding.location,
                    "message": f"Resolved existing {base_finding.kind}: {base_finding.location}",
                })

        return new_problems, existing_debt, resolved_problems

    def _determine_classification(
        self,
        curr_vec: ArchitectureVector,
        base_vec: ArchitectureVector,
        regressions: List[str],
        new_problems: List[Dict[str, Any]],
        resolved_problems: List[Dict[str, Any]],
        metrics: Dict[str, MetricDelta],
    ) -> DeltaClassification:
        has_critical_regression = bool(regressions) or any(
            p.get("kind") in ["high_complexity_function", "dependency_cycle", "duplicate_clone"]
            for p in new_problems
        )

        if has_critical_regression:
            return DeltaClassification.REGRESSION
        elif not curr_vec.lizard_available and not curr_vec.jscpd_available and not curr_vec.valknut_available:
            return DeltaClassification.UNKNOWN
        elif (
            (resolved_problems or
             curr_vec.total_cyclomatic_complexity < base_vec.total_cyclomatic_complexity or
             curr_vec.clone_groups_count < base_vec.clone_groups_count or
             (metrics.get("max_cyclomatic_complexity") and metrics["max_cyclomatic_complexity"].delta <= -3))
            and not regressions and not new_problems
        ):
            return DeltaClassification.IMPROVED
        else:
            return DeltaClassification.NEUTRAL

    def _format_summary_header(
        self,
        classification: DeltaClassification,
        base_vec: ArchitectureVector,
        curr_vec: ArchitectureVector,
        metrics: Dict[str, MetricDelta],
        regressions: List[str],
        new_problems: List[Dict[str, Any]],
        resolved_problems: List[Dict[str, Any]],
        improvements: List[str],
        warnings: List[str],
    ) -> Tuple[str, str]:
        summary_lines: List[str] = [f"ARCHITECTURE RESULT: {classification.value}\n"]

        dupe_b = f"{base_vec.duplication_percentage:.1f}%" if base_vec.jscpd_available else "N/A"
        dupe_c = f"{curr_vec.duplication_percentage:.1f}%" if curr_vec.jscpd_available else "N/A"
        summary_lines.append(f"Duplication:       {dupe_b:>6} -> {dupe_c:<6} ({metrics['duplication_percentage'].delta_str})")
        summary_lines.append(f"Complexity (avg):  {base_vec.avg_cyclomatic_complexity:>6.1f} -> {curr_vec.avg_cyclomatic_complexity:<6.1f} ({metrics['avg_cyclomatic_complexity'].delta_str})")
        summary_lines.append(f"Max complexity:    {base_vec.max_cyclomatic_complexity:>6d} -> {curr_vec.max_cyclomatic_complexity:<6d} ({metrics['max_cyclomatic_complexity'].delta_str})")
        summary_lines.append(f"Files:             {base_vec.files_count:>6d} -> {curr_vec.files_count:<6d} ({metrics['files_count'].delta_str})")
        summary_lines.append(f"Functions:         {base_vec.functions_count:>6d} -> {curr_vec.functions_count:<6d} ({metrics['functions_count'].delta_str})")
        summary_lines.append(f"Lines of Code:     {base_vec.lines_of_code:>6d} -> {curr_vec.lines_of_code:<6d} ({metrics['lines_of_code'].delta_str})")

        if base_vec.overall_health_score is not None and curr_vec.overall_health_score is not None:
            summary_lines.append(f"Valknut Health:    {base_vec.overall_health_score:>6.1f} -> {curr_vec.overall_health_score:<6.1f} ({metrics['overall_health_score'].delta_str})")

        if regressions:
            summary_lines.append("\nSignificant regressions:")
            for reg in regressions:
                summary_lines.append(f"  - {reg}")

        if new_problems:
            summary_lines.append("\nNew problems introduced in this change:")
            for prob in new_problems[:8]:
                summary_lines.append(f"  - {prob.get('message', prob.get('kind'))}")

        if resolved_problems:
            summary_lines.append("\nExisting problems resolved by this change:")
            for res in resolved_problems[:5]:
                summary_lines.append(f"  - {res.get('message')}")

        if improvements and not regressions:
            summary_lines.append("\nImprovements:")
            for imp in improvements:
                summary_lines.append(f"  - {imp}")

        if warnings:
            summary_lines.append("\nWarnings / Tool issues:")
            for w in warnings:
                summary_lines.append(f"  - {w}")

        if classification == DeltaClassification.REGRESSION:
            suggested_action = "Investigate the newly introduced complexity, clone groups, or dependency regressions before accepting this implementation."
        elif classification == DeltaClassification.IMPROVED:
            suggested_action = "Architecture measurably improved. The refactoring or implementation reduced complexity footprint."
        elif classification == DeltaClassification.UNKNOWN:
            suggested_action = "One or more analyzers failed. Verify tool installation and rerun measurement."
        else:
            suggested_action = "Changes maintained neutral architectural footprint."

        summary_lines.append(f"\nSuggested next action:\n  {suggested_action}")
        return "\n".join(summary_lines), suggested_action
