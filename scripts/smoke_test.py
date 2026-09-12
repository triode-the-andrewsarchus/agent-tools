"""Smoke test validating all analyzers, baseline, comparison, and reuse finder."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from architecture_fitness.service import ArchitectureFitnessService


def main() -> None:
    print("=== Architecture Fitness Smoke Test ===")
    svc = ArchitectureFitnessService()

    with tempfile.TemporaryDirectory(prefix="fitness_smoke_") as tmp_dir:
        tmp_root = Path(tmp_dir)

        # Create a sample multi-file codebase
        src_dir = tmp_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        service_code = """\"\"\"User service module.\"\"\"
def authenticate_user(username, password):
    if not username or not password:
        return False
    if len(password) < 8:
        return False
    return True

def hash_token(token_str):
    res = 0
    for ch in token_str:
        res = (res * 31 + ord(ch)) % 1000000007
    return str(res)
"""
        with open(src_dir / "service.py", "w") as f:
            f.write(service_code)

        utils_code = """\"\"\"Utility functions.\"\"\"
def validate_credentials(user, pwd):
    if not user or not pwd:
        return False
    if len(pwd) < 8:
        return False
    return True
"""
        with open(src_dir / "utils.py", "w") as f:
            f.write(utils_code)

        print("1. Running measurement on sample codebase...")
        rep = svc.measure(tmp_root)
        print(f"   Files: {rep.vector.files_count}, NLOC: {rep.vector.lines_of_code}, Functions: {rep.vector.functions_count}")
        print(f"   CCN Total: {rep.vector.total_cyclomatic_complexity}, Avg CCN: {rep.vector.avg_cyclomatic_complexity}, Max CCN: {rep.vector.max_cyclomatic_complexity}")
        print(f"   Duplication: {rep.vector.duplication_percentage}%, Clones: {rep.vector.clone_groups_count}")
        print(f"   Tool statuses: {[(k, v.available, v.duration_seconds) for k, v in rep.tools.items()]}")

        print("\n2. Establishing baseline...")
        record, base_rep = svc.create_baseline(tmp_root, name="baseline-1")
        print(f"   Baseline saved: {record.id} with {record.functions_count} functions")

        print("\n3. Testing reuse candidate finder...")
        candidates = svc.reuse_candidates(tmp_root, query="authenticate user credentials")
        print(f"   Found {len(candidates)} candidates:")
        for c in candidates:
            print(f"     * {c.symbol_name} ({c.file_path}:{c.line_number}) - conf {c.confidence:.2f}: {c.relevance_reason}")

        print("\n4. Introducing duplicate / high complexity code and testing compare...")
        bad_code = """
def complex_dispatcher(op, val1, val2, flag_a, flag_b):
    if op == 'add':
        if flag_a:
            if flag_b:
                return val1 + val2 + 10
            return val1 + val2 + 5
        return val1 + val2
    elif op == 'sub':
        if flag_a:
            return val1 - val2 - 5
        return val1 - val2
    elif op == 'mul':
        if flag_b:
            return val1 * val2 * 2
        return val1 * val2
    elif op == 'div':
        if val2 == 0:
            return 0
        return val1 / val2
    elif op == 'mod':
        if val2 == 0:
            return 0
        return val1 % val2
    return 0
"""
        with open(src_dir / "dispatcher.py", "w") as f:
            f.write(bad_code)

        comp = svc.compare(tmp_root, baseline_name="baseline-1", diff_aware=False)
        print(f"   Classification: {comp.classification.value}")
        print("   Header Preview:")
        for line in comp.summary_header.splitlines()[:10]:
            print(f"     {line}")

        print("\n5. Testing hotspots identification...")
        hotspots = svc.hotspots(tmp_root, top_n=5)
        print(f"   Hotspots count: {len(hotspots)}")
        for h in hotspots:
            print(f"     * [{h.severity}] {h.title} @ {h.location}")

    print("\n=== SMOKE TEST PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
