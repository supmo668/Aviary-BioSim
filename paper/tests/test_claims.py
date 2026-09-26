"""A7 — the claims-traceability check, on synthetic evidence."""
import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys_path_saved = list(sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import claims as C
finally:
    sys.path[:] = sys_path_saved


def setup(tmp_path, claims, tex, evidence):
    (tmp_path / "evidence").mkdir()
    for name, body in evidence.items():
        (tmp_path / "evidence" / name).write_text(json.dumps(body) if not name.endswith(".csv") else body)
    (tmp_path / "claims.yaml").write_text(yaml.safe_dump({"claims": claims}))
    if tex is not None:
        (tmp_path / "main.tex").write_text(textwrap.dedent(tex))
    return tmp_path


def test_passes_when_every_number_is_a_macro(tmp_path):
    root = setup(tmp_path,
        [{"id": "subs", "value": 2090, "label": "reported", "source": "science.json:published.substitutions",
          "text": "substitutions scored"}],
        r"We scored \claimsubs{} substitutions in \S2.", {"science.json": {"published": {"substitutions": 2090}}})
    assert C.check(root) == []


def test_fails_on_a_bare_number(tmp_path):
    root = setup(tmp_path, [], "There were 2090 of them.", {})
    assert any("unmapped number" in e for e in C.check(root))


def test_fails_on_missing_file_and_on_mismatch(tmp_path):
    root = setup(tmp_path,
        [{"id": "a", "value": 1, "label": "measured", "source": "gone.json:x", "text": ""},
         {"id": "b", "value": 2, "label": "measured", "source": "e.json:x", "text": ""}],
        r"\claima{} \claimb{}", {"e.json": {"x": 3}})
    errs = C.check(root)
    assert any("missing file" in e for e in errs) and any("mismatch" in e for e in errs)


def test_fails_when_a_reported_claim_is_called_measured(tmp_path):
    root = setup(tmp_path,
        [{"id": "n", "value": 66, "label": "reported", "source": "e.json:n", "text": ""}],
        r"We measured \claimn{} choices. Fine.", {"e.json": {"n": 66}})
    assert any("reported claim phrased as measured" in e for e in C.check(root))


def test_allow_list_years_refs_and_marked_lines(tmp_path):
    root = setup(tmp_path, [], r"In 2026 see Section~\ref{sec:2} and Fig.~2. % claims: ignore-line", {})
    assert C.check(root) == []
    (tmp_path / "b").mkdir()
    root2 = setup(tmp_path / "b", [], "In 2026 see Section~\\ref{sec:2} and Figure~3.\n% a comment with 42 in it\n", {})
    assert C.check(root2) == []


def test_a_count_that_looks_like_a_far_year_is_still_a_number(tmp_path):
    root = setup(tmp_path, [], "There were 2090 of them, and 1999 before.", {})
    errs = C.check(root)
    assert any("'2090'" in e for e in errs)
    assert not any("'1999'" in e for e in errs)


def test_dotted_keys_resolve_by_longest_match(tmp_path):
    root = setup(tmp_path, [{"id": "r", "value": 60, "label": "measured", "source": "p.json:suites.register.test.sh.run", "text": ""}],
                 None, {"p.json": {"suites": {"register.test.sh": {"run": 60}}}})
    assert C.check(root) == []


def test_generates_macros_and_formats_values(tmp_path):
    root = setup(tmp_path,
        [{"id": "subs", "value": 2090, "label": "reported", "source": "e.json:x", "text": "t"},
         {"id": "mean", "value": -13.02, "label": "measured", "source": "e.json:y", "text": "t"}],
        r"\claimsubs{} \claimmean{}", {"e.json": {"x": 2090, "y": -13.02}})
    assert C.check(root) == []
    tex = (root / "claims.tex").read_text()
    assert r"\newcommand{\claimsubs}{2,090}" in tex
    assert "\\newcommand{\\claimmean}{\u221213.02}" in tex


def test_csv_rows_and_nested_list_fields_resolve(tmp_path):
    root = setup(tmp_path,
        [{"id": "rows", "value": 2, "label": "reconstructed", "source": "t.csv:rows", "text": ""},
         {"id": "first", "value": 7, "label": "measured", "source": "e.json:items.0.n", "text": ""}],
        None, {"t.csv": "a,b\n1,2\n3,4\n", "e.json": {"items": [{"n": 7}]}})
    assert C.check(root) == []


def test_a_missing_main_tex_only_resolves_claims(tmp_path):
    root = setup(tmp_path, [{"id": "a", "value": 1, "label": "measured", "source": "e.json:x", "text": ""}],
                 None, {"e.json": {"x": 1}})
    assert C.check(root) == []
    assert (root / "claims.tex").exists()
