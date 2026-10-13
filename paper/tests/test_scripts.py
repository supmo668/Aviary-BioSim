"""Standing rules 2 and 3 of the white-paper plan, asserted.

Rule 2: every run saves its exact config next to its output — one implementation,
paper/scripts/_provenance.py, that every script calls.
Rule 3: a missing or empty --inputs directory is an ERROR (exit 2) that NAMES the path
checked. Never a finding of "unrecoverable" against a tree that never had the files.
"""
import json
import pathlib
import re
import subprocess

import pytest


def test_provenance_block_names_every_required_field(prov):
    prov.dirty_paths = lambda: []
    prov.require_clean_tree()
    blk = prov.block(inputs_path="/nowhere", extra={"seed": 0})
    for k in ("git_sha", "recorded_at", "inputs_path", "python", "seed"):
        assert k in blk, k
    assert len(blk["git_sha"]) == 40
    assert blk["recorded_at"].endswith("Z")
    assert blk["inputs_path"] == "/nowhere"


def test_provenance_block_records_versions_and_says_when_a_module_is_absent(prov):
    prov.dirty_paths = lambda: []
    prov.require_clean_tree()
    blk = prov.block(inputs_path=None, modules=("json", "module_that_does_not_exist_xq"))
    assert blk["inputs_path"] is None
    assert "json" in blk["versions"]
    assert blk["versions"]["module_that_does_not_exist_xq"].startswith("not importable")


def test_provenance_block_publishes_no_home_or_checkout_path(prov):
    """QG F06: the repository is public and its evidence recorded the machine's username
    and directory layout through inputs_path, cwd and every extra. A path inside the
    repository becomes <repo>/…, one under the home directory ~/…; nothing else changes."""
    from pathlib import Path
    home, repo, parent = str(Path.home().resolve()), str(prov.REPO), str(prov.PARENT)
    prov.dirty_paths = lambda: []
    prov.require_clean_tree()
    blk = prov.block(inputs_path=f"{repo}/science/out",
                     extra={"cwd": repo, "hf_home": f"{home}/.cache/hf", "argv": [f"{home}/bin/tool", "run"],
                            "tail": f"UNVERIFIED {home}/x/y.yaml not readable", "seed": 7, "digest": "ab" * 32,
                            "sibling": f"{parent}/projects/same-repo/.v2r",
                            "plugin": f"{home}/.claude/plugins/cache/some-plugins/someplug/1.2.3/tools/referee",
                            "other": f"{home}/code/elsewhere/thing"})
    assert blk["inputs_path"] == "<repo>/science/out"
    assert blk["cwd"] == "<repo>"
    assert blk["seed"] == 7 and blk["digest"] == "ab" * 32
    # coordinator's rule (#576): the enclosing project is a role, a plugin is a name and a
    # version, and any other home-relative path keeps only its last component
    assert blk["sibling"] == "<parent-project>/projects/same-repo/.v2r"
    assert blk["plugin"] == "<plugin:someplug 1.2.3>/tools/referee"
    assert blk["argv"] == ["~/…/tool", "run"]
    assert blk["hf_home"] == "~/…/hf"
    assert blk["tail"] == "UNVERIFIED ~/…/y.yaml not readable"
    assert blk["other"] == "~/…/thing"
    dumped = json.dumps(blk, ensure_ascii=False)
    assert home not in dumped and parent not in dumped


PAPER_DIR = pathlib.Path(__file__).resolve().parents[1]
HOME_PATTERNS = ("/Users/", "/home/", "/root/", "C:\\Users\\")
EMAIL = re.compile(rb"[\w.+-]+@[\w-]+\.[\w.-]+")
PDF_DATE = re.compile(rb"/CreationDate\s*\((D:[^)]*)\)")


def _manifest_artifact_paths():
    """The paths publish.yml actually ships. Reading them from the manifest rather than
    hardcoding is the point: widen the deposit and the scan widens with it."""
    import yaml
    manifest = yaml.safe_load((PAPER_DIR / "publish.yml").read_text())
    return [PAPER_DIR / a["path"] for a in manifest["artifacts"]]


def _payload_files():
    out = []
    for p in _manifest_artifact_paths():
        out += [f for f in sorted(p.rglob("*")) if f.is_file()] if p.is_dir() else [p]
    return out


def test_the_deposit_payload_carries_no_home_path_or_email():
    """The DEPOSIT, not just evidence/. The old scan walked `evidence` for four suffixes while
    the manifest ships four paths and seven file types, so `claims.yaml`, `main.pdf` and all of
    `figures/` went unscanned — and that is exactly where the one real leak sat (a `.pyc` under
    figures/ carrying the username). Binary files are read as bytes, because a PDF's text is
    glyph-encoded inside compressed streams: a naive text grep reports clean on content that
    IS there. Author email is permitted in main.pdf only (the deliberate byline)."""
    home = str(pathlib.Path.home().resolve()).encode()
    offenders = []
    for f in _payload_files():
        b = f.read_bytes()
        rel = f.relative_to(PAPER_DIR)
        if home in b or any(pat.encode() in b for pat in HOME_PATTERNS):
            offenders.append(f"{rel}: home/absolute path")
        if f.name != "main.pdf" and EMAIL.search(b):
            offenders.append(f"{rel}: email address")
    assert offenders == [], offenders


def test_no_untracked_file_rides_along_in_the_deposit_payload():
    """The leak that got through was untracked AND gitignored, so `git ls-files`, review and
    every other test were blind to it while it sat inside a declared artifact directory."""
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], text=True, cwd=PAPER_DIR.parent).split("\0"))
    strays = [str(f.relative_to(PAPER_DIR.parent)) for f in _payload_files()
              if str(f.relative_to(PAPER_DIR.parent)) not in tracked]
    assert strays == [], strays


def test_every_pdf_in_the_payload_has_a_utc_creation_date():
    """Matplotlib stamped the figures with the local wall-clock time and the machine's UTC
    offset, publishing the author's timezone to the second. main.pdf was already normalised."""
    bad = []
    for f in _payload_files():
        if f.suffix != ".pdf":
            continue
        for m in PDF_DATE.finditer(f.read_bytes()):
            d = m.group(1).decode()
            if not (d.endswith("Z") or "-00'00'" in d or "+00'00'" in d):
                bad.append(f"{f.relative_to(PAPER_DIR)}: {d}")
    assert bad == [], bad


def test_the_input_identifier_appears_in_no_test_or_fixture():
    """F33: the input's identifier, release and digest live in the methods and evidence/ ONLY —
    'never in tests, fixtures or messages'. The ruling was breached at ~67 sites across six
    test files; this pins it. The real values are read from the evidence file rather than
    written here, so the test itself does not become the breach it forbids."""
    import json as _json
    repo = PAPER_DIR.parent
    inp = _json.loads((PAPER_DIR / "evidence" / "science-input.json").read_text())
    secrets = {inp["identifier"], inp["fresh"]["release"], inp["fresh"]["sequence_sha256"]}
    searched = [p for d in ("science/tests", "paper/tests", ".claude")
                for p in (repo / d).rglob("*.py") if "__pycache__" not in p.parts]
    assert searched, "found no test files to scan"
    offenders = [f"{p.relative_to(repo)}: {k[:3]}…"
                 for p in searched for k in secrets if k in p.read_text(errors="replace")]
    assert offenders == [], offenders


def test_a_dirty_tree_is_refused_so_the_recorded_sha_identifies_the_producing_code(prov, capsys):
    """A7-2. `git_sha` is a claim about WHICH CODE ran, and it only holds if the tree was
    clean when it ran: science.json recorded a sha whose tree did not yet contain the
    fields the file carries, because the script was still uncommitted. Refuse, and name
    what was dirty."""
    prov.dirty_paths = lambda: ["paper/scripts/science_rerun.py", "paper/evidence/x.json"]
    with pytest.raises(SystemExit) as e:
        prov.require_clean_tree()
    assert e.value.code == 2
    assert "paper/scripts/science_rerun.py" in capsys.readouterr().err


def _status(prov, monkeypatch, *entries):
    """Stub `git status --porcelain -z`, capturing the argv so the invocation is asserted
    rather than assumed: mocking check_output wholesale let the real call lose --porcelain
    and cwd=REPO with every test still green (QG F17)."""
    seen = {}

    def fake(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        return "\0".join(entries) + ("\0" if entries else "")

    monkeypatch.setattr(prov.subprocess, "check_output", fake)
    return seen


def test_dirty_paths_asks_git_for_machine_readable_status_in_the_repository(prov, monkeypatch):
    seen = _status(prov, monkeypatch, " M paper/scripts/a.py")
    prov.dirty_paths()
    assert seen["argv"] == ["git", "status", "--porcelain", "-z", "--no-renames"]
    assert seen["kw"]["cwd"] == prov.REPO


def test_the_evidence_a_rebuild_writes_does_not_count_as_a_dirty_tree(prov, monkeypatch):
    """`tree_clean` is a claim about the CODE that produced the file. A full rebuild writes
    its evidence in sequence, so the first producer's own output would otherwise make every
    later one refuse. Only files a producer WRITES are exempt; a changed script still counts."""
    _status(prov, monkeypatch, " M paper/evidence/science-input.json", "?? paper/evidence/agent-run.json")
    assert prov.dirty_paths() == []
    _status(prov, monkeypatch, " M paper/evidence/science.json", " M paper/scripts/agent_run.py")
    assert prov.dirty_paths() == ["paper/scripts/agent_run.py"]


def test_the_hand_authored_evidence_is_an_input_and_still_counts_as_dirty(prov, monkeypatch):
    """QG F2: taxonomy.csv and weave-count.json are written by no script — they are inputs
    that back published counts. A blanket directory exemption hid an uncommitted hand edit
    to either while every producer still recorded tree_clean true."""
    _status(prov, monkeypatch, " M paper/evidence/taxonomy.csv")
    assert prov.dirty_paths() == ["paper/evidence/taxonomy.csv"]
    _status(prov, monkeypatch, " M paper/evidence/weave-count.json")
    assert prov.dirty_paths() == ["paper/evidence/weave-count.json"]


def test_a_rename_out_of_the_evidence_directory_does_not_read_as_clean(prov, monkeypatch):
    """QG F4: git's rename form is `R  old -> new` in ONE entry. Slicing it and prefix-testing
    the whole string meant renaming a file OUT of the exempt directory excluded a staged file
    elsewhere, and the run recorded tree_clean TRUE over a tree that did not contain it —
    affirmatively false, not merely unproven. `--no-renames` reports the two sides separately."""
    _status(prov, monkeypatch, "D  paper/evidence/taxonomy.csv", "A  paper/scripts/renamed.py")
    assert prov.dirty_paths() == ["paper/evidence/taxonomy.csv", "paper/scripts/renamed.py"]
    with pytest.raises(SystemExit):
        prov.require_clean_tree()


def test_a_path_that_merely_starts_like_an_exempt_one_still_counts(prov, monkeypatch):
    _status(prov, monkeypatch, " M paper/evidence/science.json.bak", " M paper/evidence-notes.txt")
    assert prov.dirty_paths() == ["paper/evidence/science.json.bak", "paper/evidence-notes.txt"]


def test_the_published_dirty_list_withholds_untracked_filenames(prov, monkeypatch):
    """QG F11: a checkout carries untracked scratch, credential and client-named files, and
    this list ships in a public deposit. Untracked names become a count; tracked names, which
    are public already, are listed under the same cap the refusal message uses."""
    _status(prov, monkeypatch, " M paper/scripts/a.py", "?? .env.production", "?? notes-for-a-client.md")
    published = prov.publishable_dirty()
    assert "paper/scripts/a.py" in published
    assert "(2 untracked file(s), names withheld)" in published
    assert not any(".env" in p or "client" in p for p in published)
    # the refusal decision still sees them — an uncommitted new module is exactly the state
    # that makes a recorded commit fail to describe the code that ran
    assert len(prov.dirty_paths()) == 3


def test_the_published_dirty_list_is_capped_like_the_refusal_message(prov, monkeypatch):
    _status(prov, monkeypatch, *[f" M paper/scripts/f{i}.py" for i in range(12)])
    published = prov.publishable_dirty()
    assert len(published) == 11 and "(+2 more tracked)" in published


def test_the_refusal_names_every_dirty_path_up_to_the_cap_and_says_how_many_it_omitted(prov, capsys):
    """QG F17: the test asserted only the FIRST path, so a producer that named one of fifty
    dirty files passed. Cutting the slice to [:1] survived the whole suite."""
    prov.dirty_paths = lambda: [f"paper/scripts/f{i}.py" for i in range(3)]
    with pytest.raises(SystemExit):
        prov.require_clean_tree()
    err = capsys.readouterr().err
    assert all(f"paper/scripts/f{i}.py" in err for i in range(3))

    prov.dirty_paths = lambda: [f"paper/scripts/g{i}.py" for i in range(12)]
    with pytest.raises(SystemExit):
        prov.require_clean_tree()
    err = capsys.readouterr().err
    assert "paper/scripts/g9.py" in err and "paper/scripts/g10.py" not in err
    assert "(+2 more)" in err


def test_block_refuses_to_claim_a_tree_state_the_guard_never_checked(prov):
    """QG F3: the old default recomputed at write time, by which point the script had written
    its own exempt evidence, so it almost always evaluated TRUE — a producer that forgot the
    guard still published tree_clean true, asserting a guarantee that was never checked."""
    prov.dirty_paths = lambda: ["paper/scripts/x.py"]
    with pytest.raises(RuntimeError, match="without require_clean_tree"):
        prov.block(inputs_path=None)


def test_a_clean_tree_passes_and_the_block_says_so(prov):
    prov.dirty_paths = lambda: []
    assert prov.require_clean_tree() is True
    assert prov.block(inputs_path=None)["tree_clean"] is True


def test_an_explicitly_allowed_dirty_tree_is_recorded_as_dirty_not_hidden(prov, monkeypatch, capsys):
    """The escape hatch may not quietly produce evidence that LOOKS clean: the block has to
    carry tree_clean false and the paths, AND say so on stderr — deleting the warning
    survived the whole suite, because the test took no capsys (QG F17)."""
    _status(prov, monkeypatch, " M paper/scripts/science_rerun.py")
    assert prov.require_clean_tree(allow_dirty=True) is False
    err = capsys.readouterr().err
    assert "WARNING" in err and "NOT pinned" in err and "paper/scripts/science_rerun.py" in err
    blk = prov.block(inputs_path=None)
    assert blk["tree_clean"] is False
    assert blk["dirty_paths"] == ["paper/scripts/science_rerun.py"]


def test_the_recorded_dirty_list_is_the_one_from_before_the_run_not_a_re_sample(prov, monkeypatch):
    """QG F17: only the boolean was checked, so re-sampling the LIST at write time survived —
    which would publish the evidence the run had just written as the dirty paths."""
    _status(prov, monkeypatch, " M paper/scripts/a.py")
    prov.require_clean_tree(allow_dirty=True)
    _status(prov, monkeypatch, " M paper/scripts/b.py")
    assert prov.block(inputs_path=None)["dirty_paths"] == ["paper/scripts/a.py"]


def test_the_block_reports_the_tree_state_from_before_the_run_wrote_anything(prov):
    """Scripts write into the repository as they run (evidence files, record copies), so a
    state sampled at block() time would read dirty for an honest clean run. The state
    recorded is the one require_clean_tree() observed at the start."""
    prov.dirty_paths = lambda: []
    prov.require_clean_tree()
    prov.dirty_paths = lambda: ["paper/evidence/just-written.json"]
    assert prov.block(inputs_path=None)["tree_clean"] is True


# Each producer with the arguments argparse demands, so parse_args SUCCEEDS and the run
# reaches the tree check. Supplying none made the test pass for the wrong reason: argparse
# exited 2 on a missing required argument and its usage line, which now advertises
# `[--allow-dirty-tree]`, contained the word the assertion looked for.
PRODUCERS = [
    ("record_referee", ["--referee", "/nonexistent/referee"]),
    ("drain1_from_git", []),
    ("drain1_record_check", ["--record", "/nonexistent/r.v2r", "--register", "/nonexistent/register"]),
    ("science_input", ["--inputs", "/nonexistent/in"]),
    ("science_rerun", ["--inputs", "/nonexistent/in"]),
    ("agent_run", ["--inputs", "/nonexistent/in"]),
    ("plugin_tests", ["--plugin-repo", "/nonexistent/repo"]),
    ("repo_tests", []),
]


@pytest.mark.parametrize("name,argv", PRODUCERS, ids=[p[0] for p in PRODUCERS])
def test_every_producer_refuses_to_write_evidence_from_a_dirty_tree(name, argv, monkeypatch,
                                                                    capsys, tmp_path):
    """A7-2, wired up: the refusal belongs to every script that writes an evidence file,
    not only to _provenance. Loaded WITHOUT the conftest clean-tree patch on purpose —
    this is the one test that must see the real guard. Every path passed is absent, so
    the only thing that can produce this exact refusal is the tree check."""
    from conftest import load_script
    mod = load_script(name)
    monkeypatch.setattr(mod.P, "dirty_paths", lambda: ["paper/scripts/sentinel_dirty.py"])
    out = tmp_path / "out.json"
    argv = argv + ["--out", str(out)]
    if name == "drain1_record_check":
        argv += ["--copy-to", str(tmp_path / "copies")]
    with pytest.raises(SystemExit) as e:
        mod.main(argv)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "the working tree is dirty" in err
    assert "paper/scripts/sentinel_dirty.py" in err
    # the refusal must precede the WRITE, which is what this test is named for. The output
    # used to be left at the default — the LIVE paper/evidence/ — so moving the guard to
    # after the writes still passed, and the run modified real evidence (QG F10).
    assert not out.exists(), f"{name} wrote its evidence before refusing"


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


def _clone_with_suite(tmp_path, body: str) -> tuple[_Path, str]:
    """A throwaway local clone of this repository with one extra commit holding t/test_x.py,
    so the referee command can be run end to end against a suite whose outcome the test
    chose. Nothing touches the real repository's refs (QG F10)."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--local", "--no-hardlinks", str(REPO), str(clone)], check=True)
    (clone / "t").mkdir()
    (clone / "t" / "test_x.py").write_text(body)
    git = ["git", "-C", str(clone), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["add", "t"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "suite under test"], check=True)
    sha = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return clone, sha


def _run_referee_sh_in(clone: _Path, sha: str):
    env = dict(os.environ, DRAIN1_END_COMMIT=sha, SUITE_PATH="t/test_x.py")
    return subprocess.run(["/bin/sh", str(REFEREE_SH)], cwd=clone, env=env,
                          capture_output=True, text=True, timeout=600)


def test_referee_command_reports_a_passing_suite_with_plan_and_results_and_exit_0(tmp_path):
    clone, sha = _clone_with_suite(tmp_path, "def test_a():\n    assert True\n\ndef test_b():\n    assert 1 == 1\n")
    r = _run_referee_sh_in(clone, sha)
    assert r.returncode == 0, (r.returncode, r.stderr)
    lines = r.stdout.splitlines()
    assert lines[0] == "PLAN 2"
    assert sorted(lines[1:3]) == ["RESULT pass test_x/test_a", "RESULT pass test_x/test_b"]
    assert lines[3] == f"# archived commit {sha}"
    assert "COULD-NOT-RUN" not in r.stderr


def test_referee_command_exits_1_when_the_suite_ran_and_a_test_failed(tmp_path):
    """QG F10: `[ "$PYRC" -eq 1 ] && exit 1` was never exercised; replaced by `:`, a failing
    suite exited 0 to the recorder, which reads the exit code directly."""
    clone, sha = _clone_with_suite(tmp_path, "def test_a():\n    assert True\n\ndef test_b():\n    assert False\n")
    r = _run_referee_sh_in(clone, sha)
    assert r.returncode == 1, (r.returncode, r.stderr)
    lines = r.stdout.splitlines()
    assert lines[0] == "PLAN 2"
    assert "RESULT fail test_x/test_b" in lines and "RESULT pass test_x/test_a" in lines
    assert "False" not in r.stdout, "no assertion text may reach the output"


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
    ('{"total":6,"passed":6,"failed":0,"skipped":0}', 1),         # clean JSON, nonzero exit (QG Q24)
    ('{"total":0,"passed":0,"failed":0,"skipped":0}', 0),         # zero tests ran (QG Q24)
    # QG F09: each verdict field alone, with the referee exiting 0 — every failing case
    # above also exits non-zero, so the field checks could be deleted unnoticed.
    ('{"total":6,"passed":5,"failed":1,"skipped":0}', 0),
    ('{"total":6,"passed":5,"failed":0,"skipped":1}', 0),
    ('{"total":6,"passed":5,"failed":0,"skipped":0,"unaccounted":1}', 0),
    ('{"total":6,"passed":6,"failed":0,"skipped":0,"plan_error":"PLAN 7 but 6 results"}', 0),
    ('{"total":null,"passed":null,"failed":null,"skipped":null}', 0),
], ids=["no-results", "failed", "skipped", "unreadable", "clean-json-nonzero-exit", "zero-tests",
        "failed-exit0", "skipped-exit0", "unaccounted-exit0", "plan-error-exit0", "null-total"])
def test_recorder_records_not_measured_and_exits_2_otherwise(script, tmp_path, stdout, code):
    R = script("record_referee")
    out = tmp_path / "drain1-rerun.json"
    assert R.main(["--referee", _stub_referee(tmp_path, stdout, code), "--out", str(out)]) == 2
    d = json.loads(out.read_text())
    assert d["label"].startswith("NOT MEASURED")
    assert d["referee_exit"] == code


def test_recorder_errors_on_a_missing_referee_naming_the_path(script, tmp_path, capsys):
    """QG F13: a mistyped --referee raised FileNotFoundError out of subprocess.run — a
    traceback, nothing written — instead of exit 2 naming the path."""
    R = script("record_referee")
    out = tmp_path / "drain1-rerun.json"
    missing = tmp_path / "no-such-referee"
    assert R.main(["--referee", str(missing), "--out", str(out)]) == 2
    assert str(missing) in capsys.readouterr().err
    assert not out.exists()


def test_recorder_runs_the_suite_over_the_commit_it_records(script, tmp_path, monkeypatch):
    """QG Q19: --commit was written into the evidence as archived_commit, but the referee
    command ran DRAIN1_END_COMMIT (default 2e00aa3), so a non-default --commit produced
    evidence naming one tree while the tests ran over another."""
    R = script("record_referee")
    monkeypatch.delenv("DRAIN1_END_COMMIT", raising=False)
    seen = tmp_path / "seen-commit"
    stub = tmp_path / "referee"
    stub.write_text("#!/bin/sh\n"
                    f"printf '%s' \"${{DRAIN1_END_COMMIT:-unset}}\" > '{seen}'\n"
                    "printf '%s\\n' '{\"total\":6,\"passed\":6,\"failed\":0,\"skipped\":0}'\n")
    stub.chmod(0o755)
    out = tmp_path / "drain1-rerun.json"
    assert R.main(["--referee", str(stub), "--out", str(out), "--commit", "abc1234"]) == 0
    assert seen.read_text() == "abc1234"
    d = json.loads(out.read_text())
    assert d["archived_commit"] == "abc1234"
    assert d["provenance"]["archived_commit_env"] == "abc1234"


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


def test_record_check_errors_on_a_missing_record_dir_naming_the_path(script, tmp_path, capsys):
    C = script("drain1_record_check")
    missing = tmp_path / "absent"
    with pytest.raises(SystemExit) as e:
        C.main(["--record", str(missing), "--register", _stub_register(tmp_path, 0),
                "--out", str(tmp_path / "o.json"), "--copy-to", str(tmp_path / "c")])
    assert e.value.code == 2
    assert str(missing) in capsys.readouterr().err


def test_record_check_requires_the_register_tool_and_names_it_when_absent(script, tmp_path, capsys):
    """QG F07: --register defaulted to one machine's absolute plugin-cache path; anywhere
    else the file did not exist, verify-record was silently skipped (ran: false) and the
    script still exited 0 — a skipped verification indistinguishable from a performed one."""
    C = script("drain1_record_check")
    rec = _synthetic_record(tmp_path, script)
    assert "DEFAULT_REGISTER" not in dir(C), "no machine-specific default may remain"
    with pytest.raises(SystemExit):                      # argparse: --register is required
        C.main(["--record", str(rec), "--out", str(tmp_path / "o.json"), "--copy-to", str(tmp_path / "c")])
    missing = tmp_path / "no-such-register"
    rc = C.main(["--record", str(rec), "--register", str(missing),
                 "--out", str(tmp_path / "o.json"), "--copy-to", str(tmp_path / "c")])
    assert rc == 2
    assert str(missing) in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


def test_record_check_source_carries_no_home_directory_path():
    src = (REPO / "paper" / "scripts" / "drain1_record_check.py").read_text()
    assert "/Users/" not in src and "/home/" not in src


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
                        "release_date": "x", "http_last_modified": "y", "sequence_version": "2"})[1])
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
                                                     "http_last_modified": "", "sequence_version": ""})
    out = tmp_path / "o.json"
    # QG Q6: a mismatch is labelled so in the file (claims.py then refuses to build on it)
    # and exits non-zero, like every other runner — not "measured" with exit 0.
    assert S.main(["--inputs", str(inputs), "--out", str(out)]) == 1
    d = json.loads(out.read_text())
    assert d["match"] is False
    assert d["label"].startswith("MISMATCH")
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


def _invented_artifact_with_controls():
    """An INVENTED artifact shaped like the real one: a first round that requests the
    constrained positions and two region positions TOGETHER, and a final write-up whose
    own heading names control positions, two of which lie outside the region."""
    return {
        "objective": "invented objective", "model": "invented/model",
        "rounds": [
            {"round": 1, "reasoning": "r1",
             "requested": ['score_variant({"accession":"X","position":31,"mutant":"A"})',
                           'score_variant({"accession":"X","position":43,"mutant":"A"})',
                           'score_variant({"accession":"X","position":70,"mutant":"A"})',
                           'score_variant({"accession":"X","position":83,"mutant":"A"})'],
             "results": ["r"] * 4, "completion_tokens": 10},
            {"round": 2, "reasoning": "r2",
             "requested": ['score_variant({"accession":"X","position":62,"mutant":"A"})'],
             "results": ["r"], "completion_tokens": 5},
            {"round": 3, "reasoning": (
                # a prose line mentioning controls, followed by bullets, must NOT be read as
                # a heading; and an earlier scratch list must not beat the final write-up
                "We used tolerant positions as a control.\n- Z99Z **+9.9**\n"
                "## Preliminary controls\n- A11A **+0.5**\n"
                "### Least tolerant\n- C31A **-13.9**\n- C43A **-16.1**\n"
                "### Control positions that tolerate substitution\n"
                "- F25A **+3.1**\n- Q62A **+1.5**\n- D20A **+1.4**\n- P79A **+1.1**\n"
                "#### Caveat\n- K65A **+0.4**\n"      # a sub-heading must not truncate the list
                "- P72A **+0.2**\n- G70A **+0.2**\n- E83A **-0.1**\n"
                "- see also Figure S2B and Table T4C\n"   # cross-refs are not substitutions
                "```python\n# control group for the assay\n- W88W is not a variant\n```\n"
                "## What this implies\nprose that must not be copied\n- C31A **-13.9**\n"),
             "measurements": []},
        ],
        "conclusion": "secret conclusion",
        # the agent measured everything it named; a position it never measured cannot be one
        # of its controls, which is what filters the cross-reference tokens back out
        "audit_trail": [f"score_variant({{'accession': 'X', 'position': {p}, 'mutant': 'A'}}) -> ok"
                        for p in (20, 25, 31, 43, 62, 65, 70, 72, 79, 83)],
    }


def test_agent_run_records_the_controls_the_agent_itself_named(script, tmp_path):
    """A7-1. The paper said the agent probed a region as a control. The agent never named
    the region; it named seven positions under its own 'Control positions' heading, two of
    them outside the region. The evidence has to carry the agent's own list so the text can
    report it instead of interpreting it — positions only, never the prose."""
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    (d / "discovery.json").write_text(json.dumps(_invented_artifact_with_controls()))
    science = tmp_path / "science.json"
    science.write_text(json.dumps({"headline": {"c_peptide_region": [57, 87],
                                                "c_peptide_controls": {"62": 1.5, "70": 0.2,
                                                                       "72": 0.2, "79": 1.1, "83": -0.1},
                                                "cysteine_positions": [31, 43]}}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(science)]) == 0
    text = out.read_text()
    c = json.loads(text)["control_positions"]
    # 65 is INSIDE the region but is NOT one of the science-derived controls, so classifying
    # against the region and classifying against `c_peptide_controls` give different answers
    # and the test can tell them apart. They were numerically identical before, and swapping
    # one for the other survived the whole suite — the A7-1 point was unverified (QG F17).
    assert c["named_by_the_agent"] == [20, 25, 62, 65, 70, 72, 79, 83]
    assert c["named_by_the_agent_count"] == 8
    assert c["named_by_the_agent_in_c_peptide"] == [62, 65, 70, 72, 79, 83]
    assert c["named_by_the_agent_in_c_peptide_count"] == 6
    assert c["named_by_the_agent_outside_c_peptide"] == [20, 25]
    assert c["named_by_the_agent_in_c_peptide"] != c["c_peptide_positions_from_science_json"]
    # the extraction is auditable: which round, which heading, what was thrown away
    ex = c["named_by_the_agent_extraction"]
    assert ex["round"] == 3 and "Control positions" in ex["heading"]
    assert set(ex["discarded_not_measured"]) >= {2, 4}   # Figure S2B / Table T4C
    assert "prose that must not be copied" not in text and "secret conclusion" not in text


def test_the_control_parser_ignores_code_fences_prose_and_earlier_scratch_lists(script):
    """QG F7, three reproduced defects in one: a `#` comment inside a fenced code block was
    read as a heading, any line containing 'control' was read as a heading, and the FIRST
    matching heading won although the paper reports the agent's FINAL write-up."""
    A = script("agent_run")
    measured = [20, 25, 31, 43, 62, 65, 70, 72, 79, 83]
    named, prov = A.controls_named_by_the_agent(_invented_artifact_with_controls(), measured)
    assert 99 not in named          # the prose mention's bullet
    assert 11 not in named          # the earlier "Preliminary controls" list
    assert 88 not in named          # the comment inside the code fence
    assert 65 in named              # a sub-heading did not truncate the list
    assert prov["round"] == 3


def test_the_control_parser_reports_no_list_rather_than_an_empty_one(script):
    """QG F17: `return None` -> `return []` survived. An empty list is a positive assertion
    that the agent named NO controls; absent means no control section was found at all."""
    A = script("agent_run")
    named, prov = A.controls_named_by_the_agent(
        {"rounds": [{"reasoning": "no headings here at all"}]}, [1, 2, 3])
    assert named is None and prov is None


def test_agent_run_records_that_the_constrained_positions_were_requested_in_round_one(script, tmp_path):
    """A7-1. 'Having found the cysteines, it probed the C-peptide' describes a sequence the
    artifact does not contain: the first round asks for both at once. Record the round each
    was first requested in, so the text cannot assert an order the evidence contradicts."""
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    (d / "discovery.json").write_text(json.dumps(_invented_artifact_with_controls()))
    science = tmp_path / "science.json"
    science.write_text(json.dumps({"headline": {"c_peptide_region": [57, 87],
                                                "c_peptide_controls": {"62": 1.5},
                                                "cysteine_positions": [31, 43]}}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(science)]) == 0
    j = json.loads(out.read_text())
    assert j["requested_positions_per_round"][0] == [31, 43, 70, 83]
    assert j["cysteines_first_requested_in_round"] == 1
    # the region was probed in the SAME round, not after a finding
    assert j["c_peptide_first_requested_in_round"] == 1
    # and ALL the cysteines were in that round — the paper says "the six ... together", which
    # an any-of fact cannot support (QG F6)
    assert j["all_cysteines_requested_in_round"] == 1


def test_an_any_of_round_is_not_recorded_as_an_all_of_round(script, tmp_path):
    """QG F6. `first_round_requesting` is an ANY-of fact, and `return 1` unconditionally
    survived the whole suite because every asserted value was 1. The paper's load-bearing
    sentence needs the all-of fact, so both are recorded and they must be able to differ."""
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    art = {
        "objective": "o", "model": "m",
        "rounds": [
            # round 1 asks for ONE of the two; round 2 asks for BOTH together, so the any-of
            # answer is 1 and the all-in-one-round answer is 2
            {"round": 1, "requested": ['{"position": 31}'], "reasoning": "", "completion_tokens": 1},
            {"round": 2, "requested": ['{"position": 31}', '{"position": 43}'],
             "reasoning": "", "completion_tokens": 1},
        ],
        "conclusion": "c",
        "audit_trail": ["score_variant({'position': 31}) -> ok"],
    }
    (d / "discovery.json").write_text(json.dumps(art))
    science = tmp_path / "science.json"
    science.write_text(json.dumps({"headline": {"c_peptide_region": [57, 87],
                                                "c_peptide_controls": {},
                                                "cysteine_positions": [31, 43]}}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(science)]) == 0
    j = json.loads(out.read_text())
    assert j["cysteines_first_requested_in_round"] == 1      # one of them arrived in round 1
    assert j["all_cysteines_requested_in_round"] == 2        # but not all until round 2
    assert j["c_peptide_first_requested_in_round"] is None   # never requested


def test_agent_run_says_pending_rather_than_null_when_the_science_input_is_absent(script, tmp_path):
    """QG F19: a bare null conflated 'the agent never requested these' with 'the input was
    missing and nothing was computed'. The round fields use the same sentinel as the rest."""
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    (d / "discovery.json").write_text(json.dumps(_invented_artifact_with_controls()))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out),
                   "--science", str(tmp_path / "absent.json")]) == 0
    j = json.loads(out.read_text())
    for k in ("cysteines_first_requested_in_round", "all_cysteines_requested_in_round",
              "c_peptide_first_requested_in_round"):
        assert isinstance(j[k], str) and j[k].startswith("pending"), k
    assert j["science_json_sha256"] is None


def test_agent_run_pins_the_science_json_it_read(script, tmp_path):
    """QG F2: science.json is exempt from the tree check, so tree_clean says nothing about
    it — yet three published fields are classified against its region annotation. The digest
    is what pins that input, exactly as artifact_sha256 already pins the external artifact."""
    import hashlib
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    (d / "discovery.json").write_text(json.dumps(_invented_artifact_with_controls()))
    science = tmp_path / "science.json"
    science.write_text(json.dumps({"headline": {"c_peptide_region": [57, 87],
                                                "c_peptide_controls": {"62": 1.5},
                                                "cysteine_positions": [31, 43]}}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(science)]) == 0
    assert json.loads(out.read_text())["science_json_sha256"] == \
        hashlib.sha256(science.read_bytes()).hexdigest()


def test_agent_run_errors_on_a_malformed_c_peptide_region_naming_the_field(script, tmp_path, capsys):
    """QG F18: a partially written sibling gave a bare TypeError/ValueError traceback instead
    of this project's convention — ERROR plus exit 2, naming what was wrong."""
    A = script("agent_run")
    d = tmp_path / "discovery"
    d.mkdir()
    (d / "discovery.json").write_text(json.dumps(_invented_artifact_with_controls()))
    science = tmp_path / "science.json"
    science.write_text(json.dumps({"headline": {"c_peptide_region": [57, None],
                                                "c_peptide_controls": {},
                                                "cysteine_positions": [31]}}))
    out = tmp_path / "agent-run.json"
    assert A.main(["--inputs", str(d), "--out", str(out), "--science", str(science)]) == 2
    assert "c_peptide_region" in capsys.readouterr().err
    assert not out.exists()


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


HEADLINE_KEYS = ["substitutions", "cysteine_mean", "other_mean", "cysteine_positions", "c_peptide_region",
                 "c_peptide_controls", "mature_from_position", "cysteine_mean_mature", "other_mean_mature",
                 "n_substitutions_mature"]


@pytest.mark.parametrize("key", HEADLINE_KEYS)
def test_compare_covers_every_headline_key(script, key):
    """QG F04: compare() carries a hand-typed key tuple; dropping any key but cysteine_mean
    silently stopped comparing it while science.json still said every field matched."""
    S = script("science_rerun")
    a = S.headline(_synthetic_results(), [3, 5])
    b = json.loads(json.dumps(a))
    v = b[key]
    b[key] = (v + 1 if isinstance(v, (int, float)) else
              {"3": 0.0} if isinstance(v, dict) else [99] if isinstance(v, list) else "x")
    m = S.compare(a, b)
    assert m[key] is False, key
    assert all(m[k] for k in HEADLINE_KEYS if k != key)


def test_compare_compares_every_headline_key_the_scan_produces(script):
    """Every headline key except the per-position list is a compared key — a key added to
    headline() without a compare() entry would be published unchecked."""
    S = script("science_rerun")
    a = S.headline(_synthetic_results(), [3])
    assert set(S.compare(a, a)) == set(a) - {"per_position_mean"}


def test_science_rerun_refuses_a_non_isolated_hf_home(script, tmp_path, monkeypatch):
    S = script("science_rerun")
    monkeypatch.delenv("HF_HOME", raising=False)
    assert S.main(["--inputs", str(tmp_path), "--out", str(tmp_path / "o.json")]) == 2


def test_science_rerun_errors_on_a_missing_agent_run_naming_the_path(script, tmp_path, monkeypatch, capsys):
    """QG F08: the agent-run file was read with no check, so a clean rebuild raised a
    FileNotFoundError traceback instead of the exit-2 named error every input gets."""
    S = script("science_rerun")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "paper/.hf-cache"))
    inputs = tmp_path / "out" / "esm"
    inputs.mkdir(parents=True)
    (inputs / "results.json").write_text(json.dumps(_synthetic_results()))
    missing = tmp_path / "no-agent-run.json"
    assert S.main(["--inputs", str(tmp_path / "out"), "--agent-run", str(missing), "--out", str(tmp_path / "o.json")]) == 2
    assert str(missing) in capsys.readouterr().err


# --- A6: the plugin suites, re-run ----------------------------------------------------

def test_plugin_summary_regex_matches_the_libs_own_line(script):
    """tests/lib.sh's tests_summary prints exactly: '---' then '<n> run, <m> failed'."""
    T = script("plugin_tests")
    assert T.parse_summary("ok 1\nok 2\n---\n41 run, 0 failed\n") == (41, 0)
    assert T.parse_summary("---\n3 run, 1 failed\nafter") == (3, 1)
    assert T.parse_summary("no summary here") is None
    assert T.parse_summary("2 run, 0 failed\n---\n5 run, 2 failed\n") == (5, 2), "the last one wins"


def _plugin_repo(tmp_path, suites: dict, annotated_tag: bool = False):
    """A throwaway git repository with tests/<name> files and a tag v9.9.9 at its one commit."""
    import subprocess
    repo = tmp_path / "plugin"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for name, body in suites.items():
        (repo / "tests" / name).write_text(body)
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "x"], check=True)
    subprocess.run(git + ["tag"] + (["-a", "-m", "release"] if annotated_tag else []) + ["v9.9.9"], check=True)
    return repo


def test_plugin_tests_runs_each_suite_in_a_scratch_worktree_and_removes_it(script, tmp_path):
    T = script("plugin_tests")
    import subprocess
    repo = _plugin_repo(tmp_path, {
        "good.test.sh": "echo ok\necho ---\necho '2 run, 0 failed'\nexit 0\n",
        "bad.test.sh": "echo ---\necho '2 run, 1 failed'\nexit 1\n"})
    out = tmp_path / "o.json"
    rc = T.main(["--plugin-repo", str(repo), "--tag", "v9.9.9", "--suites", "good.test.sh", "bad.test.sh",
                 "--out", str(out)])
    d = json.loads(out.read_text())
    assert rc == 1 and d["label"].startswith("NOT GREEN")
    assert d["suites"]["good.test.sh"] == {"run": 2, "failed": 0, "exit": 0, "summary_found": True, "passed": 2}
    assert d["suites"]["bad.test.sh"]["failed"] == 1 and d["suites"]["bad.test.sh"]["exit"] == 1
    wts = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout
    assert "v9.9.9" not in wts, "the scratch worktree must be removed afterwards"


@pytest.mark.parametrize("body", [
    "echo started\nexit 0\n",                              # no summary line, exit 0 (stopped early)
    "echo ---\necho '2 run, 1 failed'\nexit 0\n",          # summary says failed, exit 0
    "echo ---\necho '2 run, 0 failed'\nexit 1\n",          # summary clean, non-zero exit
], ids=["no-summary-exit0", "failed-exit0", "clean-exit1"])
def test_plugin_tests_is_not_green_unless_summary_exit_and_failures_all_agree(script, tmp_path, body):
    """QG F03: the only failing suite in the test above had failed=1 AND exit=1, so each
    conjunct of the all-green rule could be deleted alone with the suite still green."""
    T = script("plugin_tests")
    repo = _plugin_repo(tmp_path, {"s.test.sh": body})
    out = tmp_path / "o.json"
    rc = T.main(["--plugin-repo", str(repo), "--tag", "v9.9.9", "--suites", "s.test.sh", "--out", str(out)])
    assert rc == 1
    assert json.loads(out.read_text())["label"].startswith("NOT GREEN")


def test_plugin_tests_records_the_commit_behind_an_annotated_tag(script, tmp_path):
    """The `plugincommit` claim says 'plugin commit'; `rev-parse <tag>` on an annotated tag
    is the tag object, not the commit."""
    import subprocess
    T = script("plugin_tests")
    repo = _plugin_repo(tmp_path, {"s.test.sh": "echo ---\necho '1 run, 0 failed'\n"}, annotated_tag=True)
    out = tmp_path / "o.json"
    assert T.main(["--plugin-repo", str(repo), "--tag", "v9.9.9", "--suites", "s.test.sh", "--out", str(out)]) == 0
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert json.loads(out.read_text())["commit"] == head


def test_plugin_tests_errors_on_an_unknown_tag_naming_it(script, tmp_path, capsys):
    """QG F13: an unknown --tag raised CalledProcessError out of rev-parse."""
    T = script("plugin_tests")
    repo = _plugin_repo(tmp_path, {"s.test.sh": "echo ---\necho '1 run, 0 failed'\n"})
    out = tmp_path / "o.json"
    assert T.main(["--plugin-repo", str(repo), "--tag", "v0.0.0-absent", "--suites", "s.test.sh", "--out", str(out)]) == 2
    assert "v0.0.0-absent" in capsys.readouterr().err
    assert not out.exists()


# --- the repository's own suites and mutant sweep, counted (QG F11) --------------------

class _Proc:
    def __init__(self, stdout: str, rc: int):
        self.stdout, self.stderr, self.returncode = stdout, "", rc


def _canned_repo_tests(monkeypatch, R, suite_out: str, suite_rc: int, mutant_out: str, mutant_rc: int):
    """Every `uv run` the script makes answers with canned pytest / sweep output (the mutant
    command is told apart by its run_mutants.py argument); git and platform calls go through."""
    real = R.subprocess.run

    def fake_run(cmd, **kw):
        if cmd and cmd[0] != "uv":
            return real(cmd, **kw)
        if any("run_mutants.py" in c for c in cmd):
            return _Proc(mutant_out, mutant_rc)
        return _Proc(suite_out, suite_rc)
    monkeypatch.setattr(R.subprocess, "run", fake_run)


GREEN_SUITE = "....\n4 passed in 0.10s\n"
GREEN_SWEEP = "48/48 live mutants killed; 1 retired\n"


@pytest.mark.parametrize("suite_out, suite_rc, mutant_out, mutant_rc", [
    (GREEN_SUITE, 0, GREEN_SWEEP, 0),
], ids=["all-green"])
def test_repo_tests_is_measured_when_every_suite_and_the_sweep_are_green(script, tmp_path, monkeypatch,
                                                                         suite_out, suite_rc, mutant_out, mutant_rc):
    R = script("repo_tests")
    _canned_repo_tests(monkeypatch, R, suite_out, suite_rc, mutant_out, mutant_rc)
    out = tmp_path / "o.json"
    assert R.main(["--out", str(out)]) == 0
    d = json.loads(out.read_text())
    assert d["label"].startswith("measured (re-run, ")
    assert d["mutants"] == {"killed": 48, "live": 48, "retired": 1, "exit": 0}
    assert d["total_passed"] == 4 * len(R.SUITES)


@pytest.mark.parametrize("suite_out, suite_rc, mutant_out, mutant_rc", [
    ("ERROR: file or directory not found: paper/tests\n", 4, GREEN_SWEEP, 0),   # no summary, exit 4
    ("...F\n3 failed, 1 passed in 0.2s\n", 1, GREEN_SWEEP, 0),                  # failures
    ("3 failed, 1 passed in 0.2s\n", 0, GREEN_SWEEP, 0),                        # failures but exit 0
    ("4 skipped in 0.1s\n", 0, GREEN_SWEEP, 0),                                 # nothing passed
    (GREEN_SUITE, 0, "47/48 live mutants killed; 1 retired\n", 1),             # a survivor
    (GREEN_SUITE, 0, "47/48 live mutants killed; 1 retired\n", 0),             # a survivor, exit 0
    (GREEN_SUITE, 0, "Traceback (most recent call last) ...\n", 0),            # no count line at all
    (GREEN_SUITE, 0, "", 1),                                                   # sweep died silently
], ids=["suite-no-summary-exit4", "suite-failed", "suite-failed-exit0", "suite-only-skipped",
        "mutant-survivor", "mutant-survivor-exit0", "mutant-no-count-line", "mutant-silent-exit1"])
def test_repo_tests_is_not_green_unless_everything_parsed_and_passed(script, tmp_path, monkeypatch,
                                                                     suite_out, suite_rc, mutant_out, mutant_rc):
    """The file behind six claims. An unparsed mutant line left killed and live both None,
    and None == None read as a full kill."""
    R = script("repo_tests")
    _canned_repo_tests(monkeypatch, R, suite_out, suite_rc, mutant_out, mutant_rc)
    out = tmp_path / "o.json"
    assert R.main(["--out", str(out)]) == 1
    assert json.loads(out.read_text())["label"].startswith("NOT GREEN")


# --- A5: the taxonomy is machine-checked -------------------------------------------

HEADER = "id,symptom,why_it_passed_review,found_by,regression_test,label,comp_bio_analogue,source\n"


def test_taxonomy_check_passes_a_consistent_file_and_counts(script, tmp_path):
    X = script("taxonomy_check")
    (tmp_path / "t.py").write_text("")
    csvf = tmp_path / "t.csv"
    csvf.write_text(HEADER
                    + f'"T01","s","w","f","{tmp_path}/t.py","documented, tested","a","src"\n'
                    + '"T02","s","w","f","","documented, no test","a","src"\n')
    # an absolute path is checked as-is when joined: REPO / abs == abs
    failures, stats = X.check(csvf, None)
    assert failures == [] and stats == {"rows": 2, "with_tests": 1, "documented_only": 1}


def test_taxonomy_check_lists_a_missing_test_and_a_mislabelled_row(script, tmp_path):
    X = script("taxonomy_check")
    csvf = tmp_path / "t.csv"
    csvf.write_text(HEADER
                    + '"T01","s","w","f","tests/absent-for-this-test.sh","documented, tested","a","src"\n'
                    + '"T02","s","w","f","","documented, tested","a","src"\n'
                    + '"T02","","w","f","","documented, no test","a","src"\n')
    failures, _ = X.check(csvf, tmp_path)
    joined = "\n".join(failures)
    assert "T01: regression test not found" in joined
    assert "T02: no test cited" in joined
    assert "duplicate id" in joined and "empty symptom" in joined
    assert X.main(["--csv", str(csvf), "--plugin-root", str(tmp_path)]) == 1


# --- A8: figures come from paper/evidence only ------------------------------------------

def test_make_figures_refuses_any_directory_but_the_evidence_dir(tmp_path):
    import importlib.util
    src = _Path(__file__).resolve().parents[1] / "figures" / "make_figures.py"
    spec = importlib.util.spec_from_file_location("make_figures_under_test", src)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with pytest.raises(SystemExit) as e:
        m.guard(str(tmp_path))
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        m.main(["--evidence", "science/out", "--out", str(tmp_path)])
    assert m.guard(str(m.EVIDENCE)) == m.EVIDENCE.resolve()


# --- P1: the publish manifest is prepared and nothing is enabled -----------------------

def test_publish_manifest_is_complete_and_nothing_deposits():
    import re
    import yaml
    paper = _Path(__file__).resolve().parents[1]
    m = yaml.safe_load((paper / "publish.yml").read_text())
    assert m["topic"] and isinstance(m["topic"], str)
    # The author's name and ORCID are values the PRINCIPAL owns. Asserting a literal here
    # tests the principal's data, not the manifest, and turns the next correction to their
    # own name into a test failure for no defect. Read them from the manifest instead and
    # assert they are populated and CONSISTENT with what the paper prints — which is
    # strictly stronger, because it catches the manifest and the paper disagreeing about
    # who wrote it, something the literal never checked.
    name, orcid = m["authors"][0]["name"], m["authors"][0]["orcid"]
    assert isinstance(name, str) and name.strip(), "manifest author name is empty"
    assert re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid)
    main_tex = (paper / "main.tex").read_text()
    assert name in main_tex, f"manifest author name is not the one main.tex prints"
    assert orcid in main_tex, "manifest ORCID is not the one main.tex prints"
    # Affiliation and email were supplied by the principal (#456); same rule as the name:
    # populated, and printed by the paper exactly as the manifest states them.
    affiliation, email = m["authors"][0]["affiliation"], m["authors"][0]["email"]
    assert isinstance(affiliation, str) and affiliation.strip(), "manifest affiliation is empty"
    assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email), "manifest email is malformed"
    assert affiliation in main_tex, "manifest affiliation is not the one main.tex prints"
    assert email in main_tex, "manifest email is not the one main.tex prints"
    assert "to be supplied" not in main_tex, "a placeholder for a principal-supplied value survived"
    flat = yaml.safe_dump(m)
    for placeholder in ("YOUR_HANDLE", "0000-0000", "Family Given", "TBD", "TODO"):
        assert placeholder not in flat
    for a in m["artifacts"]:
        assert not a["path"].startswith("/") and ".." not in a["path"]
        assert (paper / a["path"]).exists(), a["path"]
    # NARROWED, deliberately (principal ruling 2026-10-13): a SANDBOX deposit is permitted so
    # the pipeline can be proven end to end, as the spec requires before any live deposit. The
    # invariant that actually matters is unchanged and still enforced by a test — no venue may
    # deposit LIVE. A live deposit is irreversible and carries a DOI; it stays gated here.
    live = [name for name, v in m["venues"].items()
            if v.get("enabled") is True and v.get("sandbox") is not True]
    assert live == [], f"live deposit enabled in the manifest for: {live}"
    for name, v in m["venues"].items():
        if v.get("enabled") is True:
            assert v.get("sandbox") is True, f"{name} is enabled but not marked sandbox"
    assert m["manual"]["arxiv"]["prepared_only"] is True


def test_the_manifest_carries_the_metadata_a_repository_needs_for_discovery():
    """A deposit nobody can find is a deposit that did not happen. Zenodo indexes these
    fields, so they are declared in the manifest and read by the pipeline rather than
    hardcoded in a workflow node (principal requirement, 2026-10-13)."""
    import yaml
    paper = _Path(__file__).resolve().parents[1]
    m = yaml.safe_load((paper / "publish.yml").read_text())
    z = m["venues"]["zenodo"]
    assert z["upload_type"] == "publication" and z["publication_type"] == "preprint"
    assert m["keywords"] and len(m["keywords"]) >= 4
    assert m["language"] == "eng"
    # a domain category, so the record lands in the right discipline facets
    subjects = m["subjects"]
    assert subjects and all({"term", "identifier", "scheme"} <= set(s) for s in subjects)
    # and a machine-readable link back to the code the paper is about
    rel = {r["relation"]: r for r in m["related_identifiers"]}
    assert "isSupplementTo" in rel, "the deposit must point at the repository it documents"
    assert rel["isSupplementTo"]["identifier"].startswith("https://github.com/")


# --- QG Q1/Q12: the scripts must not depend on the working directory -------------------

def _repo():
    import pathlib
    return pathlib.Path(__file__).resolve().parents[2]


def test_drain1_rows_are_the_same_from_any_working_directory(script, monkeypatch):
    """git pathspecs are cwd-relative: run from paper/, `ls-tree … demo/tests` matched
    nothing and every sealed_test came back empty with exit 0."""
    D = script("drain1_from_git")
    monkeypatch.chdir(_repo() / "paper")
    rows = D.rows(first="28af3c4", last="2e00aa3")
    assert len(rows) == 6
    assert all(r["sealed_test"].startswith("demo/tests/") for r in rows), [r["sealed_test"] for r in rows]


def test_drain1_from_git_main_refuses_an_empty_sealed_test(script, monkeypatch, tmp_path, capsys):
    """A row with no sealed test is a failed reconstruction, not a CSV with a blank column."""
    D = script("drain1_from_git")
    real = D.rows
    monkeypatch.setattr(D, "rows", lambda *a, **k: [dict(r, sealed_test="") for r in real(*a, **k)])
    assert D.main(["--out", str(tmp_path / "x.csv")]) == 2
    assert not (tmp_path / "x.csv").exists()
    assert "sealed_test" in capsys.readouterr().err


def test_run_state_check_is_the_same_from_any_working_directory(script, monkeypatch):
    """`git log -- .v2r/` from paper/ checks paper/.v2r/ — 'never tracked' by accident."""
    R = script("drain1_record_check")
    monkeypatch.chdir(_repo())
    at_root = R.run_state_ever_tracked()
    monkeypatch.chdir(_repo() / "paper")
    assert R.run_state_ever_tracked() == at_root
    # and the probe is live: a directory that IS tracked is reported as tracked from paper/
    assert R.run_state_ever_tracked("paper/evidence") is True


def test_every_default_output_lands_under_the_repository(script, monkeypatch):
    """Defaults were root-relative strings; from paper/ they wrote paper/paper/evidence/."""
    import argparse
    monkeypatch.chdir(_repo() / "paper")
    evidence = (_repo() / "paper" / "evidence").resolve()
    for name in ("drain1_from_git", "drain1_record_check", "record_referee", "science_input",
                 "science_rerun", "agent_run", "plugin_tests", "repo_tests", "taxonomy_check"):
        mod = script(name)
        seen = {}
        orig = argparse.ArgumentParser.parse_args

        def grab(self, args=None, namespace=None, _seen=seen, _orig=orig):
            for act in self._actions:
                if act.dest in ("out", "copy_to", "agent_run", "science", "csv") and act.default:
                    _seen[act.dest] = act.default
            raise SystemExit(0)
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", grab)
        try:
            mod.main([])
        except SystemExit:
            pass
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", orig)
        assert seen, name
        for dest, default in seen.items():
            p = pathlib_resolve(default)
            assert p.is_relative_to(evidence), f"{name} --{dest} default {default!r} -> {p}"


def pathlib_resolve(p):
    import pathlib
    return pathlib.Path(p).resolve()


def test_every_recipe_command_in_the_evidence_readme_runs_from_the_repo_root():
    """QG Q12: the README's recipe column named scripts relative to paper/ while their
    defaults and HF_HOME assumed the repository root, so no single cwd ran them all."""
    import re
    readme = (_repo() / "paper" / "README.md").read_text()
    table = readme[readme.index("## Files"):readme.index("The **evidence-location rule**")]
    cited = re.findall(r"(?<![\w/])((?:paper/)?scripts/[\w./-]+\.(?:py|sh))", table)
    assert cited, "the recipe table cites no scripts"
    for path in cited:
        assert (_repo() / path).is_file(), f"{path} does not exist relative to the repository root"


def test_science_rerun_records_the_snapshot_revision_of_the_named_model(script, tmp_path, monkeypatch):
    """QG Q2: the HF cache stores snapshots/<revision>/model.safetensors as a symlink into
    blobs/. Resolving first recorded the blob directory as the 'revision' and the blob hash
    as the 'weights_file'; rglob over the whole hub could also hash a different model."""
    import hashlib
    S = script("science_rerun")
    hub = tmp_path / "hub"

    def cache(model_id, rev, content):
        root = hub / f"models--{model_id.replace('/', '--')}"
        blob = root / "blobs" / hashlib.sha256(content).hexdigest()
        blob.parent.mkdir(parents=True)
        blob.write_bytes(content)
        snap = root / "snapshots" / rev
        snap.mkdir(parents=True)
        (snap / "model.safetensors").symlink_to(blob)

    cache("aaa/other-model", "1111111", b"the wrong weights")      # sorts first in the hub
    cache("facebook/esm2_t33_650M_UR50D", "08e4846e", b"the right weights")
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    f = S.model_facts("facebook/esm2_t33_650M_UR50D")
    assert f["revision"] == "08e4846e"
    assert f["weights_file"] == "model.safetensors"
    assert f["weights_sha256"] == hashlib.sha256(b"the right weights").hexdigest()
    assert f["weights_bytes"] == len(b"the right weights")


@pytest.mark.parametrize("match, per_position, measured", [
    ({"a": True, "b": True}, True, True),
    ({"a": True, "b": False}, True, False),
    ({"a": True, "b": True}, False, False),      # QG Q6: the per-position means are a result too
])
def test_science_rerun_labels_measured_only_when_every_comparison_matched(script, match, per_position, measured):
    """main.tex says every headline value AND all per-position means matched; the label —
    the field claims.py checks — must require both, or a per-position drift builds green."""
    S = script("science_rerun")
    label, rc = S.verdict(match, per_position, "2026-10-01")
    assert label.startswith("measured (re-run, 2026-10-01)") is measured
    assert label.startswith("MISMATCH") is (not measured)
    assert rc == (0 if measured else 1)
