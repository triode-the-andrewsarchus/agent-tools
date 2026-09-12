"""Tests for individual analyzer runners and error handling."""

from pathlib import Path
from unittest.mock import patch
import pytest

from architecture_fitness.config import FitnessConfig
from architecture_fitness.runners.jscpd_runner import JscpdRunner
from architecture_fitness.runners.lizard_runner import LizardRunner
from architecture_fitness.runners.valknut_runner import ValknutRunner


def test_lizard_runner_basic(temp_dir):
    src = temp_dir / "sample.py"
    src.write_text("""def compute(a, b):
    if a > 0:
        if b > 0:
            return a + b
    return 0
""")
    runner = LizardRunner()
    status, functions, summary = runner.run(temp_dir)

    assert status.available is True
    assert len(functions) == 1
    assert functions[0].name == "compute"
    assert functions[0].cyclomatic_complexity == 3
    assert summary["files_count"] == 1


def test_lizard_runner_excludes(temp_dir):
    config = FitnessConfig(exclude_paths=["**/ignore_me/**", "*.tmp.py"])
    runner = LizardRunner(config)

    sub = temp_dir / "ignore_me"
    sub.mkdir()
    (sub / "bad.py").write_text("def should_ignore():\n    pass\n")
    (temp_dir / "test.tmp.py").write_text("def should_ignore_too():\n    pass\n")
    (temp_dir / "good.py").write_text("def keep():\n    pass\n")

    status, functions, summary = runner.run(temp_dir)
    assert len(functions) == 1
    assert functions[0].name == "keep"


def test_lizard_runner_missing(temp_dir):
    with patch("architecture_fitness.runners.lizard_runner.LIZARD_LIB_AVAILABLE", False), \
         patch("shutil.which", return_value=None):
        runner = LizardRunner()
        status, functions, summary = runner.run(temp_dir)
        assert status.available is False
        assert "not installed" in status.error


def test_jscpd_runner_basic(temp_dir):
    f1 = temp_dir / "file1.py"
    f2 = temp_dir / "file2.py"
    dup_block = "\n".join([f"    val_{i} = calculate_value({i})" for i in range(20)])
    f1.write_text(f"def process_one():\n{dup_block}\n    return True\n")
    f2.write_text(f"def process_two():\n{dup_block}\n    return False\n")

    runner = JscpdRunner()
    status, duplicates, stats = runner.run(temp_dir)

    assert status.available is True
    assert len(duplicates) >= 1
    assert stats["total"]["clones"] >= 1


def test_jscpd_runner_missing(temp_dir):
    with patch("shutil.which", return_value=None):
        runner = JscpdRunner()
        status, duplicates, stats = runner.run(temp_dir)
        assert status.available is False
        assert "not installed" in status.error


def test_valknut_runner_basic(temp_dir):
    src = temp_dir / "main.py"
    src.write_text("""def add(x, y):
    return x + y
""")
    runner = ValknutRunner()
    status, findings, data = runner.run(temp_dir)

    assert status.available is True
    assert "summary" in data
    assert data["summary"]["total_files"] == 1


def test_valknut_runner_missing(temp_dir):
    with patch("shutil.which", return_value=None):
        runner = ValknutRunner()
        status, findings, data = runner.run(temp_dir)
        assert status.available is False
        assert "not installed" in status.error


def test_valknut_malformed_output(temp_dir):
    runner = ValknutRunner()
    with patch.object(runner, "get_version", return_value="1.5.1"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Corrupted syntax error"
        status, findings, data = runner.run(temp_dir)
        assert status.error is not None
