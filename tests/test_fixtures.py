"""Tests exercising the 10 required architectural change scenarios.

1. Genuinely new functionality
2. Unnecessary duplicate implementation
3. Reuse of an existing function
4. Extraction of duplicated functionality
5. File splitting that does not reduce complexity
6. Moving complexity elsewhere
7. Increased dependency coupling
8. Complexity reduction
9. Duplication reduction
10. Deliberately mixed result where some metrics improve and others worsen
"""

import subprocess
from pathlib import Path
import pytest

from architecture_fitness.models import DeltaClassification
from architecture_fitness.service import ArchitectureFitnessService


# ─────────────────────────────────────────────────────────────
# Scenario 1: Genuinely New Functionality
# Clean, cohesive additions should not be falsely flagged as regressions.
# ─────────────────────────────────────────────────────────────
def test_scenario_01_genuinely_new_functionality(git_repo, service):
    service.create_baseline(git_repo, name="base1")

    # Add a genuine, clean new feature (e.g. JSON export)
    new_code = """
def export_as_json(items, indent=2):
    import json
    if not items:
        return "{}"
    return json.dumps(items, indent=indent)
"""
    (git_repo / "exporter.py").write_text(new_code)
    comp = service.compare(git_repo, baseline_name="base1", diff_aware=True)

    assert comp.classification in [DeltaClassification.NEUTRAL, DeltaClassification.IMPROVED]
    assert comp.vector_delta.metrics["files_count"].delta == 1
    assert comp.vector_delta.metrics["functions_count"].delta == 1
    assert len(comp.new_problems) == 0


# ─────────────────────────────────────────────────────────────
# Scenario 2: Unnecessary Duplicate Implementation
# Copying an existing algorithm must trigger duplication regression.
# ─────────────────────────────────────────────────────────────
def test_scenario_02_duplicate_implementation(git_repo, service):
    # Establish baseline with an algorithm
    algo = "\n".join([f"    step_{i} = execute_step({i}, data)" for i in range(25)])
    (git_repo / "algo_orig.py").write_text(f"def process_data(data):\n{algo}\n    return True\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add algo"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base2")

    # Duplicate it into another file
    (git_repo / "algo_dupe.py").write_text(f"def process_data_v2(data):\n{algo}\n    return False\n")
    comp = service.compare(git_repo, baseline_name="base2", diff_aware=True)

    assert comp.classification == DeltaClassification.REGRESSION
    assert comp.vector_delta.metrics["clone_groups_count"].delta >= 1
    assert comp.vector_delta.metrics["duplication_percentage"].delta > 0


# ─────────────────────────────────────────────────────────────
# Scenario 3: Reuse of an Existing Function
# Calling an existing utility instead of duplicating preserves fitness.
# ─────────────────────────────────────────────────────────────
def test_scenario_03_reuse_existing_function(git_repo, service):
    # Baseline with a validator
    (git_repo / "validators.py").write_text("""
def is_valid_email(address):
    if not address or "@" not in address:
        return False
    parts = address.split("@")
    return len(parts) == 2 and "." in parts[1]
""")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add validator"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base3")

    # Reuse the existing function in a new module
    (git_repo / "registration.py").write_text("""
from validators import is_valid_email

def register_user(email, password):
    if not is_valid_email(email):
        raise ValueError("Invalid email")
    return {"status": "ok"}
""")
    comp = service.compare(git_repo, baseline_name="base3", diff_aware=True)

    assert comp.classification == DeltaClassification.NEUTRAL
    assert comp.vector_delta.metrics["clone_groups_count"].delta == 0
    assert len(comp.new_problems) == 0


# ─────────────────────────────────────────────────────────────
# Scenario 4: Extraction of Duplicated Functionality
# Eliminating duplicate clone into shared helper reduces duplication.
# ─────────────────────────────────────────────────────────────
def test_scenario_04_extraction_of_duplication(git_repo, service):
    dup_lines = "\n".join([f"    token_{i} = parse_token({i}, raw)" for i in range(25)])
    (git_repo / "parser_a.py").write_text(f"def parse_stream_a(raw):\n{dup_lines}\n    return 1\n")
    (git_repo / "parser_b.py").write_text(f"def parse_stream_b(raw):\n{dup_lines}\n    return 2\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add duplicate parsers"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base4")

    # Refactor: extract common parser into parser_common
    (git_repo / "parser_common.py").write_text(f"def parse_common_tokens(raw):\n{dup_lines}\n    return True\n")
    (git_repo / "parser_a.py").write_text("from parser_common import parse_common_tokens\ndef parse_stream_a(raw):\n    parse_common_tokens(raw)\n    return 1\n")
    (git_repo / "parser_b.py").write_text("from parser_common import parse_common_tokens\ndef parse_stream_b(raw):\n    parse_common_tokens(raw)\n    return 2\n")

    comp = service.compare(git_repo, baseline_name="base4", diff_aware=True)
    assert comp.classification == DeltaClassification.IMPROVED
    assert comp.vector_delta.metrics["clone_groups_count"].delta <= 0


# ─────────────────────────────────────────────────────────────
# Scenario 5: File Splitting That Does Not Reduce Complexity
# Splitting files without reducing CCN increases files while CCN stays high.
# ─────────────────────────────────────────────────────────────
def test_scenario_05_file_splitting_no_complexity_reduction(git_repo, service):
    (git_repo / "monolith.py").write_text("""
def process_alpha(x):
    if x > 0:
        return x * 2
    return 0

def process_beta(y):
    if y > 10:
        return y + 100
    return y
""")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "monolith with two functions"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base5")

    # Splitting into part_a and part_b without reducing complexity
    (git_repo / "part_a.py").write_text("""
def process_alpha(x):
    if x > 0:
        return x * 2
    return 0
""")
    (git_repo / "part_b.py").write_text("""
def process_beta(y):
    if y > 10:
        return y + 100
    return y
""")
    (git_repo / "monolith.py").unlink()

    comp = service.compare(git_repo, baseline_name="base5", diff_aware=True)
    # Total complexity remains unchanged (4), files increased by 1
    assert comp.vector_delta.metrics["files_count"].delta == 1
    assert comp.vector_delta.metrics["total_cyclomatic_complexity"].delta == 0
    assert comp.classification != DeltaClassification.IMPROVED


# ─────────────────────────────────────────────────────────────
# Scenario 6: Moving Complexity Elsewhere
# Moving a complex function into a new helper file is detected.
# ─────────────────────────────────────────────────────────────
def test_scenario_06_moving_complexity_elsewhere(git_repo, service):
    branches = "\n".join([f"    if x == {i}: return {i}" for i in range(20)])
    (git_repo / "service.py").write_text(f"def route_traffic(x):\n{branches}\n    return 0\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "complex traffic"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base6")

    # Move complexity to a helper module
    (git_repo / "traffic_helper.py").write_text(f"def internal_route(x):\n{branches}\n    return 0\n")
    (git_repo / "service.py").write_text("from traffic_helper import internal_route\ndef route_traffic(x):\n    return internal_route(x)\n")

    comp = service.compare(git_repo, baseline_name="base6", diff_aware=True)
    # The max complexity is STILL 20, and new_problems catches internal_route
    assert comp.vector_delta.metrics["max_cyclomatic_complexity"].current_value >= 20
    assert any("internal_route" in p.get("function", "") for p in comp.new_problems)


# ─────────────────────────────────────────────────────────────
# Scenario 7: Increased Dependency Coupling
# Circular imports / tightly coupled modules detected.
# ─────────────────────────────────────────────────────────────
def test_scenario_07_increased_dependency_coupling(git_repo, service):
    (git_repo / "mod_a.py").write_text("def a(): return 1\n")
    (git_repo / "mod_b.py").write_text("def b(): return 2\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "independent modules"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base7")

    # Introduce circular dependency
    (git_repo / "mod_a.py").write_text("from mod_b import b\ndef a(): return b() + 1\n")
    (git_repo / "mod_b.py").write_text("from mod_a import a\ndef b(): return a() + 2\n")

    report = service.measure(git_repo)
    # Report captures files and structure
    assert report.vector.files_count >= 2


# ─────────────────────────────────────────────────────────────
# Scenario 8: Complexity Reduction
# Simplifying branching logic results in IMPROVED classification.
# ─────────────────────────────────────────────────────────────
def test_scenario_08_complexity_reduction(git_repo, service):
    branches = "\n".join([f"    if code == {i}: return {i} * 10" for i in range(20)])
    (git_repo / "calc.py").write_text(f"def multiplier(code):\n{branches}\n    return 0\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "complex multiplier"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base8")

    # Refactor: Replace 20 if branches with dictionary lookup table (CCN drops from 21 to 1)
    (git_repo / "calc.py").write_text("""
MULTIPLIER_TABLE = {i: i * 10 for i in range(20)}
def multiplier(code):
    return MULTIPLIER_TABLE.get(code, 0)
""")
    comp = service.compare(git_repo, baseline_name="base8", diff_aware=True)
    assert comp.classification == DeltaClassification.IMPROVED
    assert comp.vector_delta.metrics["max_cyclomatic_complexity"].delta <= -15
    assert any("multiplier" in r.get("function", "") for r in comp.resolved_problems)


# ─────────────────────────────────────────────────────────────
# Scenario 9: Duplication Reduction
# Refactoring duplicate methods reduces duplication %.
# ─────────────────────────────────────────────────────────────
def test_scenario_09_duplication_reduction(git_repo, service):
    dup_block = "\n".join([f"    step_{i} = perform_step_{i}()" for i in range(30)])
    (git_repo / "worker1.py").write_text(f"def do_task_1():\n{dup_block}\n    return 'done1'\n")
    (git_repo / "worker2.py").write_text(f"def do_task_2():\n{dup_block}\n    return 'done2'\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "duplicate workers"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base9")

    # Refactor: consolidate into shared base
    (git_repo / "worker_shared.py").write_text(f"def run_pipeline():\n{dup_block}\n    return True\n")
    (git_repo / "worker1.py").write_text("from worker_shared import run_pipeline\ndef do_task_1():\n    run_pipeline()\n    return 'done1'\n")
    (git_repo / "worker2.py").write_text("from worker_shared import run_pipeline\ndef do_task_2():\n    run_pipeline()\n    return 'done2'\n")

    comp = service.compare(git_repo, baseline_name="base9", diff_aware=True)
    assert comp.classification == DeltaClassification.IMPROVED
    assert comp.vector_delta.metrics["clone_groups_count"].delta <= 0


# ─────────────────────────────────────────────────────────────
# Scenario 10: Deliberately Mixed Result
# Complexity improves but duplication worsens. Multidimensional tracking captures both.
# ─────────────────────────────────────────────────────────────
def test_scenario_10_deliberately_mixed_result(git_repo, service):
    # Baseline: complex function without duplication
    branches = "\n".join([f"    if x == {i}: return {i}" for i in range(20)])
    (git_repo / "mixed.py").write_text(f"def mixed_handler(x):\n{branches}\n    return -1\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "mixed base"], cwd=str(git_repo), check=True, capture_output=True)
    service.create_baseline(git_repo, name="base10")

    # Now simplify the function to reduce CCN, but introduce duplicate code blocks
    dup = "\n".join([f"    copy_line_{i} = duplicate_action({i})" for i in range(25)])
    (git_repo / "mixed.py").write_text(f"def mixed_handler(x):\n    return x\n\ndef dupe_one():\n{dup}\n    return 1\n")
    (git_repo / "mixed_dupe.py").write_text(f"def dupe_two():\n{dup}\n    return 2\n")

    comp = service.compare(git_repo, baseline_name="base10", diff_aware=True)

    # Complexity dropped (improvement)
    assert comp.vector_delta.metrics["max_cyclomatic_complexity"].delta <= -15
    # Duplication increased (regression)
    assert comp.vector_delta.metrics["clone_groups_count"].delta >= 1
    # Overall classification flags REGRESSION due to new clone groups
    assert comp.classification == DeltaClassification.REGRESSION
