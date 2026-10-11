"""A7 — the claims-traceability check, on synthetic evidence."""
import json
import re
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


def _label_for(name, claims):
    """The label a synthetic evidence file carries when a test does not set one: the
    strongest label any claim citing it uses (a claim may only ever DOWNGRADE to reported)."""
    labels = [c["label"] for c in claims if c["source"].split(":")[0] == name]
    strong = [l for l in labels if not l.startswith("reported")]
    return (strong or labels or ["measured"])[0]


# claims.py refuses evidence that does not establish its own pinning (QG F1), so a synthetic
# evidence file stands in for a properly pinned one unless a test sets its provenance itself.
PINNED = {"git_sha": "0" * 40, "tree_clean": True}


def setup(tmp_path, claims, tex, evidence):
    (tmp_path / "evidence").mkdir()
    for name, body in evidence.items():
        if name.endswith(".csv"):
            (tmp_path / "evidence" / name).write_text(body)
            side = (tmp_path / "evidence" / name).with_suffix(".provenance.json")
            if not side.exists():
                side.write_text(json.dumps({"label": _label_for(name, claims), **PINNED}))
            continue
        if isinstance(body, dict) and "label" not in body:
            body = {"label": _label_for(name, claims), **body}
        if isinstance(body, dict) and "provenance" not in body:
            body = {**body, "provenance": dict(PINNED)}
        (tmp_path / "evidence" / name).write_text(json.dumps(body))
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
    assert "longtable" in table and "2,090" in table
    assert "e.json:x\\_y" in table.replace(r"\allowbreak{}", "")   # paths may break (Q29)


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
    digest = "0123456789abcdef" * 4                      # invented; never a real input's digest
    root = setup(tmp_path,
        [{"id": "sha", "value": digest, "label": "measured", "source": "e.json:s", "text": "t"},
         {"id": "rel", "value": "2026_03", "label": "measured", "source": "e.json:r", "text": "t"}],
        None, {"e.json": {"s": digest, "r": "2026_03"}})
    assert C.check(root) == []
    table = (root / "claims-table.tex").read_text()
    assert r"\begin{longtable}{@{}lp{" in table, "the value column must be a wrapping p column"
    row = next(l for l in table.splitlines() if l.startswith(r"\texttt{sha}"))
    assert r"\allowbreak" in row and row.replace(r"\allowbreak{}", "").count(digest) == 1
    rel_row = next(l for l in table.splitlines() if l.startswith(r"\texttt{rel}"))
    assert r"\allowbreak" not in rel_row.split("&")[1], "a short VALUE gets no break points"
    assert digest in (root / "claims.tex").read_text(), "the text macro carries the digest unbroken"


# --- QG Q4: a claim's label is checked against the evidence file's own label ------------

@pytest.mark.parametrize("ev_label", ["MISMATCH — reported; see limitations",
                                      "NOT MEASURED — the referee did not produce a passing verdict",
                                      "NOT GREEN — a suite failed"])
def test_fails_when_the_evidence_says_it_did_not_pass(tmp_path, ev_label):
    """A file whose own label says the run failed must not build, even if its numbers
    still equal claims.yaml — the paper would print them as measured."""
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured (re-run, 2026-09-26)", "source": "e.json:n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": ev_label, "n": 6}})
    assert any("evidence label" in e and "e.json" in e for e in C.check(root))


@pytest.mark.parametrize("ev_label", ["MISMATCH — reported; see limitations",
                                      "NOT MEASURED — the referee did not produce a passing verdict"])
def test_a_reported_claim_cannot_stand_on_a_file_that_did_not_pass(tmp_path, ev_label):
    """QG F01: `reported` skips the prefix check (the allowed downgrade), so the failing-label
    check at label_error is the ONLY thing between a MISMATCH file and the paper. The test
    above never reached it — a measured claim is refused by the prefix check first."""
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "reported", "source": "e.json:published.n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": ev_label, "published": {"n": 6}}})
    errs = C.check(root)
    assert any("evidence label" in e and "cannot stand" in e for e in errs), errs


def test_fails_when_a_float_claim_differs_from_its_evidence(tmp_path):
    """QG F02: the float path compares within 1e-9; a drifted mean must be a mismatch."""
    root = setup(tmp_path,
        [{"id": "mean", "value": -13.02, "label": "measured", "source": "e.json:y", "text": "t"}],
        r"\claimmean{}", {"e.json": {"y": -13.03}})
    assert any(e.startswith("mismatch mean") for e in C.check(root))


@pytest.mark.parametrize("tex", [r"We closed \textbf{48} tasks.", r"\emph{17} failures remained."])
def test_a_number_inside_a_formatting_macro_is_still_unmapped(tmp_path, tex):
    """QG F12: the number gate excluded brace-adjacent digits to skip macro arguments such
    as \\ref{sec:2}; those are stripped by REF first, so the exclusion only hid a literal
    number wrapped in \\textbf or \\emph."""
    root = setup(tmp_path, [], tex, {})
    assert any("unmapped number" in e for e in C.check(root))


def test_fails_when_a_claim_upgrades_its_evidence_label(tmp_path):
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured (re-run, 2026-09-26)", "source": "e.json:n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": "reported (artifact counted, 2026-09-26)", "n": 6}})
    assert any("evidence label" in e for e in C.check(root))


def test_a_claim_may_downgrade_to_reported(tmp_path):
    """The published run's values sit inside a re-run file: reporting them is honest."""
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "reported", "source": "e.json:published.n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": "measured (re-run, 2026-09-26)", "published": {"n": 6}}})
    assert C.check(root) == []


def test_fails_when_the_evidence_has_no_label(tmp_path):
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured", "source": "e.json:n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": None, "n": 6}})
    assert any("no label" in e for e in C.check(root))


def test_a_csv_label_comes_from_its_rows_or_its_sidecar(tmp_path):
    root = setup(tmp_path,
        [{"id": "r", "value": 2, "label": "documented", "source": "t.csv:rows", "text": ""}],
        None, {"t.csv": "id,label\n1,\"documented, tested\"\n2,documented\n"})
    (tmp_path / "evidence" / "t.provenance.json").unlink()
    # Only the LABEL question is under test here. Deleting the sidecar also removes the
    # file's pinning evidence, which claims.py now refuses separately (QG F1) — that
    # refusal is correct and is asserted in its own test.
    assert [e for e in C.check(root) if "evidence label" in e] == []
    (tmp_path / "evidence" / "t.csv").write_text("id,label\n1,reported\n2,documented\n")
    assert any("evidence label" in e for e in C.check(root))


def _pinning_case(tmp_path, provenance):
    return setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured", "source": "e.json:n", "text": ""}],
        r"\claimn{}", {"e.json": {"label": "measured", "n": 6, "provenance": provenance}})


def test_a_claim_cannot_stand_on_evidence_produced_on_a_dirty_tree(tmp_path):
    """QG F1. tree_clean was written by every producer and read by nothing, so evidence
    recorded on a dirty tree satisfied every check while the paper asserted the opposite."""
    root = _pinning_case(tmp_path, {"git_sha": "0" * 40, "tree_clean": False,
                                    "dirty_paths": ["paper/scripts/x.py"]})
    errs = C.check(root)
    assert any("dirty tree" in e and "paper/scripts/x.py" in e for e in errs), errs


def test_a_claim_cannot_stand_on_evidence_that_never_established_its_pinning(tmp_path):
    """An ABSENT tree_clean is not a pass: it means the guarantee was never checked. This is
    the live case — one shipped file predates the rule — so silence must not read as clean."""
    root = _pinning_case(tmp_path, {"git_sha": "0" * 40})
    assert any("no tree_clean" in e for e in C.check(root)), C.check(root)


def test_a_named_exception_may_stand_unpinned_with_a_recorded_reason(tmp_path):
    """An exception is DECLARED, not forgotten: each carries a reason, so a file that simply
    lost its provenance can never be mistaken for one we decided to allow. The standing
    exceptions are the two hand-authored inputs, which no script produces and which therefore
    have no producing commit to pin."""
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "queried", "source": "weave-count.json:n", "text": ""}],
        r"\claimn{}", {"weave-count.json": {"label": "queried", "n": 6}})
    assert C.check(root) == []
    assert set(C.UNPINNED_ALLOWED) == {"weave-count.json", "taxonomy.csv"}
    assert all(C.UNPINNED_ALLOWED.values()), "every exception must carry a reason"


def test_an_allowlisted_file_that_HAS_a_provenance_block_but_no_tree_clean_is_allowed(tmp_path, monkeypatch):
    """Both escapes in pinning_error() must stay covered. The two standing exceptions have no
    provenance block at all, so they return at the earlier `not isinstance(prov, dict)` check
    and the allow-list branch AFTER the tree_clean test became unreachable from every test —
    deleting it survived the suite. This case reaches it: a block that exists but says nothing
    about the tree, which is the shape a file predating the rule actually has."""
    monkeypatch.setitem(C.UNPINNED_ALLOWED, "legacy.json", "predates the rule; disclosed")
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured", "source": "legacy.json:n", "text": ""}],
        r"\claimn{}", {"legacy.json": {"label": "measured", "n": 6,
                                       "provenance": {"git_sha": "0" * 40}}})
    assert C.pinning_error(root, "legacy.json") is None
    assert C.check(root) == []
    # and without the allow-list entry the very same file is refused
    monkeypatch.delitem(C.UNPINNED_ALLOWED, "legacy.json")
    assert "no tree_clean" in (C.pinning_error(root, "legacy.json") or "")


def test_the_one_commit_invariant_refuses_a_set_rebuilt_from_two_commits(tmp_path):
    """QG F15. The appendix says five file groups were rebuilt from ONE commit but binds a
    macro resolving to just one file's sha, so the plural sentence was asserted, not checked."""
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured", "source": "science.json:n", "text": ""}],
        r"\claimn{}",
        {"science.json": {"label": "measured", "n": 6,
                          "provenance": {"git_sha": "a" * 40, "tree_clean": True}},
         "agent-run.json": {"label": "measured", "n": 6,
                            "provenance": {"git_sha": "b" * 40, "tree_clean": True}}})
    assert any("one-commit invariant" in e for e in C.check(root)), C.check(root)


def test_the_one_commit_invariant_passes_when_they_agree(tmp_path):
    root = setup(tmp_path,
        [{"id": "n", "value": 6, "label": "measured", "source": "science.json:n", "text": ""}],
        r"\claimn{}",
        {"science.json": {"label": "measured", "n": 6,
                          "provenance": {"git_sha": "a" * 40, "tree_clean": True}},
         "agent-run.json": {"label": "measured", "n": 6,
                            "provenance": {"git_sha": "a" * 40, "tree_clean": True}}})
    assert C.check(root) == []


def test_every_committed_evidence_file_is_pinned_or_a_declared_exception():
    """The shipped set, not only the writers: each real evidence file either carries
    tree_clean true or is named in UNPINNED_ALLOWED with a reason."""
    root = Path(__file__).resolve().parents[1]
    for f in sorted((root / "evidence").glob("*.json")):
        if f.name.endswith(".provenance.json"):
            continue
        err = C.pinning_error(root, f.name)
        assert err is None, err


def test_a_claim_marked_table_false_is_a_macro_but_not_an_appendix_row(tmp_path):
    """QG Q7: the F33 ruling publishes the input's identifier, release and digest in the
    methods and the evidence file only; the appendix table reprinted all three."""
    root = setup(tmp_path,
        [{"id": "acc", "value": "X00000", "label": "measured", "source": "e.json:a", "text": "t", "table": False},
         {"id": "n", "value": 6, "label": "measured", "source": "e.json:n", "text": "t"}],
        r"\claimacc{} \claimn{}", {"e.json": {"a": "X00000", "n": 6}})
    assert C.check(root) == []
    assert r"\newcommand{\claimacc}{X00000}" in (root / "claims.tex").read_text()
    table = (root / "claims-table.tex").read_text()
    assert "X00000" not in table and r"\texttt{acc}" not in table
    assert r"\texttt{n}" in table


def test_the_real_appendix_carries_no_f33_value():
    """Whatever the claims say, the generated appendix of THIS paper must not print the
    published input's identifier, release or digest."""
    import yaml as _y
    paper = Path(__file__).resolve().parents[1]
    claims = {c["id"]: c for c in _y.safe_load((paper / "claims.yaml").read_text())["claims"]}
    table = C.claims_table(list(claims.values()))
    for cid in ("accession", "uprelease", "seqsha"):
        assert str(claims[cid]["value"]) not in table.replace(r"\allowbreak{}", "").replace(r"\_", "_"), cid


# --- the paper's own text against its claims (QG Q9, Q11, Q14) ---------------------------

def _paper():
    return Path(__file__).resolve().parents[1]


def _kind(label: str) -> str:
    return re.split(r"[(;]", label)[0].strip()


def test_every_label_kind_in_use_is_defined_in_the_paper_and_the_readme():
    """QG Q9: the paper promised 'one of five labels' while three claims carried a sixth,
    'recovered record'. Every kind used must be in both legends, and the count must agree."""
    import yaml as _y
    kinds = {_kind(c["label"]) for c in _y.safe_load((_paper() / "claims.yaml").read_text())["claims"]}
    tex = (_paper() / "main.tex").read_text()
    readme = (_paper() / "README.md").read_text()
    for k in kinds:
        assert f"\\emph{{{k}}}" in tex, f"main.tex does not define the label {k!r}"
        assert f"**{k}**" in readme, f"paper/README.md does not define the label {k!r}"
    words = {5: "five", 6: "six", 7: "seven"}
    assert f"one of {words[len(kinds)]} labels" in tex


def test_every_c_peptide_control_in_the_evidence_is_cited():
    """QG Q11: the agent probed five C-peptide positions; the paper printed three, with no
    recorded rule for which. Every control the evidence holds must be a cited claim."""
    import yaml as _y
    sci = json.loads((_paper() / "evidence" / "science.json").read_text())
    claims = _y.safe_load((_paper() / "claims.yaml").read_text())["claims"]
    by_source = {c["source"]: c["id"] for c in claims}
    tex = (_paper() / "main.tex").read_text()
    for pos in sci["headline"]["c_peptide_controls"]:
        src = f"science.json:headline.c_peptide_controls.{pos}"
        assert src in by_source, f"no claim for the control at position {pos}"
        assert f"\\claim{by_source[src]}{{}}" in tex, f"control at {pos} is not cited in main.tex"


def test_the_readme_gives_the_referee_configuration_the_paper_points_to():
    """QG Q14: main.tex sends readers to the README for the configuration key and the
    referee command; it had neither."""
    readme = (_paper() / "README.md").read_text()
    rr = (_paper() / "scripts" / "record_referee.py").read_text()
    cmd = re.search(r'REFEREE_COMMAND = "([^"]+)"', rr).group(1)
    assert "tests.referee_command" in readme
    assert cmd in readme


def test_a_long_evidence_path_can_wrap_in_the_appendix_table(tmp_path):
    """QG Q29: file:field paths in a fixed-width column ran up to 192pt off the page,
    because \\texttt never breaks a word. Break points go after / . and : only."""
    src = "repo-tests.json:suites..claude/skills/v2r-loop/scripts/tests.passed"
    root = setup(tmp_path, [{"id": "n", "value": 1, "label": "measured", "source": src, "text": "t"}],
                 None, {"repo-tests.json": {"suites": {".claude/skills/v2r-loop/scripts/tests": {"passed": 1}}}})
    assert C.check(root) == []
    row = next(l for l in (root / "claims-table.tex").read_text().splitlines() if l.startswith(r"\texttt{n}"))
    cell = row.split("&")[3]
    assert cell.count(r"\allowbreak{}") >= 5
    flat = cell.replace(r"\allowbreak{}", "").replace(r"\mbox{-}", "-")
    assert "repo-tests.json:suites..claude/skills/v2r-loop/scripts/tests.passed" in flat
