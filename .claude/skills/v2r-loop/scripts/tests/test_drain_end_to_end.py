import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _fixture_drain(git_repo, register_data):
    """One satisfiable unit, one deliberately unsatisfiable one."""
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    (sealed / "test_u001.py").write_text("def test_ok():\n    assert True\n")
    (sealed / "test_u002.py").write_text("def test_never():\n    assert False\n")
    register_data["units"][1]["state"] = "open"
    register_data["units"][1]["attempts"] = 0
    register.save(register.REGISTER, register_data)


def _drain(git_repo):
    while (unit_id := register.next_open(register.load(register.REGISTER))):
        register.main(["claim", unit_id])
        register.main(["seal", unit_id])
        while register.main(["close", unit_id]) == 1:
            data = register.load(register.REGISTER)
            unit = register.unit_by_id(data, unit_id)
            if register.attempts_exhausted(unit, data):
                ev = register.V2R_DIR / "ev.out"
                ev.write_text("sealed test failed\n")
                register.main(["park", unit_id, "--evidence", str(ev)])
                break


def test_drain_closes_what_it_can_and_parks_the_rest(git_repo, register_data):
    _fixture_drain(git_repo, register_data)
    register.main(["drain-start", "--drain", "1", "--seed", "1337"])

    _drain(git_repo)
    register.main(["drain-end", "--outcome", "completed"])

    data = register.load(register.REGISTER)
    assert register.unit_by_id(data, "U-001")["state"] == "closed"
    assert register.unit_by_id(data, "U-002")["state"] == "parked"


def test_every_commit_on_the_branch_is_green(git_repo, register_data):
    _fixture_drain(git_repo, register_data)
    register.main(["drain-start", "--drain", "1", "--seed", "1337"])

    _drain(git_repo)

    subjects = register.git("log", "--pretty=%s").splitlines()
    assert any(s.startswith("U-001") for s in subjects)
    assert not any("parked attempt" in s for s in subjects)


def test_the_parked_unit_leaves_its_attempt_on_a_branch(git_repo, register_data):
    _fixture_drain(git_repo, register_data)
    register.main(["drain-start", "--drain", "1", "--seed", "1337"])

    _drain(git_repo)

    assert "park/U-002" in register.git("branch", "--list", "park/U-002")
