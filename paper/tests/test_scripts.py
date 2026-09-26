"""Standing rules 2 and 3 of the white-paper plan, asserted.

Rule 2: every run saves its exact config next to its output — one implementation,
paper/scripts/_provenance.py, that every script calls.
Rule 3: a missing or empty --inputs directory is an ERROR (exit 2) that NAMES the path
checked. Never a finding of "unrecoverable" against a tree that never had the files.
"""
import json

import pytest


def test_provenance_block_names_every_required_field(prov):
    blk = prov.block(inputs_path="/nowhere", extra={"seed": 0})
    for k in ("git_sha", "recorded_at", "inputs_path", "python", "seed"):
        assert k in blk, k
    assert len(blk["git_sha"]) == 40
    assert blk["recorded_at"].endswith("Z")
    assert blk["inputs_path"] == "/nowhere"


def test_provenance_block_records_versions_and_says_when_a_module_is_absent(prov):
    blk = prov.block(inputs_path=None, modules=("json", "module_that_does_not_exist_xq"))
    assert blk["inputs_path"] is None
    assert "json" in blk["versions"]
    assert blk["versions"]["module_that_does_not_exist_xq"].startswith("not importable")


def test_require_inputs_errors_on_missing_dir_and_names_the_path(prov, tmp_path, capsys):
    missing = tmp_path / "not-there"
    with pytest.raises(SystemExit) as e:
        prov.require_inputs(missing)
    assert e.value.code == 2
    # the message must NAME the path checked, on stderr and in the recorded error
    assert str(missing) in prov.LAST_ERROR
    assert str(missing) in capsys.readouterr().err


def test_require_inputs_errors_on_empty_dir(prov, tmp_path):
    with pytest.raises(SystemExit) as e:
        prov.require_inputs(tmp_path)
    assert e.value.code == 2
    assert "empty" in prov.LAST_ERROR and str(tmp_path) in prov.LAST_ERROR


def test_require_inputs_returns_the_path_when_it_holds_something(prov, tmp_path):
    (tmp_path / "a.json").write_text("{}")
    assert prov.require_inputs(str(tmp_path)) == tmp_path


# --- A1: the referee command's could-not-run branches, without running the suite --------
import os
import subprocess
from pathlib import Path as _Path

REPO = _Path(__file__).resolve().parents[2]
REFEREE_SH = REPO / "paper" / "scripts" / "sealed_suite_results.sh"


def _run_referee_sh(env_extra: dict, path: str | None = None):
    env = dict(os.environ, **env_extra)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(["/bin/sh", str(REFEREE_SH)], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=300)


def _assert_could_not_run(r, naming: str):
    """The shape that must never look like a failing suite: exit 3, NOTHING on stdout,
    one COULD-NOT-RUN line on stderr naming what was missing."""
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert r.stdout == "", r.stdout
    assert r.stderr.startswith("COULD-NOT-RUN: "), r.stderr
    assert naming in r.stderr, r.stderr


def test_referee_command_refuses_an_unknown_commit():
    _assert_could_not_run(_run_referee_sh({"DRAIN1_END_COMMIT": "0000000"}), "0000000")


def test_referee_command_refuses_when_a_tool_is_missing():
    _assert_could_not_run(_run_referee_sh({}, path="/nonexistent-for-this-test"), "is not on PATH")


def test_referee_command_refuses_a_missing_suite_directory():
    _assert_could_not_run(_run_referee_sh({"SUITE_PATH": "demo/absent-for-this-test"}), "no test path")


def test_referee_command_reports_zero_collected_as_could_not_run():
    """A module with no tests in it: pytest collects nothing and exits 5. That is the one
    case a lazy referee command turns into a pass. (A directory is not used here: pytest
    would recurse into every subtree beneath it.)"""
    _assert_could_not_run(_run_referee_sh({"SUITE_PATH": "demo/__init__.py"}), "zero tests collected")


# --- the junit -> RESULT converter, on synthetic reports ---------------------------------

JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="4">
  <testcase classname="pkg.test_a" name="test_one"/>
  <testcase classname="pkg.test_a" name="test_two"><failure message="x"/></testcase>
  <testcase classname="pkg.test_b" name="test_three"><skipped message="y"/></testcase>
  <testcase classname="pkg.test_b" name="test_four"><error message="z"/></testcase>
</testsuite></testsuites>
"""


def test_junit_converter_emits_a_plan_and_one_result_per_case(script, tmp_path, capsys):
    J = script("junit_to_results")
    (tmp_path / "junit.xml").write_text(JUNIT)
    assert J.main(["x", str(tmp_path / "junit.xml"), "abc1234"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "PLAN 4"
    assert out[1:5] == ["RESULT pass test_a/test_one", "RESULT fail test_a/test_two",
                        "RESULT skip test_b/test_three", "RESULT fail test_b/test_four"]
    assert out[5] == "# archived commit abc1234"
    assert "message" not in "\n".join(out), "no assertion text may reach the output"


def test_junit_converter_treats_zero_testcases_as_could_not_run(script, tmp_path, capsys):
    J = script("junit_to_results")
    (tmp_path / "junit.xml").write_text('<testsuites><testsuite name="s" tests="0"/></testsuites>')
    assert J.main(["x", str(tmp_path / "junit.xml"), "abc1234"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "zero testcases" in captured.err


def test_junit_converter_treats_an_unreadable_report_as_could_not_run(script, tmp_path, capsys):
    J = script("junit_to_results")
    (tmp_path / "junit.xml").write_text("<not xml")
    assert J.main(["x", str(tmp_path / "junit.xml"), "abc1234"]) == 3
    assert capsys.readouterr().out == ""


# --- the evidence recorder, against a stub referee ---------------------------------------

def _stub_referee(tmp_path, stdout: str, exit_code: int = 0):
    stub = tmp_path / "referee"
    stub.write_text(f"#!/bin/sh\nprintf '%s\\n' '{stdout}'\nexit {exit_code}\n")
    stub.chmod(0o755)
    return str(stub)


def test_recorder_labels_measured_only_on_a_clean_verdict(script, tmp_path):
    R = script("record_referee")
    out = tmp_path / "drain1-rerun.json"
    ref = _stub_referee(tmp_path, '{"total":6,"passed":6,"failed":0,"skipped":0}')
    assert R.main(["--referee", ref, "--out", str(out), "--commit", "abc1234"]) == 0
    d = json.loads(out.read_text())
    assert d["label"].startswith("measured (re-run, ")
    assert d["referee"]["total"] == 6 and d["archived_commit"] == "abc1234"
    assert d["provenance"]["referee_command"] == "sh paper/scripts/sealed_suite_results.sh"


@pytest.mark.parametrize("stdout, code", [
    ("", 0),                                                       # could not run: no results
    ('{"total":6,"passed":5,"failed":1,"skipped":0}', 1),         # ran and failed
    ('{"total":6,"passed":5,"failed":0,"skipped":1}', 1),         # a skip is not a pass
    ("not json at all", 0),                                        # unreadable
], ids=["no-results", "failed", "skipped", "unreadable"])
def test_recorder_records_not_measured_and_exits_2_otherwise(script, tmp_path, stdout, code):
    R = script("record_referee")
    out = tmp_path / "drain1-rerun.json"
    assert R.main(["--referee", _stub_referee(tmp_path, stdout, code), "--out", str(out)]) == 2
    d = json.loads(out.read_text())
    assert d["label"].startswith("NOT MEASURED")
    assert d["referee_exit"] == code
