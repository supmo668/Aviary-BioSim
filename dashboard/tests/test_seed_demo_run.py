"""B1 — the demo seeder must never write the live run-state directory.

It once wrote a made-up 23-task, 3-pass fixture into `.v2r/` in the main checkout, over
pass 1's own record; a fixture there is indistinguishable from a real record to every
consumer. The seeder now writes a separate directory by default and refuses `.v2r`
whatever is or is not inside it. The module is loaded inside each test (never at import
time) so nothing leaks between tests.
"""
import importlib.util
from pathlib import Path

import pytest

SEEDER = Path(__file__).resolve().parents[1] / "seed_demo_run.py"


def load():
    spec = importlib.util.spec_from_file_location("seed_demo_run_under_test", SEEDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_target_is_a_separate_fixture_dir(tmp_path):
    m = load()
    assert m.main(tmp_path) == 0
    assert (tmp_path / ".v2r-demo" / "register.yaml").exists()
    assert not (tmp_path / ".v2r").exists(), "the seeder must never create the live dir"


def test_refuses_a_live_run_state_dir_and_writes_nothing(tmp_path, capsys):
    m = load()
    live = tmp_path / ".v2r"
    live.mkdir()
    (live / "register.yaml").write_text("version: 1\n")
    before = (live / "register.yaml").read_text()
    rc = m.main(tmp_path, target=".v2r")
    assert rc == 2
    assert (live / "register.yaml").read_text() == before
    assert not (live / "run-record-1.yaml").exists()
    assert ".v2r" in capsys.readouterr().err


def test_refuses_the_live_dir_even_when_empty(tmp_path):
    m = load()
    (tmp_path / ".v2r").mkdir()
    assert m.main(tmp_path, target=".v2r") == 2
    assert list((tmp_path / ".v2r").iterdir()) == []


def test_refuses_a_path_that_resolves_to_the_live_dir(tmp_path):
    """A different spelling of the same directory is the same directory."""
    m = load()
    (tmp_path / "sub").mkdir()
    assert m.main(tmp_path, target="sub/../.v2r") == 2
    assert not (tmp_path / ".v2r").exists()


def test_seeded_records_are_marked_as_fixture(tmp_path):
    import yaml
    m = load()
    m.main(tmp_path)
    for n in (1, 2, 3):
        rec = yaml.safe_load((tmp_path / ".v2r-demo" / f"run-record-{n}.yaml").read_text())
        assert rec["produced_by"] == "dashboard/seed_demo_run.py (FIXTURE — not a run that happened)"
