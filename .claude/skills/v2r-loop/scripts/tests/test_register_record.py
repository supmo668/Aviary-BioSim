import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_instinct_pin_is_none_before_any_instinct_exists(git_repo):
    assert register.instinct_pin() is None


def test_instinct_pin_is_the_tree_sha_of_the_store(git_repo):
    store = git_repo / ".aiadlc" / "instincts"
    store.mkdir(parents=True)
    (store / "prefer-uv-run.md").write_text("always invoke via uv run\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "add instinct")

    assert register.instinct_pin() == register.git("rev-parse", "HEAD:.aiadlc/instincts")


def test_instinct_pin_changes_when_the_store_changes(git_repo):
    store = git_repo / ".aiadlc" / "instincts"
    store.mkdir(parents=True)
    (store / "one.md").write_text("first\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "one")
    first = register.instinct_pin()

    (store / "two.md").write_text("second\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "two")

    assert register.instinct_pin() != first


def test_drain_end_writes_a_run_record(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "parked"
    register.save(register.REGISTER, register_data)

    assert register.main(["drain-end", "--outcome", "completed"]) == 0

    record = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())
    assert record["drain"] == 1
    assert record["seed"] == 1337
    assert record["closed"] == ["U-002"]
    assert record["parked"] == ["U-001"]
    assert record["outcome"] == "completed"
    assert record["register_sha"].startswith("sha256:")


def test_run_record_is_stable_for_identical_register_state(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    register.main(["drain-end", "--outcome", "completed"])
    first = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())

    register.main(["drain-end", "--outcome", "completed"])
    second = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())

    assert first["register_sha"] == second["register_sha"]
    assert first["closed"] == second["closed"]
    assert first["parked"] == second["parked"]
