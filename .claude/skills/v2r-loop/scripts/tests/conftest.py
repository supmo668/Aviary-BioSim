import subprocess
from pathlib import Path

import pytest


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A real git repo with one commit, cwd set to it."""
    git("init", "-q", "-b", "main", cwd=tmp_path)
    git("config", "user.email", "test@example.com", cwd=tmp_path)
    git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("seed\n")
    git("add", "README.md", cwd=tmp_path)
    git("commit", "-q", "-m", "seed", cwd=tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def register_data():
    return {
        "version": 1,
        "run": {
            "drain": 1,
            "seed": 1337,
            "instinct_pin": None,
            "ceilings": {
                "max_drains": 3,
                "max_attempts": 3,
                "max_wall_clock_s": 21600,
                "max_spend_usd": 25,
            },
        },
        "units": [
            {
                "id": "U-001",
                "satisfies": "R1",
                "statement": "SpendTracker.record accumulates per-call cost",
                "stub": "skeleton/spend_tracker.py::SpendTracker.record",
                "sealed_test": "tests/sealed/v2r/test_u001.py",
                "sealed_test_sha": None,
                "state": "open",
                "attempts": 0,
                "pre_claim_sha": None,
                "evidence": None,
                "park_branch": None,
            },
            {
                "id": "U-002",
                "satisfies": "R1",
                "statement": "SpendTracker.total sums recorded costs",
                "stub": "skeleton/spend_tracker.py::SpendTracker.total",
                "sealed_test": "tests/sealed/v2r/test_u002.py",
                "sealed_test_sha": None,
                "state": "closed",
                "attempts": 1,
                "pre_claim_sha": None,
                "evidence": None,
                "park_branch": None,
            },
        ],
    }
