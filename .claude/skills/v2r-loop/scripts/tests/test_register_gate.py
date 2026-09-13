"""Regression tests for the gate's refusal paths.

Every test here encodes a way the gate could silently stop being a gate.
Findings 1-4 of the trust-core review; each one closed a unit, or burned its
attempts, without a sealed test ever asserting anything.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _claimed(git_repo, register_data, body: str):
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    (sealed / "test_u001.py").write_text(body)
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register.save(register.REGISTER, register_data)


def test_close_halts_when_every_test_is_skipped(git_repo, register_data):
    """Exit 0 with nothing asserted must never close a unit."""
    _claimed(git_repo, register_data, (
        "import pytest\n\n"
        "@pytest.mark.skip(reason='not implemented')\n"
        "def test_should_not_close():\n    assert False\n"
    ))

    assert register.main(["close", "U-001"]) == 3
    assert register.unit_by_id(register.load(register.REGISTER), "U-001")["state"] == "claimed"


def test_close_halts_when_pytest_cannot_be_imported(monkeypatch, git_repo, register_data):
    """A gate that never ran must not look like a gate that ran and failed."""
    _claimed(git_repo, register_data, "def test_ok():\n    assert True\n")
    monkeypatch.setattr(register, "_pytest_available", lambda: False)

    assert register.main(["close", "U-001"]) == 3

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"
    assert unit["attempts"] == 0, "a missing gate must not consume the attempt budget"


def test_close_refuses_a_unit_that_was_never_claimed(git_repo, register_data):
    _claimed(git_repo, register_data, "def test_ok():\n    assert True\n")
    data = register.load(register.REGISTER)
    register.unit_by_id(data, "U-001")["state"] = "open"
    register.save(register.REGISTER, data)

    assert register.main(["close", "U-001"]) == 2
    assert register.unit_by_id(register.load(register.REGISTER), "U-001")["state"] == "open"


def test_close_does_not_record_closed_when_the_commit_fails(monkeypatch, git_repo, register_data):
    """The register must never claim `closed` with no commit behind it."""
    _claimed(git_repo, register_data, "def test_ok():\n    assert True\n")
    real_git = register.git

    def flaky_git(*args):
        if args and args[0] == "commit":
            raise subprocess.CalledProcessError(1, "git commit")
        return real_git(*args)

    monkeypatch.setattr(register, "git", flaky_git)

    assert register.main(["close", "U-001"]) == 3
    assert register.unit_by_id(register.load(register.REGISTER), "U-001")["state"] == "claimed"


def test_unknown_unit_id_is_a_clean_error_not_a_traceback(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)

    assert register.main(["close", "U-999"]) == 2
