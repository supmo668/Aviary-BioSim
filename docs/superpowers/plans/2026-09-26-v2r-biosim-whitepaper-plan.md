# v2r-loop / BioSim White Paper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `paper/` — the evidence files, the claims-traceability check, the figures, the LaTeX draft and the publish manifest for a publication-rigour white paper on the v2r-loop as a lab method, with BioSim as the worked experiment — such that every number in the TeX maps to a file under `paper/evidence/` with a label, and the CTO's publication-rigour review can start.

**Architecture:** Evidence is produced by small standalone scripts under `paper/scripts/`, each writing one JSON/CSV under `paper/evidence/` *with its exact run config beside the numbers* (git SHA, model ids, versions, seeds, inputs path, timestamp). The TeX never carries a literal number: `paper/claims.py` reads `paper/claims.yaml`, resolves every claim against its evidence file, emits `paper/claims.tex` (one macro per claim) and fails the build on any unmapped number, missing file, value mismatch, or a *reported* claim phrased as *measured*. Figures are generated only from `paper/evidence/`.

**Tech Stack:** Python 3.12 via `uv run --script` (PEP-723 headers, no global installs), `pytest`, `pyyaml`, `requests`, `torch` + `transformers` (A3c only, isolated), `matplotlib`, LaTeX (`latexmk` or `tectonic`, whichever is present), the aiadlc plugin's `tools/referee` and `tools/register` (v0.64.0).

**Spec:** `docs/superpowers/specs/2026-09-25-v2r-biosim-whitepaper-design.md` in the coordinating (private) bioFM repository, approved by the principal 2026-09-25 and amended 2026-09-25 (#288/#290/#291). Its decisions D1–D7, the evidence-integrity finding (§3), the work table (§4), the outline (§5) and the gates (§6) are restated where a task depends on them.

---

## Standing rules (apply to every task)

1. **Plain language in anything a reader sees** (paper, figures, evidence README): *pass* not drain, *task* not build unit, *setting work aside* not parking, *independent test* not sealed test, *worklist* not register. Code identifiers and file paths keep their names.
2. **Every run saves its exact config next to its output**: `git_sha`, `recorded_at` (UTC ISO-8601), `inputs_path` (absolute, as passed), `python`, package versions it imported, `model_id`/`revision`/`weights_sha256` where a model ran, `device`, `seed`. `paper/scripts/_provenance.py` (Task 0) is the one implementation; every script calls it.
3. **Evidence-location rule** (spec §4, #290): scripts that read the published run take `--inputs <absolute path>`; a missing or empty directory is an **error, exit 2, naming the path checked**. Never "unrecoverable" without a named path. The published run lives ONLY in the main checkout: `/Users/mo/github/personal/bioFM/projects/aviary-biosim/science/out/` (verified 2026-09-26: `seqs/` 10 files, `esm/results.json`, `discovery/discovery.json`). Never `cd` there.
4. **Labels** (spec §4): `measured` (re-run, dated), `reconstructed` (from version control), `reported` (from the published run, not re-derived), `documented` (a taxonomy row citing its source), `queried` (an external store answered on a date). A label is a field in the evidence file, not prose.
5. **Identifier constraint** (prospective, #324 wording): no new tracked file pairs a sequence identifier with a substance or organism name. Evidence records `sha256(identifier)`, never the identifier. Subagent prompts carry the #324 content block verbatim.
6. **Do not cite `.v2r/` in the main checkout** — it is the seeded fixture (spec §3). Task 3 handles the *worktree's* candidate record separately.
7. **Commit through `tools/git-safe-commit`** with `--work-item` per the CTO's assignment; stage explicit paths only; never `git add -A`. Boundary commits go through `/iteration-complete`.
8. **Not authorised** (spec §7, #272): new passes, CoreWeave runs, the lessons-pin fix, any venue deposit including sandbox, OpenAIRE, n8n workflow creation, edits to the three pre-existing identifier sites.

## File structure

```
paper/
  README.md                      what each evidence file is, its label, how it was produced
  claims.yaml                    every claim: id, value, label, source file:field, text
  claims.py                      the traceability check; emits claims.tex
  claims.tex                     GENERATED — one \newcommand per claim
  main.tex                       the draft (W1)
  refs.bib                       references
  publish.yml                    the publish manifest (P1)
  evidence/
    drain1-rerun.json            A1  measured
    drain1-from-git.csv          A2  reconstructed
    drain1-record-check.json     A2b candidate register-written record vs git
    science-input.json           A3a/b  fresh fetch vs published input (hashes only)
    science.json                 A3c measured re-run
    agent-run.json               A4  counts from the published discovery artifact
    weave-count.json             A4  queried trace counts
    taxonomy.csv                 A5  documented
    plugin-tests.json            A6  measured
  figures/
    make_figures.py              A8 — reads paper/evidence only
    *.pdf                        GENERATED
  scripts/
    _provenance.py               config block shared by every script
    sealed_suite_results.sh      A1 — the referee_command
    drain1_from_git.py           A2
    drain1_record_check.py       A2b
    science_input.py             A3a/b
    science_rerun.py             A3c
    agent_run.py                 A4
    taxonomy_check.py            A5
    plugin_tests.py              A6
  tests/
    test_claims.py               A7 unit tests
    test_scripts.py              evidence-location rule + provenance block tests
dashboard/
  seed_demo_run.py               MODIFY (B1)
  tests/test_seed_demo_run.py    NEW (B1)
.gitignore                       MODIFY: add .v2r-demo/, paper/.hf-cache/, paper/figures/*.pdf? (no — PDFs are tracked), paper/*.aux etc.
SUBMISSION.md                    MODIFY line 101 (seeder now writes .v2r-demo/)
```

---

### Task 0: Provenance block and the evidence README

**Files:**
- Create: `paper/scripts/_provenance.py`
- Create: `paper/README.md`
- Create: `paper/tests/test_scripts.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing test**

```python
# paper/tests/test_scripts.py
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "paper" / "scripts"))


def test_provenance_block_names_every_required_field():
    import _provenance as P
    blk = P.block(inputs_path="/nowhere", extra={"seed": 0})
    for k in ("git_sha", "recorded_at", "inputs_path", "python", "seed"):
        assert k in blk, k
    assert len(blk["git_sha"]) == 40
    assert blk["recorded_at"].endswith("Z")


def test_require_inputs_errors_on_missing_dir_and_names_the_path(tmp_path):
    import _provenance as P
    missing = tmp_path / "not-there"
    with __import__("pytest").raises(SystemExit) as e:
        P.require_inputs(missing)
    assert e.value.code == 2
    # the message must NAME the path checked
    assert str(missing) in str(e.value) or str(missing) in P.LAST_ERROR


def test_require_inputs_errors_on_empty_dir(tmp_path):
    import _provenance as P
    with __import__("pytest").raises(SystemExit) as e:
        P.require_inputs(tmp_path)
    assert e.value.code == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with pyyaml pytest paper/tests/test_scripts.py -q`
Expected: FAIL — `ModuleNotFoundError: _provenance`

- [ ] **Step 3: Write the implementation**

```python
# paper/scripts/_provenance.py
"""The config block every evidence script writes beside its numbers.

Standing rule: every run saves its exact config (git SHA, versions, seeds,
inputs path, timestamp) next to its output. Also implements the evidence-
location rule: a missing or empty --inputs directory is an ERROR (exit 2)
that names the path it checked — never a finding of "unrecoverable".
"""
from __future__ import annotations

import datetime as _dt
import importlib
import platform
import subprocess
import sys
from pathlib import Path

LAST_ERROR = ""


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def versions(*modules: str) -> dict:
    out = {}
    for m in modules:
        try:
            out[m] = getattr(importlib.import_module(m), "__version__", "unknown")
        except Exception as e:  # noqa: BLE001 — recorded, not hidden
            out[m] = f"not importable: {type(e).__name__}"
    return out


def block(inputs_path: str | Path | None, extra: dict | None = None,
          modules: tuple[str, ...] = ()) -> dict:
    b = {
        "git_sha": git_sha(),
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "inputs_path": str(inputs_path) if inputs_path is not None else None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": versions(*modules),
    }
    b.update(extra or {})
    return b


def require_inputs(path: str | Path) -> Path:
    """Evidence-location rule. Exit 2 with the path NAMED on missing/empty."""
    global LAST_ERROR
    p = Path(path)
    if not p.is_dir():
        LAST_ERROR = f"inputs directory does not exist: {p}"
    elif not any(p.iterdir()):
        LAST_ERROR = f"inputs directory is empty: {p}"
    else:
        return p
    print(f"ERROR: {LAST_ERROR}", file=sys.stderr)
    raise SystemExit(2)
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with pyyaml pytest paper/tests/test_scripts.py -q`
Expected: `3 passed`

- [ ] **Step 5: Write `paper/README.md`** — one table row per evidence file: file, task id, label, producing command, date column filled in by the task that produces it. Use plain language. Start it with the labels legend from Standing rule 4.

- [ ] **Step 6: Add to `.gitignore`**

```
# white paper — local caches and LaTeX build products; evidence and PDFs are tracked
.v2r-demo/
paper/.hf-cache/
paper/*.aux
paper/*.log
paper/*.out
paper/*.fls
paper/*.fdb_latexmk
paper/*.bbl
paper/*.blg
```

- [ ] **Step 7: Commit**

```bash
"$T/git-safe" add paper/scripts/_provenance.py paper/tests/test_scripts.py paper/README.md .gitignore
"$T/git-safe-commit" "paper: provenance block, evidence-location rule, evidence README" --work-item <id> --stage impl
```

---

### Task 1 (B1): The seeder refuses a live run-state directory

**Spec §3:** the seeder wrote a made-up 23-task, 3-pass fixture into the live `.v2r/`, over pass 1's real record. Fix: the seeder writes to a **separate** directory by default and **refuses** `.v2r` when anything is already there. This is itself a taxonomy row (Task 7).

**Files:**
- Modify: `dashboard/seed_demo_run.py:52-56` (target dir) and the `__main__` block
- Create: `dashboard/tests/test_seed_demo_run.py`
- Modify: `SUBMISSION.md:101`, `artifacts/dashboard.html:80` (the documented command)
- Modify: `dashboard/v2r_dashboard.py:30` — default path stays `.v2r`; add the `.v2r-demo` hint to the input's label only.

- [ ] **Step 1: Write the failing tests**

```python
# dashboard/tests/test_seed_demo_run.py
import importlib.util, sys
from pathlib import Path

import pytest

SEEDER = Path(__file__).resolve().parents[1] / "seed_demo_run.py"


def load():
    spec = importlib.util.spec_from_file_location("seed_demo_run", SEEDER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_default_target_is_a_separate_fixture_dir(tmp_path):
    m = load()
    assert m.main(tmp_path) == 0
    assert (tmp_path / ".v2r-demo" / "register.yaml").exists()
    assert not (tmp_path / ".v2r").exists(), "the seeder must never create the live dir"


def test_refuses_a_live_run_state_dir_and_writes_nothing(tmp_path, capsys):
    m = load()
    live = tmp_path / ".v2r"
    live.mkdir()
    (live / "register.yaml").write_text("version: 1\n")
    before = (live / "register.yaml").read_text()
    rc = m.main(tmp_path, target=".v2r")
    assert rc == 2
    assert (live / "register.yaml").read_text() == before
    assert not (live / "run-record-1.yaml").exists()
    assert ".v2r" in capsys.readouterr().err


def test_refuses_the_live_dir_even_when_empty(tmp_path):
    m = load()
    (tmp_path / ".v2r").mkdir()
    assert m.main(tmp_path, target=".v2r") == 2


def test_seeded_records_are_marked_as_fixture(tmp_path):
    import yaml
    m = load()
    m.main(tmp_path)
    rec = yaml.safe_load((tmp_path / ".v2r-demo" / "run-record-1.yaml").read_text())
    assert rec["produced_by"] == "dashboard/seed_demo_run.py (FIXTURE — not a run that happened)"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --with pytest --with pyyaml pytest dashboard/tests -q`
Expected: 4 failures (`main() got an unexpected keyword argument 'target'`, missing `.v2r-demo`, …)

- [ ] **Step 3: Implement**

Replace the `main` signature and its first lines, and the `__main__` block:

```python
LIVE_DIR = ".v2r"          # the loop's real run state — this script must never write it
DEFAULT_TARGET = ".v2r-demo"


def main(root: Path, target: str = DEFAULT_TARGET) -> int:
    v2r = root / target
    if v2r.name == LIVE_DIR or v2r.resolve() == (root / LIVE_DIR).resolve():
        # The live directory is evidence of a pass that happened. A fixture written
        # there is indistinguishable from a real record to every consumer, and it
        # once overwrote pass 1's own record. Refuse, whatever is or is not inside.
        print(f"refusing to write fixture data into the live run-state directory {v2r}; "
              f"use the default {DEFAULT_TARGET}/ or pass another --target", file=sys.stderr)
        return 2
    v2r.mkdir(parents=True, exist_ok=True)
    ceilings = {...}   # unchanged
    ...
```

In each `yaml.safe_dump` of a run record add the key
`"produced_by": "dashboard/seed_demo_run.py (FIXTURE — not a run that happened)"`.

`__main__`:

```python
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--target", default=DEFAULT_TARGET,
                    help=f"directory under ROOT to write (default {DEFAULT_TARGET}); {LIVE_DIR} is refused")
    a = ap.parse_args()
    sys.exit(main(Path(a.root), target=a.target))
```

- [ ] **Step 4: Run the tests** — Expected: `4 passed`. Then the full existing suites, unchanged: `uv run --with pytest --with pyyaml pytest .claude/skills/v2r-loop/scripts/tests -q` → `42 passed`.

- [ ] **Step 5: Update the documented commands** — `SUBMISSION.md:101` and `artifacts/dashboard.html:80`: the seeder now writes `.v2r-demo/`; the dashboard's path box must be pointed at it to see the fixture. Do not change any number on either page.

- [ ] **Step 6: Commit** — `paper: seeder writes .v2r-demo and refuses the live .v2r (B1)`.

---

### Task 2 (A1): Re-run the six independent tests through the referee

**Spec §4 A1:** check out the pass-end commit, run the six independent tests through `tools/referee`, record the verdicts → `paper/evidence/drain1-rerun.json` (+ referee receipt), label `measured (re-run, date)`.

**Dependency (CTO):** `tools/referee` resolves `tests.referee_command_aviary-biosim` then `tests.referee_command` from the parent `agency.yaml` (referee lines 253–264). Neither is set. The CTO must add, on the parent's `agency.yaml` (same precedent as `quality.test_command_aviary-biosim`, commit `114f771`):

```yaml
tests:
  referee_command_aviary-biosim: "sh paper/scripts/sealed_suite_results.sh"
```

No `agency.yaml` may be created in this repo (first-match shadowing — ruling #331/#341).

**Hook note:** the seal hook blocks read-shaped shell verbs against `tests/sealed` for this agent. This task never reads the tests: `git archive` extracts a commit's tree, `pytest` runs it, the referee reports coarse verdicts. Stated here so the CTO can object at the gate.

**Files:**
- Create: `paper/scripts/sealed_suite_results.sh`
- Create: `paper/evidence/drain1-rerun.json` (generated)

- [ ] **Step 1: Write the referee command**

```sh
#!/bin/sh
# paper/scripts/sealed_suite_results.sh — the tests.referee_command for this repo.
# Extracts the pass-end commit's demo/ tree (code + independent tests as they were
# when the pass closed), runs the suite there, and prints one RESULT line per test
# in the referee's contract. Nothing here prints assertion text.
set -eu
COMMIT="${DRAIN1_END_COMMIT:-2e00aa3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git archive "$COMMIT" demo | tar -x -C "$WORK"
( cd "$WORK" && uv run --with pytest --with pyyaml --with fhaviary \
    pytest demo/tests/sealed -q --junitxml junit.xml >/dev/null 2>&1 || true )
python3 - "$WORK/junit.xml" "$COMMIT" <<'PY'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
for tc in root.iter("testcase"):
    cat = tc.get("classname", "").split(".")[-1] + "/" + tc.get("name", "")
    if tc.find("failure") is not None or tc.find("error") is not None:
        print(f"RESULT fail {cat}")
    elif tc.find("skipped") is not None:
        print(f"RESULT skip {cat}")
    else:
        print(f"RESULT pass {cat}")
print(f"# archived commit {sys.argv[2]}")
PY
```

- [ ] **Step 2: Run the referee** (after the CTO confirms the config):

Run: `"$T/referee" run --sign > /tmp/referee.json; echo exit=$?`
Expected: JSON with `total` = the number of tests in the six files, `fail` = 0, `skip` = 0, and a receipt path. Read the exit code directly, never through a pipe (rule #313).

- [ ] **Step 3: Write the evidence file** — `paper/evidence/drain1-rerun.json`:

```json
{
  "label": "measured (re-run, <date>)",
  "archived_commit": "2e00aa3",
  "referee": <the JSON from Step 2, verbatim>,
  "receipt_path": "<from --sign>",
  "note": "Hash E on the receipt binds the CURRENT tree; the suite ran over the archived pass-end tree named above.",
  "provenance": <_provenance.block(inputs_path=None, extra={"referee_command": "sh paper/scripts/sealed_suite_results.sh"})>
}
```
Produce it with a five-line Python snippet in the task, not by hand; the snippet lives at `paper/scripts/record_referee.py`.

- [ ] **Step 4: Verify** — `python3 -c "import json;d=json.load(open('paper/evidence/drain1-rerun.json'));assert d['referee']['fail']==0 and d['referee']['skip']==0 and d['referee']['total']>0"`.

- [ ] **Step 5: Commit** — `paper: A1 — six independent tests re-run through the referee`.

---

### Task 3 (A2 + A2b): Reconstruct pass 1 from version control; check the candidate record

**Spec §4 A2:** `paper/evidence/drain1-from-git.csv` — unit, commit, independent-test path, statement, requirement — label `reconstructed`.

**A2b (new, found 2026-09-26):** this worktree's untracked `.v2r/` holds a 6-task record (`run-record-1.yaml`, 301 bytes, mtime 2026-09-13 11:48; `register.yaml` with a real `register_sha`, `instinct_pin: null`, 6 closed, 0 set aside) whose six `pre_claim_sha` values are all real commits. It predates the seeder and matches `docs/drain-1-notes.md` exactly. It may be the register-written record the spec calls lost. The check below establishes what can be established without reading the tests; the CTO decides the label.

**Files:**
- Create: `paper/scripts/drain1_from_git.py`, `paper/scripts/drain1_record_check.py`
- Create: `paper/evidence/drain1-from-git.csv`, `paper/evidence/drain1-record-check.json` (generated)

- [ ] **Step 1: Write the failing test** (in `paper/tests/test_scripts.py`)

```python
def test_drain1_from_git_finds_six_units_in_order():
    import drain1_from_git as D
    rows = D.rows(first="28af3c4", last="2e00aa3")
    assert [r["unit"] for r in rows] == [f"U-00{i}" for i in range(1, 7)]
    assert all(r["requirement"].startswith("R") for r in rows)
    assert all(r["sealed_test"].startswith("demo/tests/") for r in rows)
```

- [ ] **Step 2: Implement `drain1_from_git.py`**

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A2 — pass 1 reconstructed from version control. Label: reconstructed."""
import csv, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P

SUBJECT = re.compile(r"^(U-\d{3}) (.*) \(satisfies (R\d+)\)$")


def rows(first="28af3c4", last="2e00aa3"):
    log = subprocess.check_output(
        ["git", "log", "--reverse", "--format=%H%x1f%cI%x1f%s", f"{first}^..{last}"], text=True)
    out = []
    for line in log.strip().splitlines():
        sha, when, subj = line.split("\x1f")
        m = SUBJECT.match(subj)
        if not m:
            continue                      # skeleton / fix commits interleave; keep only closes
        unit, stmt, req = m.groups()
        n = unit[-3:].lstrip("0")
        tree = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", sha, "demo/tests"], text=True)
        test = next((p for p in tree.split() if p.endswith(f"test_u{unit[-3:]}.py")), "")
        out.append({"unit": unit, "requirement": req, "statement": stmt, "commit": sha[:7],
                    "committed_at": when, "sealed_test": test, "label": "reconstructed"})
    return out


def main():
    r = rows()
    out = Path("paper/evidence/drain1-from-git.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(r[0].keys()))
        w.writeheader(); w.writerows(r)
    Path("paper/evidence/drain1-from-git.provenance.json").write_text(
        json.dumps(P.block(inputs_path=None, extra={"rows": len(r), "range": "28af3c4^..2e00aa3"}), indent=2))
    print(f"wrote {out}: {len(r)} rows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Implement `drain1_record_check.py`** — takes `--record <path to .v2r dir>`; for each unit in `register.yaml` asserts `pre_claim_sha` == `git rev-parse <close_commit>^` where the close commit is found by unit id from `drain1_from_git.rows()`; computes sha256 of `run-record-1.yaml` and of `register.yaml`; records file mtimes; writes `paper/evidence/drain1-record-check.json` with `{"candidate": <abs path>, "units_checked": 6, "pre_claim_matches": n, "sealed_test_sha_checked": false, "reason": "the agent may not read the independent tests; digest check deferred to the referee or the CTO", "label": "candidate register-written record — pre-claim chain verified, digests not"}`. **Do not read the sealed tests.** Exit 2 with the path named if `--record` is missing.

- [ ] **Step 4: Run both** — Expected: CSV with 6 rows; check JSON with `pre_claim_matches: 6`.

- [ ] **Step 5: Commit** — `paper: A2 — pass 1 reconstructed from git; candidate record checked against the commit chain`.

---

### Task 4 (A3a/A3b): The science input, fetched fresh and compared by hash

**Spec §4 A3 (amended #288/#290):** fetch the record fresh from UniProt bypassing the cache; record release/version, length and sha256 of the sequence; compare to the sequence the published run used; report match/mismatch. **Identifier rule (Standing rule 5):** the evidence stores `sha256(accession)`, not the accession. The accession is read at runtime from the published input (`--inputs`), never typed into any tracked file. *Flagged for the gate: spec A3a literally says "record accession"; this plan records its hash.*

**Files:**
- Create: `paper/scripts/science_input.py`
- Create: `paper/evidence/science-input.json` (generated)
- Test: `paper/tests/test_scripts.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_science_input_errors_on_missing_inputs(tmp_path):
    import science_input as S
    with pytest.raises(SystemExit) as e:
        S.main(["--inputs", str(tmp_path / "absent"), "--out", str(tmp_path / "o.json")])
    assert e.value.code == 2


def test_science_input_compares_by_hash_without_storing_the_identifier(tmp_path, monkeypatch):
    import science_input as S
    inputs = tmp_path / "out"; (inputs / "seqs").mkdir(parents=True); (inputs / "esm").mkdir()
    # an INVENTED record shape; the identifier below is invented for this test and is not assigned to anything
    acc = "invented-record-1"   # not identifier-shaped on purpose
    (inputs / "seqs" / f"{acc}.json").write_text(json.dumps({"accession": acc, "sequence": "MAAAC", "length": 5}))
    (inputs / "esm" / "results.json").write_text(json.dumps({"human_sequence": "MAAAC"}))
    monkeypatch.setattr(S, "fetch_fresh", lambda a: {"sequence": "MAAAC", "release": "2026_04", "http_last_modified": "x"})
    out = tmp_path / "o.json"
    assert S.main(["--inputs", str(inputs), "--out", str(out)]) == 0
    d = json.loads(out.read_text())
    assert d["match"] is True
    assert acc not in out.read_text()
    assert d["published"]["sequence_sha256"] == d["fresh"]["sequence_sha256"]
```

- [ ] **Step 2: Implement**

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///
"""A3a/A3b — is the published run's input the record UniProt serves today?
Stores hashes, never the identifier (prospective identifier rule)."""
import argparse, hashlib, json, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P

H = lambda s: hashlib.sha256(s.encode()).hexdigest()


def fetch_fresh(accession: str) -> dict:
    r = requests.get(f"https://rest.uniprot.org/uniprotkb/{accession}.fasta",
                     timeout=30, allow_redirects=False, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    if not lines or not lines[0].startswith(">"):
        sys.exit(f"ERROR: unexpected FASTA body from UniProt ({len(r.text)} bytes)")
    seq = "".join(lines[1:])
    return {"sequence": seq, "release": r.headers.get("x-uniprot-release", ""),
            "release_date": r.headers.get("x-uniprot-release-date", ""),
            "http_last_modified": r.headers.get("last-modified", ""),
            "entry_version": lines[0].split("SV=")[-1].split()[0] if "SV=" in lines[0] else ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    inputs = P.require_inputs(a.inputs)
    res = json.loads((inputs / "esm" / "results.json").read_text())
    human = res["human_sequence"]
    rec = next((json.loads(p.read_text()) for p in (inputs / "seqs").glob("*.json")
                if json.loads(p.read_text()).get("sequence") == human), None)
    if rec is None:
        print(f"ERROR: no record under {inputs/'seqs'} carries the published human sequence", file=sys.stderr); return 2
    fresh = fetch_fresh(rec["accession"])
    out = {
        "label": "measured (fresh fetch, " + P.block(None)["recorded_at"][:10] + ")",
        "identifier_sha256": H(rec["accession"]),
        "published": {"length": len(human), "sequence_sha256": H(human)},
        "fresh": {"length": len(fresh["sequence"]), "sequence_sha256": H(fresh["sequence"]),
                  "release": fresh["release"], "release_date": fresh["release_date"],
                  "entry_version": fresh["entry_version"], "http_last_modified": fresh["http_last_modified"]},
        "match": H(human) == H(fresh["sequence"]),
        "provenance": P.block(inputs_path=inputs, modules=("requests",)),
    }
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(("MATCH" if out["match"] else "MISMATCH — flag the CTO before any prose"), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests, then the real thing**

Run: `uv run --with requests --with pytest paper/scripts/science_input.py --inputs /Users/mo/github/personal/bioFM/projects/aviary-biosim/science/out --out paper/evidence/science-input.json`
Expected: `MATCH paper/evidence/science-input.json`. **On MISMATCH: stop, report both hashes to the CTO, write no prose** (spec §4).

- [ ] **Step 4: Commit** — `paper: A3a/b — published input compared by hash to a fresh fetch`.

---

### Task 5 (A3c): Re-run the protein model over the hash-verified input — the torch task

**Authorised** by #291 inside this plan, with conditions: isolated environment, never global; record torch version, model id + revision, weights sha256; never commit weights. **Done-condition:** `paper/evidence/science.json` exists with every field in Step 3 and its `match` block filled; `paper/.hf-cache/` is gitignored and untracked; `git status` shows no weights.

**Files:**
- Create: `paper/scripts/science_rerun.py`
- Create: `paper/evidence/science.json` (generated)

- [ ] **Step 1: Isolated environment** — every invocation sets `HF_HOME=$PWD/paper/.hf-cache` (gitignored in Task 0) and uses `uv run --with torch --with transformers --with requests --with numpy` (uv's cache; nothing global). Record `uv --version`.

- [ ] **Step 2: Implement** — the script imports `science/esm_tool.py` and `science/run_experiment.py` by path, sets `torch.manual_seed(0)`, runs `run_experiment.main()` (it writes `science/out/esm/results.json` **in this worktree**, gitignored), then:

```python
weights = next((Path(os.environ["HF_HOME"]) / "hub").rglob("*.safetensors"))
snapshot_rev = weights.resolve().parent.name          # HF cache: .../snapshots/<revision>/model.safetensors
science = {
  "label": None,                                      # set below
  "model_id": E.MODEL_ID, "revision": snapshot_rev,
  "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
  "device": E.device(), "seed": 0,
  "headline": {"substitutions": len(res["substitutions"]),
               "cysteine_mean": round(mean(scores at res["cysteine_positions"]), 2),
               "other_mean": round(mean(scores elsewhere), 2),
               "c_peptide_controls": {str(p): round(v, 2) for p, v in controls(res)},   # positions only
               "runtime_s": res["runtime_s"]},
  "per_position_mean": [round(x, 4) for x in per_position_means(res)],   # 110 numbers for the figure
  "published": <same headline block computed from --inputs/esm/results.json>,
  "match": {k: science_headline[k] == published_headline[k] for k in headline keys},
  "provenance": P.block(inputs_path=inputs, modules=("torch", "transformers", "numpy"), extra={"uv": uv_version}),
}
science["label"] = "measured (re-run, <date>)" if all(science["match"].values()) else "MISMATCH — reported; see limitations"
```
`controls(res)` returns the three C-peptide positions named in `SUBMISSION.md` § Results and their scores; the positions come from `res["regions"]`, never typed in. No sequence string is written to the evidence file.

- [ ] **Step 3: Run**

Run: `HF_HOME=$PWD/paper/.hf-cache uv run --with torch --with transformers --with requests --with numpy paper/scripts/science_rerun.py --inputs /Users/mo/github/personal/bioFM/projects/aviary-biosim/science/out --out paper/evidence/science.json`
Expected: prints the four headline numbers and `match: all True`. On any `False`: report both values to the CTO **before any prose**; the paper labels the figure *reported* and the limitations section says why.

- [ ] **Step 4: Verify nothing heavy is tracked** — `git status --porcelain | grep -E 'hf-cache|safetensors'` → empty.

- [ ] **Step 5: Commit** — `paper: A3c — protein model re-run over the hash-verified input`.

---

### Task 6 (A4): The 66-measurement run — counts from the published artifact and the trace store

**Found 2026-09-26 (read-only lookup, authorised at #272 start by #291):** the artifact exists at `<main>/science/out/discovery/discovery.json` (29,650 bytes, mtime 2026-09-13 12:23, sha256 prefix `ed9b4e2f5f01f24a`): 66 audit-trail entries, 5 rounds, model `deepseek-ai/DeepSeek-V4-Pro-0813`. The Weave project `3m-m/Aviary-BioSim` holds 36 traces / 4 roots, of which **1 root** is `run_discovery`. So A4's answer is: **found**, both artifact and trace.

**Files:**
- Create: `paper/scripts/agent_run.py`
- Create: `paper/evidence/agent-run.json`, `paper/evidence/weave-count.json` (generated)

- [ ] **Step 1: Write the failing test** — a tmp `discovery/discovery.json` with an invented 3-entry audit trail and 2 rounds; assert the output has `measurements == 3`, `rounds == 2`, `completion_tokens_per_round` a list of 2, and that the file contains no key named `audit_trail` (counts only, no content).

- [ ] **Step 2: Implement** — `--inputs <abs>/science/out/discovery`; `P.require_inputs`; read the JSON; write `{"label": "reported (artifact counted, <date>)", "measurements": len(audit_trail), "rounds": len(rounds), "completion_tokens_per_round": [...], "completion_tokens_total": sum, "model": d["model"], "control_positions": sorted positions in audit entries matching the C-peptide positions from science.json, "artifact_sha256": ..., "artifact_mtime": ..., "provenance": P.block(...)}`.

- [ ] **Step 3: Record the trace count** — `paper/evidence/weave-count.json`: `{"label": "queried (<date>)", "project": "3m-m/Aviary-BioSim", "query": "count_weave_traces_tool op_name_contains=run_discovery", "total_count": <n>, "root_traces_count": <n>, "project_total": 36, "project_roots": 4, "recorded_at": ...}` — re-query on the day, do not copy today's numbers.

- [ ] **Step 4: Run + commit** — `paper: A4 — the discovery run counted from its artifact and its trace`.

---

### Task 7 (A5): The failure-mode taxonomy

**Spec §2 contribution 3, §4 A5:** every row — symptom, why it passed review, the regression test that now pins it (by path), a comp-bio analogue. Sources: aiadlc `CHANGELOG.md` 0.56–0.64 (`/Users/mo/github/aiadlc/CHANGELOG.md`), `docs/drain-1-notes.md`, `docs/deferred-findings.md`, and the pass-5 entry assigned in #285.

**Files:**
- Create: `paper/evidence/taxonomy.csv` (hand-authored rows, machine-checked)
- Create: `paper/scripts/taxonomy_check.py`

- [ ] **Step 1: Write the check** — reads the CSV; for each row with a `regression_test` path, asserts the file exists under this repo or under `--plugin-root`; a row with no test must say `documented, no test` in `label`; exits 1 listing failures. Columns: `id,symptom,why_it_passed_review,found_by,regression_test,label,comp_bio_analogue,source`.

- [ ] **Step 2: Author the rows** (minimum set; each cites its source line):

| id | symptom | source |
|---|---|---|
| T01 | The gate read exit 1 as "test failed" while the test never ran | `README.md` § The problem…; test `.claude/skills/v2r-loop/scripts/tests/test_register_gate.py` |
| T02 | Trace publish succeeded, printed a URL, returned zero to the query | `docs/drain-1-notes.md` § Stage 4; test `…/test_register_trace.py` |
| T03 | Lessons pin computed exactly, identifies nothing (tree SHA over a hook-rewritten store) | ADR-0003; plugin CHANGELOG 0.56 "Fixed (in the port)"; plugin `tests/register.test.sh` |
| T04 | Close commit swept hook churn into task commits (`git add -A`) | CHANGELOG 0.56; plugin `tests/register.test.sh` |
| T05 | `instinct capture` discarded a correction and reinforced the stale text | CHANGELOG 0.57 |
| T06 | Run records could not say whether a run happened; a seeded file was indistinguishable | CHANGELOG 0.57 (`verify-record`) |
| T07 | `verify-record` returned 1 (retry) for UNVERIFIED | CHANGELOG 0.59 |
| T08 | The hard task closed first try because the prompt named the answer; prompts unpinned | `docs/drain-1-notes.md` § The park that didn't happen — `documented, no test` |
| T09 | Two tasks untestable in isolation; a park would have been indistinguishable from an earned one | `docs/drain-1-notes.md` § Two decomposition defects |
| T10 | Test isolation depended on collection order (F08) | `docs/deferred-findings.md` F08; `science/tests/test_stub_isolation.py` |
| T11 | Five of the guard's own tests could not fail; two of three halves deletable with the suite green; the mutation gate credited any non-zero exit (pass 5, #285) | `docs/deferred-findings.md` F08 update; `science/tests/test_stub_isolation.py` |
| T12 | A pre-import name was a transitive dependency; a resolution change turned three tests red (A7b) | commit `bb9339c`; `science/tests/test_esm_tool_accession.py` |
| T13 | The demo seeder overwrote the live run state (B1) | spec §3; `dashboard/tests/test_seed_demo_run.py` |
| T14–T20 | the referee defects (spec: "7 in `tools/referee`") | CHANGELOG 0.61–0.64 — read and cite each |

Comp-bio analogue column: benchmark leakage (T10, T11), silent QC skip (T01, T07), unlogged model identity (T03, T06), a positive control that answers the question for you (T08), a fixture presented as data (T13). Fill every row.

- [ ] **Step 3: Run the check** — `uv run paper/scripts/taxonomy_check.py --plugin-root /Users/mo/github/aiadlc` → `ok: N rows, M with tests, K documented-only`.

- [ ] **Step 4: Commit** — `paper: A5 — failure-mode taxonomy, every row citing its test or saying it has none`.

---

### Task 8 (A6): Plugin suite counts at the cited version, re-run

**Spec §4 A6:** re-run, not copied. Plugin repo `/Users/mo/github/aiadlc`, tag `v0.64.0` (commit `e54bb44`). The relevant suites are `tests/register.test.sh`, `tests/referee-*.test.sh`, `tests/spend.test.sh` (bash; `tests_summary` from `tests/lib.sh`).

**Files:** Create `paper/scripts/plugin_tests.py`, `paper/evidence/plugin-tests.json` (generated)

- [ ] **Step 1: Read `tests/lib.sh`'s `tests_summary`** to learn the exact summary line format; write the parser against it (one regex, tested with a pasted example line in `test_scripts.py`).
- [ ] **Step 2: Scratch worktree, never the live checkout** — `git -C /Users/mo/github/aiadlc worktree add /tmp/aiadlc-v0.64.0 v0.64.0`; run each suite from inside it, capturing stdout+stderr and the exit code **directly**; `git -C /Users/mo/github/aiadlc worktree remove /tmp/aiadlc-v0.64.0` afterwards.
- [ ] **Step 3: Evidence** — `{"label": "measured (re-run, <date>)", "plugin_version": "0.64.0", "commit": "e54bb44", "suites": {"register.test.sh": {"passed": n, "failed": m, "exit": 0}, ...}, "provenance": ...}`.
- [ ] **Step 4: Commit** — `paper: A6 — plugin suites re-run at v0.64.0`.

---

### Task 9 (A7): The claims-traceability check — the entry condition for review

**Spec §4 A7:** `paper/claims.yaml` maps every number and claim to `file:field` + label; `paper/claims.py` fails on any unmapped number, missing file, value mismatch, or a *reported* claim phrased as *measured*. Design: the TeX carries **no literal numbers** — it uses `\claimX` macros that `claims.py` generates into `paper/claims.tex`; the checker then treats *any* bare digit run in `main.tex` outside an allow-list as unmapped.

**Files:**
- Create: `paper/claims.yaml`, `paper/claims.py`, `paper/tests/test_claims.py`

- [ ] **Step 1: Write the failing tests**

```python
# paper/tests/test_claims.py
import json, textwrap
from pathlib import Path
import pytest, yaml
import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claims as C


def setup(tmp_path, claims, tex, evidence):
    (tmp_path / "evidence").mkdir()
    for name, body in evidence.items():
        (tmp_path / "evidence" / name).write_text(json.dumps(body))
    (tmp_path / "claims.yaml").write_text(yaml.safe_dump({"claims": claims}))
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


def test_generates_macros(tmp_path):
    root = setup(tmp_path,
        [{"id": "subs", "value": 2090, "label": "reported", "source": "e.json:x", "text": "t"}],
        r"\claimsubs{}", {"e.json": {"x": 2090}})
    C.check(root); assert r"\newcommand{\claimsubs}{2,090}" in (root / "claims.tex").read_text()
```

- [ ] **Step 2: Implement `paper/claims.py`**

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""A7 — every number in the paper maps to a file:field under paper/evidence/ with a label.
Exit 1 on: an unmapped number in main.tex, a missing evidence file, a value mismatch,
or a claim labelled reported/reconstructed/documented phrased as measured."""
import json, re, sys
from pathlib import Path
import yaml

NUMBER = re.compile(r"(?<![\w\\{])-?\d[\d,]*(?:\.\d+)?(?![\w}])")
ALLOW_LINE = "% claims: ignore-line"
YEAR = re.compile(r"\b(19|20)\d{2}\b")
REF = re.compile(r"\\(ref|cite|label|eqref|S|section|input|includegraphics)\{[^}]*\}|(?:Fig|Table|Section|Eq)\.?~?\d+")
MEASURED_WORDS = re.compile(r"\b(measured|we measure|re-run|reran)\b", re.I)


def resolve(root: Path, source: str):
    file, _, field = source.partition(":")
    p = root / "evidence" / file
    if not p.exists():
        return None, f"missing file {p}"
    d = json.loads(p.read_text()) if p.suffix == ".json" else {"rows": p.read_text().count("\n") - 1}
    for k in field.split("."):
        if isinstance(d, list): d = d[int(k)]
        elif isinstance(d, dict) and k in d: d = d[k]
        else: return None, f"field {field} not in {file}"
    return d, None


def fmt(v):
    if isinstance(v, bool): return str(v)
    if isinstance(v, int): return f"{v:,}"
    if isinstance(v, float): return f"{v:,.2f}".replace("-", "\u2212")
    return str(v)


def check(root: Path) -> list[str]:
    errs, macros = [], []
    spec = yaml.safe_load((root / "claims.yaml").read_text()) or {}
    claims = spec.get("claims", [])
    tex = (root / "main.tex").read_text()
    for c in claims:
        v, err = resolve(root, c["source"])
        if err: errs.append(err); continue
        want = c["value"]
        if isinstance(want, float) or isinstance(v, float):
            ok = abs(float(v) - float(want)) < 1e-9
        else:
            ok = v == want
        if not ok: errs.append(f"mismatch {c['id']}: claims.yaml={want} evidence={v} ({c['source']})")
        macros.append(f"\\newcommand{{\\claim{c['id']}}}{{{fmt(want)}}}")
        if c["label"].split()[0] != "measured":
            for sent in re.split(r"(?<=[.!?])\s+", tex):
                if f"\\claim{c['id']}" in sent and MEASURED_WORDS.search(sent):
                    errs.append(f"reported claim phrased as measured: {c['id']} in: {sent.strip()[:80]}")
    (root / "claims.tex").write_text("% GENERATED by claims.py — do not edit\n" + "\n".join(macros) + "\n")
    for n, line in enumerate(tex.splitlines(), 1):
        if ALLOW_LINE in line: continue
        scrub = REF.sub("", YEAR.sub("", line))
        scrub = re.sub(r"\\claim[a-zA-Z0-9]+\{\}", "", scrub)
        for m in NUMBER.finditer(scrub):
            errs.append(f"unmapped number {m.group()!r} at main.tex:{n}")
    return errs


if __name__ == "__main__":
    e = check(Path(__file__).parent)
    print("\n".join(e) or "claims: ok")
    sys.exit(1 if e else 0)
```

- [ ] **Step 3: Run tests** — `uv run --with pytest --with pyyaml pytest paper/tests/test_claims.py -q` → `6 passed`.
- [ ] **Step 4: Author `claims.yaml`** — one entry per number the paper will carry (the four science headline figures, 66, 5 rounds, 42/265/75/36+1, 6 closed/0 set aside, taxonomy row count, plugin suite counts, trace counts), each with `source` pointing at the evidence written by Tasks 2–8 and the label the producing task assigned. `text` is the sentence fragment the claim supports.
- [ ] **Step 5: Commit** — `paper: A7 — claims-traceability check, the review's entry condition`.

---

### Task 10 (A8): Figures generated from `paper/evidence/` only

**Files:** Create `paper/figures/make_figures.py`; generated `paper/figures/{timeline,cysteines,taxonomy}.pdf`. The loop schematic is drawn in TikZ inside `main.tex` (it carries no data).

- [ ] **Step 1: Write the failing test** — `make_figures.py` refuses to run if any argument points outside `paper/evidence/` (assert `SystemExit` on `--evidence science/out`).
- [ ] **Step 2: Implement** with `matplotlib` (`uv run --with matplotlib`): `timeline.pdf` from `drain1-from-git.csv` (six tasks on a time axis, one glyph each, labelled by task id and requirement); `cysteines.pdf` from `science.json:per_position_mean` (110 bars; the six cysteine positions highlighted; two horizontal lines at the two means, labelled with `\claim` values in the caption, not in the plot); `taxonomy.pdf` from `taxonomy.csv` (rows × columns as a table figure, plain language). Every figure's footer text: `generated from paper/evidence/<file> at <git_sha[:7]>`.
- [ ] **Step 3: Run; commit** — `paper: A8 — figures from evidence only`.

---

### Task 11 (W1): The draft

**Spec §5 outline, D3 audience (ML-focused computational biologists), D4 spine (the loop as a lab method), D5 (self-improvement is mechanism, not result — not in the title or abstract), D2 (CoreWeave venue only), §3 finding in limitations, plain-language rule.**

**Files:** Create `paper/main.tex`, `paper/refs.bib`; generated `paper/main.pdf`.

- [ ] **Step 1: Skeleton with every section header from §5**, `\input{claims.tex}` in the preamble, and the D4 mapping table in §2:

| lab method | the loop |
|---|---|
| pre-registration | the spec: standing requirements, frozen at one approval |
| blinded assessment | the independent test, written by someone who never sees the implementation |
| the lab notebook | the pass record and the traces |
| a protocol amendment | a lesson, adopted only between passes |

- [ ] **Step 2: Write §1–§7 and the appendix** at the outline's grain, with `\claimX{}` for every figure and no bare numbers. §6 Limitations must contain, verbatim in substance: D5; the §3 evidence finding ("pass 1 is reconstructed from version control; the record the worklist wrote was lost" — **amend if Task 3's candidate record is accepted by the CTO**); MPS + serverless compute, CoreWeave as venue only; budget enforcement never run end to end; a single pass; lessons not yet shown to change an outcome; the cache-integrity finding under reproducibility (F31, no detail). §7 states what a second pass would need and executes nothing.
- [ ] **Step 3: Build** — `cd paper && uv run --with pyyaml claims.py && (latexmk -pdf main.tex || tectonic main.tex)`; `claims.py` must print `claims: ok` first.
- [ ] **Step 4: Commit** — `paper: W1 — draft`.

---

### Task 12 (P1): The publish manifest

**Spec D6/D7 + #422 item 2 + `research/PUBLICATION_PIPELINE_SPEC.md` §12.1 (template `scripts/publish/publish.yml.template` in bioFM; `topic` required with no default; project-relative artifact paths).** Author: `Matt Mo`, ORCID `0009-0009-5233-3142` (principal-supplied 2026-09-26). **Affiliation: `SUBMISSION.md` states none** — leave the key absent and flag; do not invent. Slack: `#research-approvals`. Zenodo **sandbox** is pre-approved once the pipeline exists; `enabled: false` on every venue until the principal's go — the manifest is prepared, nothing deposits.

**Files:** Create `paper/publish.yml`; test in `paper/tests/test_scripts.py`.

- [ ] **Step 1: Write the failing test** — loads the YAML; asserts `topic` present and non-empty; `authors[0].name == "Matt Mo"`, `authors[0].orcid` matches `^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$`; no value contains `YOUR_HANDLE`, `0000-0000`, `Family Given`, `TBD`; every `artifacts[].path` is project-relative (no leading `/`, no `..`) and exists after Task 11; every venue `enabled: false`.
- [ ] **Step 2: Author**

```yaml
# paper/publish.yml — per-project publish manifest (PUBLICATION_PIPELINE_SPEC.md §12.1)
topic: v2r-biosim-whitepaper            # required, no default: names the asset folder
title: "The build loop as a lab method: an agentic worklist with independent tests, and a protein-model experiment run under it"
description: |
  A white paper for ML-focused computational biologists: a build loop in which the
  agent that writes code cannot record that it passed, taught as a lab method, with
  a protein-language-model experiment as the worked example and a failure-mode
  taxonomy from auditing the loop's own trust core.
version: "0.1.0-draft"
license: "MIT"
related_url: "https://github.com/supmo668/Aviary-BioSim"
authors:
  - name: "Matt Mo"
    orcid: "0009-0009-5233-3142"
    # affiliation: not stated in SUBMISSION.md — principal to supply at the publish gate
keywords: ["agentic build loop", "independent tests", "protein language model", "reproducibility", "failure modes"]
artifacts:
  - path: "main.pdf"
    description: "White paper PDF"
  - path: "evidence/"
    description: "Every number in the paper, with its producing config"
  - path: "claims.yaml"
    description: "Claims-traceability map (auto-checked by claims.py)"
notify:
  slack_channel: "#research-approvals"
venues:
  zenodo:
    enabled: false                    # sandbox pre-approved once the pipeline (#203) exists; LIVE needs an explicit go
    sandbox: true
    upload_type: "publication"
    publication_type: "preprint"
    zenodo_license: "mit"
  figshare: { enabled: false }
  osf: { enabled: false }
manual:
  arxiv:
    prepared_only: true               # no API; a human uploads the bundle (spec §12.3)
    primary: "cs.LG"
    cross_list: ["q-bio.QM"]
```

- [ ] **Step 3: Run the test; commit** — `paper: P1 — publish manifest, prepared, nothing enabled`.

---

### Task 13: Boundary

- [ ] `/iteration-complete` over Tasks 0–12 (the gate runs the suites by hand and records them in the receipt: 42 register, 265 science, dashboard 4, paper tests; `claims.py` ok; `taxonomy_check.py` ok).
- [ ] `pr-submit` to the CTO with: receipt path, `paper/main.pdf`, the A3 match verdicts, the A2b candidate-record check, and the migration-debt line carried from the F08 gate. **The CTO's publication-rigour review starts only after `claims.py` passes** (spec §6 gate 2).

---

## Open at the plan gate (answers change tasks; none blocks Task 0–1)

| # | Question | Default if unanswered |
|---|---|---|
| G1 | A1 config: will the CTO set `tests.referee_command_aviary-biosim` on the parent `agency.yaml`? | A1 waits; Tasks 3–12 proceed |
| G2 | A3a: record `sha256(accession)` (this plan) or the accession itself (spec wording)? | hash |
| G3 | A2b: how to label the worktree's candidate record if the pre-claim chain verifies 6/6 and the digests cannot be checked by this agent? | "candidate, partially verified"; limitations say so |
| G4 | P1: the pipeline spec §13 records the principal's choice **(b) reimplement in n8n** (2026-09-24), while D7 says option (a). The manifest shape is identical (§12.1); which does the paper's §3 name as the publish path? | name neither; say "the repository's publication pipeline" |
| G5 | P1: author name — #422 says `Matt Mo`; `SUBMISSION.md` says `Mangyin Mo`. Affiliation is stated nowhere. | `Matt Mo`; affiliation absent |
| G6 | A1: is `git archive` + `pytest` inside the referee command acceptable under the seal rule for this agent? | yes — no test content reaches the agent |

## Self-review

- **Spec coverage:** B1 → Task 1; A1 → 2; A2 → 3; A3a/b → 4; A3c → 5; A4 → 6; A5 → 7; A6 → 8; A7 → 9; A8 → 10; W1 → 11; P1 → 12; §6 gate 1 → 13. Evidence-location rule → Task 0 (`require_inputs`) used by 4, 5, 6. Config-recording rule → Task 0 (`block`) used everywhere. §3 finding → Tasks 1, 3, 11. D5 → Task 11 §6. Out-of-scope list → Standing rule 8.
- **Placeholders:** Task 5's `controls(res)` and `per_position_means(res)` are named helpers whose bodies read `res["regions"]` / `res["per_position"]` from the published schema (keys verified 2026-09-26: `cysteine_positions`, `regions`, `per_position`, `substitutions`, `summary`); write them in Task 5 Step 2 against that schema. Task 8 Step 1 deliberately reads the summary format before writing the parser.
- **Consistency:** `_provenance.block` / `require_inputs` names are the same in Tasks 0, 3, 4, 5, 6; `\claim<id>` in Tasks 9, 10, 11; `.v2r-demo` in Tasks 0, 1.
