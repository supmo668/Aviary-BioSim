import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_round_trip_preserves_units(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    loaded = register.load(register.REGISTER)
    assert loaded == register_data


def test_next_returns_first_open_unit(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    assert register.next_open(register_data) == "U-001"


def test_next_returns_none_when_nothing_open(git_repo, register_data):
    for unit in register_data["units"]:
        unit["state"] = "closed"
    assert register.next_open(register_data) is None


def test_next_skips_parked_units(git_repo, register_data):
    register_data["units"][0]["state"] = "parked"
    assert register.next_open(register_data) is None


def test_claim_marks_unit_and_records_pre_claim_sha(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)

    assert register.main(["claim", "U-001"]) == 0

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"
    assert unit["pre_claim_sha"] == register.head_sha()


def test_claim_refuses_a_unit_that_is_not_open(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)

    assert register.main(["claim", "U-002"]) == 2

    unit = register.unit_by_id(register.load(register.REGISTER), "U-002")
    assert unit["state"] == "closed"
