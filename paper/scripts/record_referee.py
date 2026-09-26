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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

REFEREE_COMMAND = "sh paper/scripts/sealed_suite_results.sh"


def coarse_from(stdout: str):
    """The referee prints its coarse JSON as the last stdout line; None if it did not."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--referee", required=True, help="path to tools/referee")
    ap.add_argument("--commit", default="2e00aa3")
    ap.add_argument("--out", default="paper/evidence/drain1-rerun.json")
    ap.add_argument("--sign", action="store_true")
    a = ap.parse_args(argv)
    cmd = [a.referee, "run"] + (["--sign"] if a.sign else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    coarse = coarse_from(r.stdout)
    ran = coarse is not None and int(coarse.get("total", 0)) > 0
    clean = ran and int(coarse.get("failed", 0)) == 0 and int(coarse.get("skipped", 0)) == 0
    prov = P.block(inputs_path=None, extra={"referee_command": REFEREE_COMMAND, "referee_argv": cmd})
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
        "note": ("Hash E on the referee's receipt binds the CURRENT tree; the suite ran over the "
                 "archived pass-end tree named above."),
        "provenance": prov,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(label, a.out)
    return 0 if clean and r.returncode == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
