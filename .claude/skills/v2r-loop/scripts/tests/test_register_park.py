import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _claimed_with_attempt(git_repo, register_data) -> str:
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register_data["units"][0]["attempts"] = 3
    register.save(register.REGISTER, register_data)
    clean_tree = register.git("rev-parse", "HEAD^{tree}")
    (git_repo / "half_built.py").write_text("def record(:  # broken\n")
    return clean_tree


def test_park_restores_the_tree_exactly(git_repo, register_data):
    clean_tree = _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    assert register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"]) == 0

    assert register.git("rev-parse", "HEAD^{tree}") == clean_tree
    assert not (git_repo / "half_built.py").exists()


def test_park_preserves_the_attempt_on_a_branch(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    assert "park/U-001" in register.git("branch", "--list", "park/U-001")
    assert "broken" in register.git("show", "park/U-001:half_built.py")


def test_park_marks_the_unit_and_keeps_the_evidence(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "parked"
    assert unit["park_branch"] == "park/U-001"
    assert Path(unit["evidence"]).read_text() == "pytest said no\n"


def test_park_does_not_touch_any_other_unit(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("nope\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    other = register.unit_by_id(register.load(register.REGISTER), "U-002")
    assert other["state"] == "closed"
    assert "blocked_by" not in other
