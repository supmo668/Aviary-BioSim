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


@pytest.mark.parametrize("target", [".V2R", ".v2r/sub", "link"])
def test_refuses_any_spelling_or_descendant_of_the_live_dir(tmp_path, target):
    """QG Q5: on a case-insensitive filesystem `.V2R` IS `.v2r`; a subdirectory of the live
    dir or a symlink to it is inside it. Each must be refused and leave the live register intact."""
    m = load()
    live = tmp_path / ".v2r"
    live.mkdir()
    (live / "register.yaml").write_text("version: 1\n")
    (tmp_path / "link").symlink_to(live, target_is_directory=True)
    assert m.main(tmp_path, target=target) == 2
    assert (live / "register.yaml").read_text() == "version: 1\n"
    assert not (live / "run-record-1.yaml").exists()
    assert not (live / "sub").exists()


def _live(tmp_path):
    live = tmp_path / ".v2r"
    live.mkdir()
    (live / "register.yaml").write_text("version: 1\n")
    (live / "parked").mkdir()
    return live


def _assert_live_untouched(live):
    assert (live / "register.yaml").read_text() == "version: 1\n"
    assert not (live / "run-record-1.yaml").exists()
    assert list((live / "parked").iterdir()) == []
    assert not (live / ".v2r-demo").exists()


def test_refuses_a_root_that_is_or_lies_inside_the_live_dir(tmp_path, capsys):
    """QG F05(b): the guard compared ROOT/target against ROOT/.v2r only, so ROOT=.v2r with
    --target . overwrote the live register, and the default target wrote .v2r/.v2r-demo/."""
    m = load()
    live = _live(tmp_path)
    assert m.main(live, target=".") == 2
    assert m.main(live) == 2
    assert m.main(live / "parked", target="x") == 2
    _assert_live_untouched(live)
    assert ".v2r" in capsys.readouterr().err


def test_refuses_an_absolute_target_that_is_a_live_dir_elsewhere(tmp_path):
    """QG F05(c): a live directory outside ROOT is still a live directory."""
    m = load()
    other = tmp_path / "other"
    other.mkdir()
    live = _live(other)
    root = tmp_path / "root"
    root.mkdir()
    assert m.main(root, target=str(live)) == 2
    assert m.main(root, target="../other/.v2r") == 2
    _assert_live_untouched(live)


@pytest.mark.parametrize("link", ["register.yaml", "parked", "run-record-1.yaml"])
def test_refuses_to_write_through_a_symlink_inside_the_target(tmp_path, link):
    """QG F05(d): open("w") and mkdir(exist_ok=True) follow symlinks; a planted link inside
    .v2r-demo/ redirected the fixture into the live directory with rc 0."""
    m = load()
    live = _live(tmp_path)
    demo = tmp_path / ".v2r-demo"
    demo.mkdir()
    (demo / link).symlink_to(live / link, target_is_directory=(link == "parked"))
    assert m.main(tmp_path) == 2
    _assert_live_untouched(live)


@pytest.mark.parametrize("target", ["", "."])
def test_refuses_an_empty_target_that_would_write_into_root(tmp_path, target):
    m = load()
    assert m.main(tmp_path, target=target) == 2
    assert not (tmp_path / "register.yaml").exists()


def test_cli_target_flag_reaches_main(tmp_path):
    import subprocess, sys as _sys
    r = subprocess.run([_sys.executable, "-B", str(SEEDER), str(tmp_path), "--target", "demo2"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "demo2" / "register.yaml").exists()
    r = subprocess.run([_sys.executable, "-B", str(SEEDER), str(tmp_path), "--target", ".v2r"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and ".v2r" in r.stderr


def test_fixture_evidence_resolves_inside_the_fixture_dir_and_the_register_is_marked(tmp_path):
    """QG Q28: the dashboard resolves a unit's evidence against the run dir's parent, so a
    fixture pointing at `.v2r/parked/...` shows live evidence (or none) under a fixture.
    Every evidence path must land inside the fixture dir, and the register itself must
    carry the fixture mark, not only the run records."""
    import yaml
    m = load()
    assert m.main(tmp_path) == 0
    target = tmp_path / ".v2r-demo"
    reg = yaml.safe_load((target / "register.yaml").read_text())
    assert reg["produced_by"] == m.FIXTURE_MARK
    evs = [u["evidence"] for u in reg["units"] if u["evidence"]]
    assert evs, "the fixture parks units, so it must carry evidence"
    for ev in evs:
        p = (target.parent / ev).resolve()
        assert p.exists(), ev
        assert p.is_relative_to(target.resolve()), ev
