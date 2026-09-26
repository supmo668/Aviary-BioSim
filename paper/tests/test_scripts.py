"""Standing rules 2 and 3 of the white-paper plan, asserted.

Rule 2: every run saves its exact config next to its output — one implementation,
paper/scripts/_provenance.py, that every script calls.
Rule 3: a missing or empty --inputs directory is an ERROR (exit 2) that NAMES the path
checked. Never a finding of "unrecoverable" against a tree that never had the files.
"""
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
