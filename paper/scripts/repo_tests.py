#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""The repository's own suites and its mutation gate, re-run and counted. Label: measured.

Runs each suite with the invocation the repository documents, reads pytest's own summary
line, and (unless --no-mutants) runs the frozen mutant catalogue and parses its final
count line. Exit codes are read directly. Nothing is copied from a document.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# No bytecode. Importing a sibling writes a .pyc whose co_filename is this machine's
# absolute path, and that file is gitignored, so review and every payload scan are blind
# to it. One such file reached a declared artifact directory once.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCI = ["uv", "run", "--with", "pytest", "--with", "pyyaml", "--with", "fhaviary", "--with", "openai",
       "--with", "weave", "--with", "requests", "python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
REG = ["uv", "run", "--with", "pytest", "--with", "pyyaml", "python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
PAPER = ["uv", "run", "--with", "pytest", "--with", "pyyaml", "--with", "requests", "--with", "matplotlib",
         "python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
SUITES = {
    "science/tests": SCI + ["science/tests"],
    ".claude/skills/v2r-loop/scripts/tests": REG + [".claude/skills/v2r-loop/scripts/tests"],
    "dashboard/tests": REG + ["dashboard/tests"],
    # uv's --with flags go BEFORE `python`; an earlier form put one after `-m pytest`, so
    # pytest received it, exited 4, and the runner recorded no count — which is the right
    # behaviour for the runner and the wrong invocation for the suite.
    "paper/tests": PAPER + ["paper/tests"],
    # The publication pipeline's decision logic. It is JavaScript because it runs in n8n
    # Code nodes, so it needs node rather than pytest -- but it decides what reaches a
    # public DOI, which makes it exactly the code that must not be the untested kind.
    "orchestration/n8n/nodes": ["node", "--test", "orchestration/n8n/nodes/pipeline.test.mjs"],
}
# Two runners, two output dialects. pytest says "23 passed"; node's test runner says
# "pass 23". Matching only pytest's form made node's suite parse as passed=None, which the
# green check reads as NOT green — a suite that ran clean would be reported as a failure.
# A counter that cannot read its own runner is the same shape as a count nobody earned.
# `\bpass (\d+)` cannot false-match pytest's "163 passed": there, "pass" is followed by
# "ed", not by a space and digits. Anchoring on the line start was tried and does not work —
# node prefixes its summary with a non-ASCII glyph that `\W` declines to match.
PYTEST_SUMMARY = re.compile(r"(\d+) passed|\bpass (\d+)\b", re.M)
FAILED = re.compile(r"(\d+) failed|\bfail (\d+)\b", re.M)
MUTANT_SUMMARY = re.compile(r"(\d+)/(\d+) live mutants killed; (\d+) retired")


def _count(pattern: "re.Pattern", out: str):
    """The last count the output reports, from whichever dialect matched."""
    hits = [g for m in pattern.finditer(out) for g in m.groups() if g is not None]
    return int(hits[-1]) if hits else None


def run(cmd: list[str]) -> dict:
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=3600)
    out = r.stdout + r.stderr
    failed = _count(FAILED, out)
    return {"passed": _count(PYTEST_SUMMARY, out),
            "failed": failed if failed is not None else 0,
            "exit": r.returncode}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=P.evidence("repo-tests.json"))
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="record tree_clean false instead of refusing (A7-2)")
    a = ap.parse_args(argv)
    # A7-2: the recorded git_sha only identifies the producing code on a clean tree.
    P.require_clean_tree(allow_dirty=a.allow_dirty_tree)
    suites = {name: run(cmd) for name, cmd in SUITES.items()}
    mutants = None
    if not a.no_mutants:
        cmd = ["uv", "run", "--with", "pytest", "--with", "pyyaml", "--with", "fhaviary", "--with", "openai",
               "--with", "weave", "--with", "requests", "python", "-B", "science/tests/mutants/run_mutants.py"]
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=7200)
        m = MUTANT_SUMMARY.findall(r.stdout + r.stderr)
        mutants = {"killed": int(m[-1][0]) if m else None, "live": int(m[-1][1]) if m else None,
                   "retired": int(m[-1][2]) if m else None, "exit": r.returncode}
    # A sweep whose count line did not parse has killed = live = None, and None == None
    # read as a full kill (QG F11): the count must exist before it can be compared.
    green = all(s["exit"] == 0 and s["passed"] and s["failed"] == 0 for s in suites.values()) and \
            (mutants is None or (mutants["exit"] == 0 and mutants["killed"] is not None
                                 and mutants["killed"] == mutants["live"]))
    out = {
        "label": ("measured (re-run, " + P.block(None)["recorded_at"][:10] + ")") if green else "NOT GREEN — see suites",
        "suites": suites,
        "total_passed": sum(s["passed"] or 0 for s in suites.values()),
        "mutants": mutants,
        "provenance": P.block(inputs_path=None),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(out["label"], {k: v["passed"] for k, v in suites.items()}, mutants)
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
