#!/usr/bin/env python3
"""Apply every frozen mutant to a throwaway copy of the tree and require it to die.

Usage:  uv run --with pytest --with pyyaml --with fhaviary --with openai --with weave \
            --with requests python science/tests/mutants/run_mutants.py [--only <id> ...]

`--with requests` is not optional: conftest pre-imports requests as a DECLARED dependency
and its baseline test goes red without it, which turns every mutant into BROKEN-CHECK.

Exit 0 only if EVERY mutant is killed. A survivor means the property that mutant
probes is no longer pinned by any test — which is exactly the state three review
passes kept finding, and the reason this runner exists.

This is the acceptance gate for simplifying the guard: the minimum guard that still
kills all of these. Never run against the working tree; each mutant gets its own
copy under a temp directory, and the tree is never written to.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalogue import MUTANTS, RETIRED  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUBTREES = ("science", "demo")


# The anti-rot test is a SPEC-rot detector, not a behavioural one: applying a mutant
# drives its own `find` count to 0, so any check that collects it kills every mutant
# regardless of whether behaviour changed. Never let it into a check.
ALWAYS = ["--ignore=science/tests/test_mutant_catalogue.py"]

KILL_SUMMARY = re.compile(r"\b\d+ (failed|error)")


def _ignore(dirpath, names):
    """Exclude the sealed referee tree by BASENAME at the right directory.

    shutil.ignore_patterns fnmatches basenames, so the "tests/sealed" pattern this
    replaced matched nothing and the sealed tree was copied into all 31 temp trees.
    Nothing collected it and the temp root is 0700, so no seal was broken — but
    commit b7d1e82's body claimed an exclusion that never happened.
    """
    drop = {n for n in names if n in ("__pycache__", "out")}
    if Path(dirpath).name == "tests":
        drop |= {n for n in names if n == "sealed"}
    return drop


def _copy_tree(root: Path) -> None:
    for sub in SUBTREES:
        shutil.copytree(REPO / sub, root / sub, ignore=_ignore)
    leaked = list((root / "demo" / "tests").glob("sealed"))
    if leaked:
        raise SystemExit("refusing to run: the sealed tree reached the scratch copy")


def _pytest(root: Path, check: str):
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", check, "-q",
         "-p", "no:cacheprovider", *ALWAYS],
        cwd=root, capture_output=True, text=True,
    )


_BASELINE_OK: dict = {}


def _baseline_is_green(check: str) -> bool:
    """An unmutated copy must pass before any mutant against it can be credited.

    Without this a mutant is credited for a failure it did not cause — a renamed check
    file, a broken fixture, an unrelated red test all read as 'killed'.
    """
    if check not in _BASELINE_OK:
        with tempfile.TemporaryDirectory(prefix="mutant-baseline-") as tmp:
            root = Path(tmp)
            _copy_tree(root)
            _BASELINE_OK[check] = _pytest(root, check).returncode == 0
    return _BASELINE_OK[check]


def run_one(mutant, keep_going=True):
    check = mutant["check"]
    if not (REPO / check.split("::")[0]).exists():
        return "BROKEN-CHECK", f"{check} does not exist"
    if not _baseline_is_green(check):
        return "BROKEN-CHECK", f"{check} is not green BEFORE mutation; a kill would prove nothing"

    with tempfile.TemporaryDirectory(prefix=f"mutant-{mutant['id']}-") as tmp:
        root = Path(tmp)
        _copy_tree(root)
        target = root / mutant["target"]
        source = target.read_text()
        occurrences = source.count(mutant["find"])
        if occurrences != 1:
            return "CATALOGUE-STALE", f"find string occurs {occurrences}x in {mutant['target']}"
        target.write_text(source.replace(mutant["find"], mutant["replace"], 1))

        completed = _pytest(root, check)
        out = completed.stdout + completed.stderr
        if completed.returncode == 0:
            tail = completed.stdout.strip().splitlines()[-1:] or [""]
            return "SURVIVED", tail[0]
        # pytest exits 1 for test failures, 2 interrupted, 3 internal, 4 usage,
        # 5 no-tests-collected. Only 1 with a failure summary is evidence that a TEST
        # noticed the mutation; the rest mean the run never got that far.
        if completed.returncode != 1 or not KILL_SUMMARY.search(out):
            return "BROKEN-CHECK", f"exit {completed.returncode}, no failure summary"
        killers = sorted({ln.split(" ")[1].split("::")[-1]
                          for ln in out.splitlines()
                          if ln.startswith(("FAILED ", "ERROR "))})
        return "killed", f"killed by {len(killers)}: {', '.join(killers[:4])}" + \
                         ("…" if len(killers) > 4 else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    selected = [m for m in MUTANTS if not args.only or m["id"] in args.only]

    survivors, stale, broken = [], [], []
    for mutant in selected:
        status, detail = run_one(mutant)
        mark = {"killed": "  killed", "SURVIVED": "SURVIVED",
                "CATALOGUE-STALE": "   STALE", "BROKEN-CHECK": "  BROKEN"}[status]
        print(f"{mark}  {mutant['id']:34} {mutant['why']}")
        if detail:
            print(f"           {detail}")
        if status == "SURVIVED":
            survivors.append(mutant["id"])
        elif status == "CATALOGUE-STALE":
            stale.append(mutant["id"])
        elif status == "BROKEN-CHECK":
            broken.append(mutant["id"])

    killed = len(selected) - len(survivors) - len(stale) - len(broken)
    print(f"\n{killed}/{len(selected)} live mutants killed; {len(RETIRED)} retired")
    for entry in RETIRED:
        print(f"  retired  {entry['id']:34} {entry['why_retired'].splitlines()[0]}")
    if stale:
        print(f"STALE (the code moved; fix the catalogue): {', '.join(stale)}")
    if broken:
        print(f"BROKEN-CHECK (a kill here would prove nothing): {', '.join(broken)}")
    if survivors:
        print(f"SURVIVED (the property is no longer pinned): {', '.join(survivors)}")
    return 1 if (survivors or stale or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
