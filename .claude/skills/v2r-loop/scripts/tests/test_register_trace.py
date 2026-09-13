import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_emit_span_is_a_noop_without_credentials(monkeypatch, capsys):
    monkeypatch.delenv("WANDB_API_KEY", raising=False)
    register.emit_span("unit.close", unit="U-001", attempts=1)
    assert capsys.readouterr().err == ""


def test_emit_span_reports_a_dropped_span_once(monkeypatch, capsys):
    monkeypatch.setenv("WANDB_API_KEY", "fake")
    monkeypatch.setattr(register, "_SPAN_SINK", None)
    monkeypatch.setattr(register, "_SPAN_WARNED", False)
    monkeypatch.setitem(sys.modules, "weave", None)  # `import weave` then raises

    register.emit_span("unit.close", unit="U-001")
    register.emit_span("unit.close", unit="U-002")

    err = capsys.readouterr().err
    assert "weave span dropped" in err
    assert err.count("weave span dropped") == 1


def test_emit_span_records_when_a_sink_is_installed(monkeypatch):
    captured = []
    monkeypatch.setattr(register, "_SPAN_SINK", captured.append)
    register.emit_span("unit.park", unit="U-014", attempts=3)
    assert captured == [{"name": "unit.park", "unit": "U-014", "attempts": 3}]


def test_close_emits_a_span(monkeypatch, git_repo, register_data):
    captured = []
    monkeypatch.setattr(register, "_SPAN_SINK", captured.append)
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    (sealed / "test_u001.py").write_text("def test_ok():\n    assert True\n")
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register.save(register.REGISTER, register_data)

    register.main(["close", "U-001"])

    assert any(span["name"] == "unit.close" for span in captured)
