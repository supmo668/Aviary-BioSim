import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _seed(git_repo, register_data, test_body: str) -> Path:
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    test_file = sealed / "test_u001.py"
    test_file.write_text(test_body)
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register.save(register.REGISTER, register_data)
    return test_file


def test_close_succeeds_and_commits_when_the_sealed_test_passes(git_repo, register_data):
    _seed(git_repo, register_data, "def test_ok():\n    assert True\n")

    assert register.main(["close", "U-001"]) == 0

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "closed"
    assert "U-001" in register.git("log", "-1", "--pretty=%s")


def test_close_refuses_when_the_sealed_test_fails(git_repo, register_data):
    _seed(git_repo, register_data, "def test_no():\n    assert False\n")

    assert register.main(["close", "U-001"]) == 1

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"
    assert unit["attempts"] == 1


def test_close_halts_when_the_sealed_test_collects_nothing(git_repo, register_data):
    _seed(git_repo, register_data, "# no tests here\n")

    assert register.main(["close", "U-001"]) == 3

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"


def test_close_halts_when_the_sealed_test_is_missing(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "claimed"
    register.save(register.REGISTER, register_data)

    assert register.main(["close", "U-001"]) == 3


def test_close_halts_when_the_sealed_test_has_a_syntax_error(git_repo, register_data):
    _seed(git_repo, register_data, "def test_broken(:\n")

    assert register.main(["close", "U-001"]) == 3
