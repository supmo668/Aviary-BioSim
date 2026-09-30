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


def test_generates_the_appendix_table(tmp_path):
    root = setup(tmp_path,
        [{"id": "subs", "value": 2090, "label": "reported", "source": "e.json:x_y", "text": "t"}],
        None, {"e.json": {"x_y": 2090}})
    assert C.check(root) == []
    table = (root / "claims-table.tex").read_text()
    assert "longtable" in table and "2,090" in table and "e.json:x\\_y" in table


def test_a_heading_or_blank_line_ends_a_sentence(tmp_path):
    root = setup(tmp_path,
        [{"id": "n", "value": 66, "label": "reported", "source": "e.json:n", "text": ""}],
        "Dashed lines are measured.}\n\\paragraph{The run.} It chose \\claimn{} things.\n\nWe re-run nothing here.\n",
        {"e.json": {"n": 66}})
    assert C.check(root) == []


def test_a_string_claim_is_escaped_for_tex_in_macro_and_table(tmp_path):
    # A release name like 2026_03 is a string claim; unescaped, its underscore is a TeX error.
    root = setup(tmp_path,
        [{"id": "rel", "value": "2026_03", "label": "measured", "source": "e.json:r", "text": "t"}],
        r"Release \claimrel{}.", {"e.json": {"r": "2026_03"}})
    assert C.check(root) == []
    assert r"\newcommand{\claimrel}{2026\_03}" in (root / "claims.tex").read_text()
    assert r"& 2026\_03 &" in (root / "claims-table.tex").read_text()


def test_a_long_string_claim_can_wrap_in_the_appendix_table(tmp_path):
    # A 64-character digest in a column that cannot wrap runs off the page.
    digest = "99603f8fb1e9872e2d24ee1e9f85108c2bddea6b148a0f1099e16ba2715c8263"
    root = setup(tmp_path,
        [{"id": "sha", "value": digest, "label": "measured", "source": "e.json:s", "text": "t"},
         {"id": "rel", "value": "2026_03", "label": "measured", "source": "e.json:r", "text": "t"}],
        None, {"e.json": {"s": digest, "r": "2026_03"}})
    assert C.check(root) == []
    table = (root / "claims-table.tex").read_text()
    assert r"\begin{longtable}{@{}lp{" in table, "the value column must be a wrapping p column"
    row = next(l for l in table.splitlines() if l.startswith(r"\texttt{sha}"))
    assert r"\allowbreak" in row and row.replace(r"\allowbreak{}", "").count(digest) == 1
    assert r"\allowbreak" not in next(l for l in table.splitlines() if l.startswith(r"\texttt{rel}"))
    assert digest in (root / "claims.tex").read_text(), "the text macro carries the digest unbroken"
