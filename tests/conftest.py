"""Pytest fixtures for Architecture Fitness test suite."""

import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest

from architecture_fitness.config import FitnessConfig
from architecture_fitness.service import ArchitectureFitnessService


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory(prefix="test_fitness_") as d:
        yield Path(d)


@pytest.fixture
def git_repo(temp_dir):
    """Initialize a git repository in temp_dir with an initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(temp_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(temp_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(temp_dir), check=True, capture_output=True)

    # Initial file
    init_file = temp_dir / "app.py"
    init_file.write_text("def hello(name):\n    return f'Hello, {name}'\n")
    subprocess.run(["git", "add", "."], cwd=str(temp_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(temp_dir), check=True, capture_output=True)
    return temp_dir


@pytest.fixture
def service():
    return ArchitectureFitnessService()
