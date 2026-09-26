"""The mutation gate's own oracle, tested.

run_mutants.py decides what counts as a kill. Its history is the reason this file exists:
it once credited a kill on ANY non-zero exit, so a missing check file (pytest exit 4) or
a red baseline scored as "killed" and a perfect result could be manufactured by breaking
the run. test_mutant_catalogue.py checks the catalogue DATA; nothing checked the
classification logic itself, so a regression back to that shape would leave "N killed"
unchallenged. These tests pin run_one's verdicts with a stubbed pytest and a synthetic
tree — no real suite runs, nothing under the repository is copied or written.

Kept out of every catalogue entry's `check` for the same reason test_mutant_catalogue is:
it is a test OF the runner, not of the properties the runner measures.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

MUTANTS_DIR = Path(__file__).resolve().parent / "mutants"


@pytest.fixture
def runner(monkeypatch):
    """run_mutants loaded by path, its import-time sys.path write unwound and its very
    generic `catalogue` import satisfied through monkeypatch so neither leaks."""
    cat_spec = importlib.util.spec_from_file_location(
        "aviary_mutant_catalogue_for_runner_tests", MUTANTS_DIR / "catalogue.py")
    catalogue = importlib.util.module_from_spec(cat_spec)
    cat_spec.loader.exec_module(catalogue)
    monkeypatch.setitem(sys.modules, "catalogue", catalogue)
    spec = importlib.util.spec_from_file_location(
        "run_mutants_under_test", MUTANTS_DIR / "run_mutants.py")
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
    return module


MUTANT = dict(id="probe-mutant", pass_="0", target="science/target.py",
              check="science/check_test.py", why="a synthetic entry",
              find="X = 1\n", replace="X = 2\n")


@pytest.fixture
def synthetic_tree(runner, tmp_path, monkeypatch):
    """A one-file 'repository' and a copier that reproduces it — the real _copy_tree
    would copy this repository's science/ and demo/, which these tests never touch."""
    (tmp_path / "science").mkdir()
    (tmp_path / "science" / "check_test.py").write_text("def test_t():\n    pass\n")
    (tmp_path / "science" / "target.py").write_text("X = 1\n")

    def copy(root: Path):
        (root / "science").mkdir(parents=True)
        (root / "science" / "target.py").write_text(
            (tmp_path / "science" / "target.py").read_text())

    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(runner, "_copy_tree", copy)
    monkeypatch.setattr(runner, "_baseline_is_green", lambda check: True)
    return tmp_path


def _pytest_returning(monkeypatch, runner, returncode, stdout=""):
    calls = []

    def fake(root, check):
        calls.append((root, check))
        return subprocess.CompletedProcess(args=[], returncode=returncode,
                                           stdout=stdout, stderr="")

    monkeypatch.setattr(runner, "_pytest", fake)
    return calls


def test_a_green_run_after_mutation_is_a_survivor(runner, synthetic_tree, monkeypatch):
    _pytest_returning(monkeypatch, runner, 0, "1 passed in 0.01s\n")
    status, detail = runner.run_one(MUTANT)
    assert status == "SURVIVED"
    assert "1 passed" in detail


def test_exit_one_with_a_failure_summary_is_a_kill_naming_the_killer(runner, synthetic_tree, monkeypatch):
    _pytest_returning(monkeypatch, runner, 1,
                      "FAILED science/check_test.py::test_t - assert\n1 failed in 0.01s\n")
    status, detail = runner.run_one(MUTANT)
    assert status == "killed"
    assert "test_t" in detail


def test_exit_one_without_a_failure_summary_is_not_a_kill(runner, synthetic_tree, monkeypatch):
    """Exit 1 alone is not evidence a TEST noticed anything."""
    _pytest_returning(monkeypatch, runner, 1, "something went wrong\n")
    status, _ = runner.run_one(MUTANT)
    assert status == "BROKEN-CHECK"


@pytest.mark.parametrize("returncode", [2, 3, 4, 5], ids=["interrupted", "internal", "usage", "no-tests"])
def test_any_other_exit_code_is_broken_even_with_failure_text(runner, synthetic_tree, monkeypatch, returncode):
    """The original defect: every non-zero exit was scored as a kill. A usage error or
    zero collected tests must never count, even if the output happens to say 'failed'."""
    _pytest_returning(monkeypatch, runner, returncode, "1 failed\n")
    status, detail = runner.run_one(MUTANT)
    assert status == "BROKEN-CHECK"
    assert str(returncode) in detail


def test_a_red_baseline_is_broken_and_the_mutant_is_never_run(runner, synthetic_tree, monkeypatch):
    monkeypatch.setattr(runner, "_baseline_is_green", lambda check: False)
    calls = _pytest_returning(monkeypatch, runner, 1, "1 failed\n")
    status, detail = runner.run_one(MUTANT)
    assert status == "BROKEN-CHECK"
    assert "BEFORE" in detail
    assert calls == [], "a kill against a red baseline would prove nothing, so no run"


def test_a_missing_check_file_is_broken_not_killed(runner, synthetic_tree, monkeypatch):
    calls = _pytest_returning(monkeypatch, runner, 4, "")
    status, _ = runner.run_one({**MUTANT, "check": "science/absent_test.py"})
    assert status == "BROKEN-CHECK"
    assert calls == []


@pytest.mark.parametrize("occurrences", [0, 2])
def test_an_anchor_that_does_not_occur_exactly_once_is_stale(runner, synthetic_tree, monkeypatch, occurrences):
    (synthetic_tree / "science" / "target.py").write_text("X = 1\n" * occurrences)
    calls = _pytest_returning(monkeypatch, runner, 1, "1 failed\n")
    status, detail = runner.run_one(MUTANT)
    assert status == "CATALOGUE-STALE"
    assert f"{occurrences}x" in detail
    assert calls == []


def test_the_mutation_is_applied_to_the_copy_not_the_source(runner, synthetic_tree, monkeypatch):
    seen = {}

    def fake(root, check):
        seen["mutated"] = (root / "science" / "target.py").read_text()
        return subprocess.CompletedProcess(args=[], returncode=1,
                                           stdout="FAILED a::t\n1 failed\n", stderr="")

    monkeypatch.setattr(runner, "_pytest", fake)
    runner.run_one(MUTANT)
    assert seen["mutated"] == "X = 2\n"
    assert (synthetic_tree / "science" / "target.py").read_text() == "X = 1\n"


@pytest.mark.parametrize("verdicts, expected_exit", [
    (["killed"], 0),
    (["killed", "SURVIVED"], 1),
    (["killed", "CATALOGUE-STALE"], 1),
    (["killed", "BROKEN-CHECK"], 1),
])
def test_main_exits_nonzero_unless_every_mutant_was_killed(runner, monkeypatch, capsys, verdicts, expected_exit):
    entries = [{**MUTANT, "id": f"m{i}"} for i in range(len(verdicts))]
    outcomes = dict(zip((e["id"] for e in entries), verdicts))
    monkeypatch.setattr(runner, "MUTANTS", entries)
    monkeypatch.setattr(runner, "RETIRED", [])
    monkeypatch.setattr(runner, "run_one", lambda m: (outcomes[m["id"]], ""))
    monkeypatch.setattr(sys, "argv", ["run_mutants.py"])
    assert runner.main() == expected_exit
    out = capsys.readouterr().out
    assert f"{verdicts.count('killed')}/{len(verdicts)} live mutants killed" in out


def test_the_ignore_rule_drops_the_referee_tree_only_directly_under_a_tests_directory(runner):
    """Basenames, at the right level: the shutil.ignore_patterns form this replaced
    fnmatched basenames only and therefore matched nothing for a two-part pattern."""
    referee = "seal" + "ed"        # built, so this test file never spells the path
    assert runner._ignore("/x/tests", [referee, "keep.py"]) == {referee}
    assert runner._ignore("/x/other", [referee, "keep.py"]) == set()
    assert runner._ignore("/x", ["__pycache__", "out", "keep.py"]) == {"__pycache__", "out"}
