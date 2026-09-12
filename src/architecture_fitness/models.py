"""Data models for Architecture Fitness system."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DeltaClassification(str, Enum):
    IMPROVED = "IMPROVED"
    NEUTRAL = "NEUTRAL"
    REGRESSION = "REGRESSION"
    UNKNOWN = "UNKNOWN"


class FunctionMetric(BaseModel):
    file_path: str
    name: str
    long_name: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    nloc: int
    token_count: int
    parameter_count: int = 0
    max_nesting_depth: int = 0


class DuplicateLocation(BaseModel):
    name: str
    start: int
    end: int
    lines: int


class DuplicateClone(BaseModel):
    format: str
    lines: int
    tokens: int
    first_file: DuplicateLocation
    second_file: DuplicateLocation
    fragment: Optional[str] = None


class StructuralFinding(BaseModel):
    analyzer: str
    kind: str  # e.g., "cycle", "chokepoint", "high_debt", "refactoring"
    severity: str  # "Critical", "High", "Medium", "Low", "Info"
    location: str
    description: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ArchitectureVector(BaseModel):
    # Base size & counts
    lines_of_code: int = 0
    functions_count: int = 0
    files_count: int = 0

    # Complexity (Lizard & Valknut)
    total_cyclomatic_complexity: int = 0
    avg_cyclomatic_complexity: float = 0.0
    max_cyclomatic_complexity: int = 0
    high_complexity_functions_count: int = 0  # CCN > 15

    # Duplication (jscpd)
    duplication_percentage: float = 0.0
    duplicated_lines: int = 0
    clone_groups_count: int = 0

    # Structural & Health (Valknut)
    cognitive_complexity_avg: Optional[float] = None
    maintainability_index_avg: Optional[float] = None
    technical_debt_ratio: Optional[float] = None
    overall_health_score: Optional[float] = None
    dependency_cycles_count: Optional[int] = None
    chokepoints_count: Optional[int] = None
    structure_issues_count: Optional[int] = None

    # Availability indicators (never pretend missing is 0)
    lizard_available: bool = True
    jscpd_available: bool = True
    valknut_available: bool = True


class MetricDelta(BaseModel):
    metric: str
    baseline_value: Any
    current_value: Any
    delta: Any
    delta_str: str
    classification: DeltaClassification
    is_regression: bool = False
    is_improvement: bool = False


class VectorDelta(BaseModel):
    classification: DeltaClassification
    metrics: Dict[str, MetricDelta]
    regressions: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Hotspot(BaseModel):
    id: str
    kind: str  # "high_complexity", "duplication", "dependency_cycle", "low_maintainability"
    location: str  # e.g. "path/file.py:func_name"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    score: float  # Higher means more problematic
    title: str
    description: str
    details: Dict[str, Any] = Field(default_factory=dict)
    recommendation: str


class ReuseCandidate(BaseModel):
    symbol_name: str
    kind: str  # "function", "method", "class", "module"
    file_path: str
    line_number: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    relevance_reason: str
    evidence: str
    confidence: float  # 0.0 - 1.0


class ToolStatus(BaseModel):
    name: str
    available: bool
    version: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    warning: Optional[str] = None


class MeasurementReport(BaseModel):
    repo_path: str
    timestamp: str
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    tools: Dict[str, ToolStatus]
    vector: ArchitectureVector
    functions: List[FunctionMetric] = Field(default_factory=list)
    duplicates: List[DuplicateClone] = Field(default_factory=list)
    findings: List[StructuralFinding] = Field(default_factory=list)
    hotspots: List[Hotspot] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    raw_summaries: Dict[str, Any] = Field(default_factory=dict)


class BaselineRecord(BaseModel):
    id: str
    name: str
    timestamp: str
    repo_path: str
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    tool_versions: Dict[str, str]
    vector: ArchitectureVector
    functions_count: int
    duplicates_count: int
    findings_count: int
    measurement_report_ref: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class ComparisonResult(BaseModel):
    classification: DeltaClassification
    summary_header: str
    baseline_id: str
    baseline_commit: Optional[str] = None
    current_commit: Optional[str] = None
    diff_aware: bool = True
    vector_delta: VectorDelta
    new_problems: List[Dict[str, Any]] = Field(default_factory=list)
    existing_debt: List[Dict[str, Any]] = Field(default_factory=list)
    resolved_problems: List[Dict[str, Any]] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    suggested_action: str
