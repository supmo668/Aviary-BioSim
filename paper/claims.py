#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""A7 — every number in the paper maps to a file:field under paper/evidence/ with a label.

Exit 1 on: an unmapped number in main.tex, a missing evidence file, a value mismatch, a
claim whose label is not supported by the evidence file's own label (or whose file says it
did not pass), or a claim labelled reported/reconstructed/documented/recovered/queried
phrased as measured.
Emits claims.tex: one \\newcommand per claim, so the TeX never carries a literal number.
"""
import json
import re
import sys
from pathlib import Path

import yaml

# Braces are NOT excluded: macro arguments that legitimately hold digits (\ref{sec:2},
# p{2.6cm}, [width=0.8\linewidth]) are stripped by REF or carry ALLOW_LINE, so excluding
# brace-adjacent digits only hid a literal number inside \textbf{} or \emph{} (QG F12).
# A digit glued to a letter (ESM-2, 650M, U-020) is part of a name, not a quantity.
NUMBER = re.compile(r"(?<![\w\\.-])-?\d[\d,]*(?:\.\d+)?(?!\w)")
ALLOW_LINE = "% claims: ignore-line"
YEAR = re.compile(r"\b(19\d{2}|20[0-3]\d)\b")     # plausible years only; 2090 is a count
REF = re.compile(r"\\(ref|cite|label|eqref|S|section|subsection|input|includegraphics|usepackage|documentclass|"
                 r"begin|end|hline|cline|multicolumn|vspace|hspace|rule|geometry|fontsize|caption|url|href)"
                 r"(\[[^\]]*\])?\{[^}]*\}|(?:Fig|Figure|Table|Section|Eq|Appendix)\.?~?\d+|\\\\\[[^\]]*\]")
MEASURED_WORDS = re.compile(r"\b(measured|we measure|re-run|reran|re-ran)\b", re.I)
# A sentence ends at .!? + whitespace, at a blank line, or at a closing brace that ends a
# heading such as \paragraph{The agent's run.} — otherwise a caption and the paragraph
# after it read as one sentence and every claim in it inherits the caption's wording.
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n\s*\n|(?<=[.!?]\})\s*")


FAILING_LABEL = re.compile(r"^\s*(NOT\b|MISMATCH\b)", re.I)


def evidence_labels(root: Path, file: str) -> list:
    """The label(s) an evidence file gives itself. A JSON file: its top-level `label`. A CSV:
    its `.provenance.json` sidecar's label, else every row's `label` column."""
    import csv
    p = root / "evidence" / file
    if p.suffix != ".csv":
        d = json.loads(p.read_text())
        return [d.get("label") if isinstance(d, dict) else None]
    side = p.with_suffix(".provenance.json")
    if side.exists():
        return [json.loads(side.read_text()).get("label")]
    with p.open(newline="") as f:
        return [row.get("label") for row in csv.DictReader(f)] or [None]


def label_error(c: dict, labels: list):
    """Why the claim's label is not supported by its evidence, or None (QG Q4).

    A label is a field inside the evidence file. The claim must say no more than the file:
    its label is a prefix of the file's own label, or it DOWNGRADES to `reported` (the
    published run's values held inside a re-run file). A file that labels itself as not
    having passed (NOT MEASURED, NOT GREEN, MISMATCH) supports no claim at all."""
    file = c["source"].partition(":")[0]
    for ev in labels:
        if not ev:
            return f"evidence label: {file} has no label (claim {c['id']})"
        if FAILING_LABEL.match(ev):
            return f"evidence label: {file} says {ev!r}; claim {c['id']} cannot stand on it"
    if c["label"].split()[0] == "reported":
        return None
    if all(ev.startswith(c["label"]) for ev in labels):
        return None
    return (f"evidence label: claim {c['id']} is labelled {c['label']!r} but {file} says "
            f"{sorted(set(labels))[0]!r}")


def resolve(root: Path, source: str):
    file, _, field = source.partition(":")
    p = root / "evidence" / file
    if not p.exists():
        return None, f"missing file {p}"
    if p.suffix == ".csv":
        rows = p.read_text().count("\n") - 1
        d = {"rows": rows}
    else:
        d = json.loads(p.read_text())
    parts = field.split(".") if field else []
    i = 0
    while i < len(parts):
        if isinstance(d, list):
            try:
                d = d[int(parts[i])]
                i += 1
            except (ValueError, IndexError):
                return None, f"field {field} not in {file}"
        elif isinstance(d, dict):
            # Keys may themselves contain dots (a suite named register.test.sh): take the
            # longest run of components that names an existing key.
            for j in range(len(parts), i, -1):
                key = ".".join(parts[i:j])
                if key in d:
                    d = d[key]
                    i = j
                    break
            else:
                return None, f"field {field} not in {file}"
        else:
            return None, f"field {field} not in {file}"
    return d, None


def fmt(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}".replace("-", "\u2212")
    return _tex(v)                        # a string claim (an identifier, a release) is TeX text


def _tex(s: str) -> str:
    return (str(s).replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("%", "\\%")
            .replace("&", "\\&").replace("#", "\\#").replace("-", "\\mbox{-}"))


def _cell(v) -> str:
    """A table value; a long unbroken string (a digest) gets break points so it wraps."""
    if isinstance(v, str) and len(v) > 20 and " " not in v:
        return "\\allowbreak{}".join(_tex(v[i:i + 12]) for i in range(0, len(v), 12))
    return fmt(v)


def _path_cell(source: str) -> str:
    """An evidence file:field for the table, breakable after / . : and _ (QG Q29, A7-14) —
    \\texttt never breaks a word, so a long path ran off the page. Underscores count too:
    a field named for what it holds (`named_by_the_agent_in_c_peptide_count`) offers no
    other break point, and the row overflowed instead of wrapping."""
    return re.sub(r"([/.:]|\\_)", lambda m: m.group(1) + "\\allowbreak{}", _tex(source))


def claims_table(claims: list[dict]) -> str:
    """The appendix: every claim, its value, its label and its evidence field."""
    lines = ["% GENERATED by claims.py — do not edit",
             "\\begin{longtable}{@{}lp{2.6cm}p{3.2cm}p{5.6cm}@{}}",
             "\\toprule id & value & label & evidence (file:field) \\\\ \\midrule \\endhead"]
    for c in claims:
        if c.get("table", True) is False:
            continue          # a macro, but not an appendix row (F33 scope: methods + evidence only)
        lines.append(f"\\texttt{{{_tex(c['id'])}}} & {_cell(c['value'])} & {_tex(c['label'])} & "
                     f"\\texttt{{{_path_cell(c['source'])}}} \\\\")
    lines += ["\\bottomrule", "\\end{longtable}", ""]
    return "\n".join(lines)


def check(root: Path) -> list[str]:
    errs, macros = [], []
    spec = yaml.safe_load((root / "claims.yaml").read_text()) or {}
    claims = spec.get("claims", [])
    tex_path = root / "main.tex"
    tex = tex_path.read_text() if tex_path.exists() else ""
    for c in claims:
        v, err = resolve(root, c["source"])
        if err:
            errs.append(err)
            continue
        want = c["value"]
        if isinstance(want, float) or isinstance(v, float):
            ok = abs(float(v) - float(want)) < 1e-9
        else:
            ok = v == want
        if not ok:
            errs.append(f"mismatch {c['id']}: claims.yaml={want} evidence={v} ({c['source']})")
        lerr = label_error(c, evidence_labels(root, c["source"].partition(":")[0]))
        if lerr:
            errs.append(lerr)
        macros.append(f"\\newcommand{{\\claim{c['id']}}}{{{fmt(want)}}}")
        if c["label"].split()[0] != "measured":
            for sent in re.split(SENTENCE, tex):
                if f"\\claim{c['id']}" in sent and MEASURED_WORDS.search(sent):
                    errs.append(f"reported claim phrased as measured: {c['id']} in: {sent.strip()[:80]}")
    (root / "claims.tex").write_text("% GENERATED by claims.py — do not edit\n" + "\n".join(macros) + "\n")
    (root / "claims-table.tex").write_text(claims_table(claims))
    for n, line in enumerate(tex.splitlines(), 1):
        if ALLOW_LINE in line or line.lstrip().startswith("%"):
            continue
        scrub = REF.sub("", YEAR.sub("", line))
        scrub = re.sub(r"\\claim[a-zA-Z0-9]+\{\}", "", scrub)
        for m in NUMBER.finditer(scrub):
            errs.append(f"unmapped number {m.group()!r} at main.tex:{n}")
    return errs


if __name__ == "__main__":
    e = check(Path(__file__).parent)
    print("\n".join(e) or "claims: ok")
    sys.exit(1 if e else 0)
