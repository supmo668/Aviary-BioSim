#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A1 — run the referee over the pass-end commit and record its verdict with provenance.

Writes paper/evidence/drain1-rerun.json. The label is `measured (re-run, <date>)` ONLY
when the referee produced a verdict with results and no failures; anything else — the
command could not run, no results arrived, a failure — is recorded as NOT MEASURED with
the referee's own words, and this script exits 2 so no caller can mistake it for a pass.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

REFEREE_COMMAND = "sh paper/scripts/sealed_suite_results.sh"


def coarse_from(stdout: str):
    """The referee's coarse JSON: the first stdout line that parses as an object with a
    `total` key. With --sign the referee prints further lines after it, so 'the last
    line' was wrong and read a signed, passing run as 'no results' — safe, but false."""
    for ln in stdout.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and "total" in d:
            return d
    return None


def _count(coarse: dict, key: str) -> int:
    """A verdict count; a missing field is 0, a null one is -1 so it can never read as
    clean (`int(None)` was a TypeError and no evidence file got written)."""
    v = coarse.get(key, 0)
    return -1 if v is None else int(v)


def receipt_hash_from(text: str):
    """The Hash E the referee reports when it signs, or None."""
    import re
    m = re.search(r"signed sealed-suite receipt \(Hash E ([0-9a-f]+)\)", text)
    return m.group(1) if m else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--referee", required=True, help="path to tools/referee")
    ap.add_argument("--commit", default="2e00aa3")
    ap.add_argument("--out", default=P.evidence("drain1-rerun.json"))
    ap.add_argument("--sign", action="store_true")
    a = ap.parse_args(argv)
    if not Path(a.referee).is_file():
        # Named error, exit 2 — not a FileNotFoundError traceback out of subprocess (QG F13).
        print(f"ERROR: --referee {a.referee} does not exist", file=sys.stderr)
        return 2
    cmd = [a.referee, "run"] + (["--sign"] if a.sign else [])
    # The suite runs over the commit this evidence names: the referee command reads
    # DRAIN1_END_COMMIT, so --commit is passed through rather than merely recorded (QG Q19).
    env = {**os.environ, "DRAIN1_END_COMMIT": a.commit}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    coarse = coarse_from(r.stdout)
    ran = coarse is not None and _count(coarse, "total") > 0
    # Every field the referee's coarse verdict carries must be clean: a failure, a skip,
    # a result the PLAN did not account for, or a PLAN error — any one of them, even
    # with exit 0, is not a passing verdict (QG F09).
    clean = (ran and _count(coarse, "failed") == 0 and _count(coarse, "skipped") == 0
             and _count(coarse, "unaccounted") == 0 and not coarse.get("plan_error"))
    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, cwd=P.REPO).stdout.strip()
    prov = P.block(inputs_path=None, extra={
        "referee_command": REFEREE_COMMAND, "referee_argv": cmd,
        # The referee resolves the command from the tree it is run in: record where.
        "cwd": str(Path.cwd()), "branch": branch,
        "archived_commit_env": env["DRAIN1_END_COMMIT"],
    })
    if clean and r.returncode == 0:
        label = f"measured (re-run, {prov['recorded_at'][:10]})"
    else:
        label = "NOT MEASURED — the referee did not produce a passing verdict"
    out = {
        "label": label,
        "archived_commit": a.commit,
        "referee_exit": r.returncode,
        "referee": coarse,
        "referee_stderr_tail": r.stderr[-2000:],
        "referee_receipt_hash_e": receipt_hash_from(r.stdout + r.stderr),
        "note": ("Hash E on the referee's receipt binds the CURRENT tree; the suite ran over the "
                 "archived pass-end tree named above."),
        "provenance": prov,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out = P.redact(out)                  # the referee's own output names paths too (QG F06)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(label, a.out)
    return 0 if clean and r.returncode == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
