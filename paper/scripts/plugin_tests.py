#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A6 — the plugin's own suites at the cited version, RE-RUN, not copied.

Checks out the tag in a scratch git worktree of the plugin repository (never its live
checkout), runs each named suite there capturing stdout+stderr and the exit code
directly, parses the suite's own summary line (`<n> run, <m> failed`, printed by
tests/lib.sh's tests_summary), and removes the worktree. Label: measured (re-run).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

SUMMARY = re.compile(r"^(\d+) run, (\d+) failed$", re.M)
DEFAULT_SUITES = ["register.test.sh", "referee-accountability.test.sh", "referee-command-permodule.test.sh",
                  "referee-injection.test.sh", "referee-skip.test.sh", "spend.test.sh", "v2r-loop.test.sh"]


def parse_summary(text: str):
    """The LAST summary line wins; None if the suite printed none (it did not finish)."""
    found = SUMMARY.findall(text)
    return (int(found[-1][0]), int(found[-1][1])) if found else None


def run_suite(worktree: Path, name: str) -> dict:
    r = subprocess.run(["bash", f"tests/{name}"], cwd=worktree, capture_output=True, text=True, timeout=1800)
    parsed = parse_summary(r.stdout + r.stderr)
    return {"run": parsed[0] if parsed else None, "failed": parsed[1] if parsed else None,
            "exit": r.returncode, "summary_found": parsed is not None,
            "passed": (parsed[0] - parsed[1]) if parsed else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-repo", required=True, help="ABSOLUTE path to the plugin git repository")
    ap.add_argument("--tag", default="v0.64.0")
    ap.add_argument("--suites", nargs="*", default=DEFAULT_SUITES)
    ap.add_argument("--out", default="paper/evidence/plugin-tests.json")
    a = ap.parse_args(argv)
    repo = P.require_inputs(a.plugin_repo)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--short", a.tag], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="plugin-suites-") as tmp:
        wt = Path(tmp) / a.tag
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), a.tag],
                       check=True, capture_output=True, text=True)
        try:
            suites = {name: run_suite(wt, name) for name in a.suites}
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                           capture_output=True, text=True)
    all_green = all(s["summary_found"] and s["failed"] == 0 and s["exit"] == 0 for s in suites.values())
    out = {
        "label": ("measured (re-run, " + P.block(None)["recorded_at"][:10] + ")") if all_green
                 else "NOT GREEN — see suites",
        "plugin_version": a.tag.lstrip("v"), "commit": commit,
        "suites": suites,
        "totals": {"run": sum(s["run"] or 0 for s in suites.values()),
                   "failed": sum(s["failed"] or 0 for s in suites.values())},
        "provenance": P.block(inputs_path=repo, extra={"tag": a.tag, "scratch_worktree": True}),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(out["label"], out["totals"], a.out)
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
