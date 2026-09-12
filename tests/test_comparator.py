"""Tests for baseline management, metric comparison, and diff-aware problem attribution."""

import subprocess
from pathlib import Path
import pytest

from architecture_fitness.models import DeltaClassification
from architecture_fitness.service import ArchitectureFitnessService


def test_baseline_creation_and_retrieval(git_repo, service):
    record, report = service.create_baseline(git_repo, name="test-base")
    assert record.id == "test-base"
    assert record.functions_count >= 1

    loaded_pair = service.baseline_mgr.get_baseline(git_repo, name_or_commit="test-base")
    assert loaded_pair is not None
    loaded_rec, loaded_rep = loaded_pair
    assert loaded_rec.id == "test-base"
    assert loaded_rep.vector.functions_count == record.vector.functions_count


def test_comparator_neutral(git_repo, service):
    service.create_baseline(git_repo, name="base")
    comp = service.compare(git_repo, baseline_name="base", diff_aware=True)
    assert comp.classification == DeltaClassification.NEUTRAL
    assert comp.vector_delta.metrics["lines_of_code"].delta == 0


def test_comparator_complexity_regression(git_repo, service):
    service.create_baseline(git_repo, name="base")

    # Add a function with cyclomatic complexity > 15
    branches = "\n".join([f"    if x == {i}: return {i}" for i in range(20)])
    (git_repo / "complex.py").write_text(f"def huge_switch(x):\n{branches}\n    return -1\n")

    comp = service.compare(git_repo, baseline_name="base", diff_aware=True)
    assert comp.classification == DeltaClassification.REGRESSION
    assert comp.vector_delta.metrics["max_cyclomatic_complexity"].delta >= 20
    assert any("huge_switch" in p.get("function", "") for p in comp.new_problems)


def test_comparator_duplication_regression(git_repo, service):
    service.create_baseline(git_repo, name="base")

    # Introduce duplicated blocks across two files
    block = "\n".join([f"    x_{i} = do_step_{i}(val)" for i in range(25)])
    (git_repo / "algo_a.py").write_text(f"def algo_a(val):\n{block}\n    return True\n")
    (git_repo / "algo_b.py").write_text(f"def algo_b(val):\n{block}\n    return False\n")

    comp = service.compare(git_repo, baseline_name="base", diff_aware=True)
    assert comp.classification == DeltaClassification.REGRESSION
    assert comp.vector_delta.metrics["duplication_percentage"].delta > 0
    assert comp.vector_delta.metrics["clone_groups_count"].delta >= 1


def test_comparator_diff_aware_isolation(git_repo, service):
    """Test that existing pre-baseline debt is not blamed on a clean new feature."""
    # Introduce pre-existing debt before baseline
    branches = "\n".join([f"    if x == {i}: return {i}" for i in range(20)])
    (git_repo / "legacy.py").write_text(f"def legacy_monster(x):\n{branches}\n    return -1\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Legacy debt commit"], cwd=str(git_repo), check=True, capture_output=True)

    # Establish baseline containing the legacy monster
    service.create_baseline(git_repo, name="with_legacy")

    # Now implement a clean, simple new feature
    (git_repo / "feature.py").write_text("def clean_add(a, b):\n    return a + b\n")

    comp = service.compare(git_repo, baseline_name="with_legacy", diff_aware=True)
    # The legacy monster should be in existing_debt, NOT new_problems!
    assert any("legacy_monster" in p.get("function", "") for p in comp.existing_debt)
    assert not any("legacy_monster" in p.get("function", "") for p in comp.new_problems)
    assert comp.classification == DeltaClassification.NEUTRAL


def test_comparator_unknown_on_missing_tools(git_repo, service):
    _, base_rep = service.create_baseline(git_repo, name="base")
    curr_rep = service.measure(git_repo)
    # Simulate all tools failing in current measurement
    curr_rep.vector.lizard_available = False
    curr_rep.vector.jscpd_available = False
    curr_rep.vector.valknut_available = False

    comp = service.comparator.compare(base_rep, curr_rep, baseline_id="base")
    assert comp.classification == DeltaClassification.UNKNOWN
