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

def _stub_referee(tmp_path, stdout: str, exit_code: int = 0, stderr: str = ""):
    stub = tmp_path / "referee"
    stub.write_text(f"#!/bin/sh\nprintf '%s\\n' '{stdout}'\n"
                    f"printf '%s\\n' '{stderr}' >&2\nexit {exit_code}\n")
    stub.chmod(0o755)
    return str(stub)


def test_recorder_finds_the_coarse_json_when_the_referee_prints_more_after_it(script, tmp_path):
    """With --sign the referee prints lines after the JSON. Reading the LAST line labelled a
    signed, passing run NOT MEASURED — the wrong answer in the safe direction, still wrong."""
    R = script("record_referee")
    out = tmp_path / "drain1-rerun.json"
    ref = _stub_referee(tmp_path, '{"total":6,"passed":6,"failed":0,"skipped":0}\nreceipt written: x.md',
                        stderr="referee: signed sealed-suite receipt (Hash E abc1234)")
    assert R.main(["--referee", ref, "--out", str(out), "--commit", "abc1234"]) == 0
    d = json.loads(out.read_text())
    assert d["label"].startswith("measured (re-run, ")
    assert d["referee_receipt_hash_e"] == "abc1234"


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


# --- A2: pass 1 reconstructed from version control -------------------------------------

def test_drain1_from_git_finds_six_units_in_order_with_their_pre_claim_parents(script):
    D = script("drain1_from_git")
    rows = D.rows(first="28af3c4", last="2e00aa3")
    assert [r["unit"] for r in rows] == [f"U-00{i}" for i in range(1, 7)]
    assert all(r["requirement"].startswith("R") for r in rows)
    assert all(r["sealed_test"].startswith("demo/tests/") for r in rows)
    assert all(len(r["parent"]) == 40 for r in rows)
    assert all(r["label"] == "reconstructed" for r in rows)


def test_drain1_from_git_keeps_only_close_commits(script):
    """A skeleton commit and a coordination commit interleave in the range."""
    D = script("drain1_from_git")
    assert len(D.rows()) == 6


def test_drain1_from_git_errors_when_nothing_matches(script, tmp_path, capsys):
    D = script("drain1_from_git")
    # a one-commit range whose subject is not a close: the range's own first commit's parent
    assert D.main(["--out", str(tmp_path / "x.csv"), "--first", "8f6a8e6", "--last", "8f6a8e6"]) == 2
    assert "no close commits" in capsys.readouterr().err


# --- A2b: the recovered record --------------------------------------------------------

def _synthetic_record(tmp_path, script, tamper_one=False):
    """A record whose pre_claim_sha values come from the REAL close-commit parents — the
    check compares against history, so the fixture must be consistent with it."""
    D = script("drain1_from_git")
    rows = D.rows()[:2]
    parents = [r["parent"] for r in rows]
    if tamper_one:
        parents[1] = "0" * 40
    rec = tmp_path / "v2r"
    rec.mkdir()
    import yaml
    (rec / "register.yaml").write_text(yaml.safe_dump({"version": 1, "run": {"drain": 1}, "units": [
        {"id": r["unit"], "state": "closed", "attempts": 0, "pre_claim_sha": p, "sealed_test_sha": "x" * 64}
        for r, p in zip(rows, parents)]}))
    import hashlib
    reg_sha = "sha256:" + hashlib.sha256((rec / "register.yaml").read_bytes()).hexdigest()
    if tamper_one:
        reg_sha = "sha256:" + "a" * 64
    (rec / "run-record-1.yaml").write_text(yaml.safe_dump(
        {"drain": 1, "register_sha": reg_sha, "instinct_pin": None, "seed": 1,
         "closed": [r["unit"] for r in rows], "parked": [], "outcome": "completed"}))
    return rec


def _stub_register(tmp_path, exit_code):
    stub = tmp_path / "register"
    stub.write_text(f"#!/bin/sh\necho 'stub verify-record'\nexit {exit_code}\n")
    stub.chmod(0o755)
    return str(stub)


def test_record_check_errors_on_a_missing_record_dir_naming_the_path(script, tmp_path):
    C = script("drain1_record_check")
    missing = tmp_path / "absent"
    with pytest.raises(SystemExit) as e:
        C.main(["--record", str(missing), "--out", str(tmp_path / "o.json"), "--copy-to", str(tmp_path / "c")])
    assert e.value.code == 2


def test_record_check_verifies_the_chain_and_never_checks_the_test_digest(script, tmp_path):
    C = script("drain1_record_check")
    rec = _synthetic_record(tmp_path, script)
    out = tmp_path / "o.json"
    assert C.main(["--record", str(rec), "--register", _stub_register(tmp_path, 0),
                   "--out", str(out), "--copy-to", str(tmp_path / "copy")]) == 0
    d = json.loads(out.read_text())
    assert d["pre_claim_matches"] == 2 and d["units_checked"] == 2
    assert d["label"] == "recovered record; pre-claim chain verified 2/2; write-time provenance not established"
    assert d["sealed_test_sha"]["checked"] is False
    assert all(u["sealed_test_sha_checked"] is False for u in d["units"])
    assert d["register_verify_record"]["exit"] == 0 and d["register_verify_record"]["ran"] is True
    assert d["register_sha"]["matches_register_file"] is True
    assert d["register_verify_record"]["record_predates_provenance_format"] is True
    assert (tmp_path / "copy" / "register.yaml").exists()
    assert d["files"]["register.yaml"]["sha256"] == __import__("hashlib").sha256((rec / "register.yaml").read_bytes()).hexdigest()


def test_record_check_counts_a_broken_link_in_the_chain(script, tmp_path):
    C = script("drain1_record_check")
    rec = _synthetic_record(tmp_path, script, tamper_one=True)
    out = tmp_path / "o.json"
    assert C.main(["--record", str(rec), "--register", _stub_register(tmp_path, 3),
                   "--out", str(out), "--copy-to", str(tmp_path / "copy")]) == 0
    d = json.loads(out.read_text())
    assert d["pre_claim_matches"] == 1
    assert "verified 1/2" in d["label"]
    assert d["register_verify_record"]["exit"] == 3
    assert d["register_sha"]["matches_register_file"] is False


def test_record_check_never_writes_the_recovered_record(script, tmp_path):
    C = script("drain1_record_check")
    rec = _synthetic_record(tmp_path, script)
    before = {p.name: p.read_bytes() for p in rec.iterdir()}
    C.main(["--record", str(rec), "--register", _stub_register(tmp_path, 0),
            "--out", str(tmp_path / "o.json"), "--copy-to", str(tmp_path / "copy")])
    assert {p.name: p.read_bytes() for p in rec.iterdir()} == before


# --- A3a/b: the science input, fetched fresh and compared by hash ----------------------

INVENTED_ACC = "Q9ZZZ9"    # invented; matches the grammar; asserted to denote nothing


def test_science_input_errors_on_missing_inputs(script, tmp_path):
    S = script("science_input")
    with pytest.raises(SystemExit) as e:
        S.main(["--inputs", str(tmp_path / "absent"), "--out", str(tmp_path / "o.json")])
    assert e.value.code == 2


def _published_inputs(tmp_path, acc, seq="MAAAC"):
    inputs = tmp_path / "out"
    (inputs / "seqs").mkdir(parents=True)
    (inputs / "esm").mkdir()
    (inputs / "seqs" / f"{acc}.json").write_text(json.dumps(
        {"accession": acc, "name": "EXMP", "organism": "Testus fictus", "sequence": seq, "length": len(seq)}))
    (inputs / "esm" / "results.json").write_text(json.dumps({"human_sequence": seq}))
    return inputs


def test_science_input_compares_by_hash_and_records_the_identifier_by_ruling(script, tmp_path, monkeypatch):
    S = script("science_input")
    inputs = _published_inputs(tmp_path, INVENTED_ACC)
    seen = []
    monkeypatch.setattr(S, "fetch_fresh", lambda a: (seen.append(a), {"sequence": "MAAAC", "release": "2026_04",
                        "release_date": "x", "http_last_modified": "y", "entry_version": "2"})[1])
    out = tmp_path / "o.json"
    assert S.main(["--inputs", str(inputs), "--out", str(out)]) == 0
    d = json.loads(out.read_text())
    assert d["match"] is True
    assert d["identifier"] == INVENTED_ACC and seen == [INVENTED_ACC]
    assert d["published"]["sequence_sha256"] == d["fresh"]["sequence_sha256"]
    assert d["fresh"]["release"] == "2026_04" and d["published"]["length"] == 5
    assert "sequence" not in d["published"] and "sequence" not in d["fresh"], "digests only, never the sequence"


def test_science_input_reports_a_mismatch(script, tmp_path, monkeypatch, capsys):
    S = script("science_input")
    inputs = _published_inputs(tmp_path, INVENTED_ACC)
    monkeypatch.setattr(S, "fetch_fresh", lambda a: {"sequence": "MAAAD", "release": "", "release_date": "",
                                                     "http_last_modified": "", "entry_version": ""})
    out = tmp_path / "o.json"
    assert S.main(["--inputs", str(inputs), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["match"] is False
    assert "MISMATCH" in capsys.readouterr().out


def test_science_input_refuses_a_cached_identifier_that_is_not_an_accession(script, tmp_path, monkeypatch):
    """Cache content is file content: a value that could steer the URL is refused before
    any request is built (the branch's own valid_accession, F34)."""
    S = script("science_input")
    inputs = _published_inputs(tmp_path, "not-an-accession-or-path")
    monkeypatch.setattr(S, "fetch_fresh", lambda a: pytest.fail("network reached; validation should have refused"))
    with pytest.raises(ValueError):
        S.main(["--inputs", str(inputs), "--out", str(tmp_path / "o.json")])


# --- A4: the discovery run counted from its artifact -----------------------------------

def test_agent_run_counts_and_copies_no_content(script, tmp_path):
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    # An INVENTED three-entry artifact; the identifier field is a non-identifier placeholder.
    (d / "discovery.json").write_text(json.dumps({
        "objective": "invented objective", "model": "invented/model",
        "rounds": [{"round": 1, "reasoning": "secret reasoning", "requested": ["a", "b"], "results": ["r", "r"],
                    "completion_tokens": 10},
                   {"round": 2, "reasoning": "more", "requested": ["c"], "results": ["r"]}],
        "conclusion": "secret conclusion",
        "audit_trail": ["score_variant({'accession': 'X', 'position': 31, 'mutant': 'A'}) -> ok",
                        "score_variant({'accession': 'X', 'position': 43, 'mutant': 'A'}) -> ok",
                        "score_variant({'accession': 'X', 'position': 31, 'mutant': 'G'}) -> ok"]}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(tmp_path / "absent.json")]) == 0
    text = out.read_text()
    j = json.loads(text)
    assert j["measurements"] == 3 and j["rounds"] == 2
    assert j["completion_tokens_per_round"] == [10, None] and j["completion_tokens_total"] == 10
    assert j["rounds_without_a_token_count"] == 1
    assert j["positions_measured"] == [31, 43] and j["distinct_positions"] == 2
    assert j["control_positions"].startswith("pending")
    for secret in ("secret reasoning", "secret conclusion", "audit_trail", "invented objective"):
        assert secret not in text


def test_agent_run_errors_when_the_artifact_is_absent_naming_the_path(script, tmp_path, capsys):
    A = script("agent_run")
    with pytest.raises(SystemExit) as e:
        A.main(["--inputs", str(tmp_path / "nowhere"), "--out", str(tmp_path / "o.json")])
    assert e.value.code == 2
    assert "nowhere" in capsys.readouterr().err


# --- A3c: the headline numbers, computed the same way on both sides ------------------

def _synthetic_results():
    """Invented: a 6-residue 'protein' with cysteines at 2 and 5, a C-peptide region 3-5,
    and 19 substitutions per position with hand-set scores."""
    seq = "ACDCCE"
    subs = []
    for pos, wt in enumerate(seq, start=1):
        for mut in "ACDEFGHIKLMNPQRSTVWY".replace(wt, ""):
            subs.append({"pos": pos, "wt": wt, "mut": mut, "score": -10.0 if wt == "C" else -2.0})
    # alanine at position 3 gets a distinctive score for the control lookup
    for s in subs:
        if s["pos"] == 3 and s["mut"] == "A":
            s["score"] = 1.234
    return {"substitutions": subs, "cysteine_positions": [2, 4, 5],
            "regions": [{"name": "signal", "start": 1, "end": 2}, {"name": "C peptide", "start": 3, "end": 5}],
            "per_position": [{"pos": p, "mean_score": -1.0 * p} for p in range(1, 7)]}


def test_headline_derives_controls_from_the_region_and_the_agent_positions(script):
    S = script("science_rerun")
    h = S.headline(_synthetic_results(), agent_positions=[1, 3, 5, 9])
    assert h["substitutions"] == 6 * 19
    assert h["cysteine_mean"] == -10.0
    # 57 non-cysteine scores, one of them 1.234 instead of -2.0: (-2.0 * 56 + 1.234) / 57
    assert h["other_mean"] == round((-2.0 * 56 + 1.234) / 57, 2) == -1.94
    assert h["c_peptide_region"] == [3, 5]
    assert h["c_peptide_controls"] == {"3": 1.23, "5": -10.0}      # 1 is outside the region; 9 is not a position
    # mature = after the signal region (1-2): positions 3-6; cysteines there 4,5; others 3,6
    assert h["mature_from_position"] == 3
    assert h["cysteine_mean_mature"] == -10.0
    assert h["other_mean_mature"] == round((-2.0 * 37 + 1.234) / 38, 2)
    assert h["n_substitutions_mature"] == 4 * 19
    assert h["per_position_mean"] == [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0]


def test_compare_flags_any_headline_difference(script):
    S = script("science_rerun")
    a = S.headline(_synthetic_results(), [3])
    b = dict(a); b["cysteine_mean"] = -9.99
    m = S.compare(a, b)
    assert m["cysteine_mean"] is False and m["substitutions"] is True


def test_science_rerun_refuses_a_non_isolated_hf_home(script, tmp_path, monkeypatch):
    S = script("science_rerun")
    monkeypatch.delenv("HF_HOME", raising=False)
    assert S.main(["--inputs", str(tmp_path), "--out", str(tmp_path / "o.json")]) == 2


# --- A6: the plugin suites, re-run ----------------------------------------------------

def test_plugin_summary_regex_matches_the_libs_own_line(script):
    """tests/lib.sh's tests_summary prints exactly: '---' then '<n> run, <m> failed'."""
    T = script("plugin_tests")
    assert T.parse_summary("ok 1\nok 2\n---\n41 run, 0 failed\n") == (41, 0)
    assert T.parse_summary("---\n3 run, 1 failed\nafter") == (3, 1)
    assert T.parse_summary("no summary here") is None
    assert T.parse_summary("2 run, 0 failed\n---\n5 run, 2 failed\n") == (5, 2), "the last one wins"


def test_plugin_tests_runs_each_suite_in_a_scratch_worktree_and_removes_it(script, tmp_path):
    T = script("plugin_tests")
    repo = tmp_path / "plugin"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "good.test.sh").write_text("echo ok\necho ---\necho '2 run, 0 failed'\nexit 0\n")
    (repo / "tests" / "bad.test.sh").write_text("echo ---\necho '2 run, 1 failed'\nexit 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x"], check=True)
    subprocess.run(["git", "-C", str(repo), "tag", "v9.9.9"], check=True)
    out = tmp_path / "o.json"
    rc = T.main(["--plugin-repo", str(repo), "--tag", "v9.9.9", "--suites", "good.test.sh", "bad.test.sh",
                 "--out", str(out)])
    d = json.loads(out.read_text())
    assert rc == 1 and d["label"].startswith("NOT GREEN")
    assert d["suites"]["good.test.sh"] == {"run": 2, "failed": 0, "exit": 0, "summary_found": True, "passed": 2}
    assert d["suites"]["bad.test.sh"]["failed"] == 1 and d["suites"]["bad.test.sh"]["exit"] == 1
    wts = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout
    assert "v9.9.9" not in wts, "the scratch worktree must be removed afterwards"
