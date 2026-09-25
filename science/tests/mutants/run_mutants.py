#!/usr/bin/env python3
"""Apply every frozen mutant to a throwaway copy of the tree and require it to die.

Usage:  uv run --with pytest --with pyyaml --with fhaviary --with openai --with weave \
            python science/tests/mutants/run_mutants.py [--only <id> ...]

Exit 0 only if EVERY mutant is killed. A survivor means the property that mutant
probes is no longer pinned by any test — which is exactly the state three review
passes kept finding, and the reason this runner exists.

This is the acceptance gate for simplifying the guard: the minimum guard that still
kills all of these. Never run against the working tree; each mutant gets its own
copy under a temp directory, and the tree is never written to.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalogue import MUTANTS  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUBTREES = ("science", "demo")


def run_one(mutant, keep_going=True):
    with tempfile.TemporaryDirectory(prefix=f"mutant-{mutant['id']}-") as tmp:
        root = Path(tmp)
        for sub in SUBTREES:
            shutil.copytree(REPO / sub, root / sub,
                            ignore=shutil.ignore_patterns("__pycache__", "out", "tests/sealed"))
        target = root / mutant["target"]
        source = target.read_text()
        occurrences = source.count(mutant["find"])
        if occurrences != 1:
            return "CATALOGUE-STALE", f"find string occurs {occurrences}x in {mutant['target']}"
        target.write_text(source.replace(mutant["find"], mutant["replace"], 1))

        completed = subprocess.run(
            [sys.executable, "-B", "-m", "pytest", mutant["check"], "-q",
             "-p", "no:cacheprovider", "-x"],
            cwd=root, capture_output=True, text=True,
        )
        if completed.returncode == 0:
            tail = completed.stdout.strip().splitlines()[-1:] or [""]
            return "SURVIVED", tail[0]
        return "killed", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    selected = [m for m in MUTANTS if not args.only or m["id"] in args.only]

    survivors, stale = [], []
    for mutant in selected:
        status, detail = run_one(mutant)
        mark = {"killed": "  killed", "SURVIVED": "SURVIVED", "CATALOGUE-STALE": "   STALE"}[status]
        print(f"{mark}  {mutant['id']:34} {mutant['why']}")
        if detail:
            print(f"           {detail}")
        if status == "SURVIVED":
            survivors.append(mutant["id"])
        elif status == "CATALOGUE-STALE":
            stale.append(mutant["id"])

    print(f"\n{len(selected) - len(survivors) - len(stale)}/{len(selected)} killed")
    if stale:
        print(f"STALE (the code moved; fix the catalogue): {', '.join(stale)}")
    if survivors:
        print(f"SURVIVED (the property is no longer pinned): {', '.join(survivors)}")
    return 1 if (survivors or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
