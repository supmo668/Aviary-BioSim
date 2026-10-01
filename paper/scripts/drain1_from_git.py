#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A2 — pass 1 reconstructed from version control. Label: reconstructed.

Every task the first pass closed left a commit whose subject is
`U-NNN <statement> (satisfies RN)`. Skeleton and coordination commits interleave; only
the close commits are kept. The independent test's path is read from the tree at the
close commit by NAME only — nothing here reads a test's content.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

SUBJECT = re.compile(r"^(U-\d{3}) (.*) \(satisfies (R\d+)\)$")
FIRST, LAST = "28af3c4", "2e00aa3"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, cwd=P.REPO)


def rows(first: str = FIRST, last: str = LAST) -> list[dict]:
    log = _git("log", "--reverse", "--format=%H%x1f%cI%x1f%s", f"{first}^..{last}")
    out = []
    for line in log.strip().splitlines():
        sha, when, subj = line.split("\x1f")
        m = SUBJECT.match(subj)
        if not m:
            continue                      # skeleton / fix commits interleave; keep only closes
        unit, stmt, req = m.groups()
        tree = _git("ls-tree", "-r", "--name-only", sha, "demo/tests")
        suffix = f"test_u{unit[-3:]}.py"
        test = next((p for p in tree.split() if p.endswith(suffix)), "")
        out.append({"unit": unit, "requirement": req, "statement": stmt, "commit": sha[:7],
                    "parent": _git("rev-parse", f"{sha}^").strip(),
                    "committed_at": when, "sealed_test": test, "label": "reconstructed"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=P.evidence("drain1-from-git.csv"))
    ap.add_argument("--first", default=FIRST)
    ap.add_argument("--last", default=LAST)
    a = ap.parse_args(argv)
    r = rows(a.first, a.last)
    if not r:
        print(f"ERROR: no close commits matched in {a.first}^..{a.last}", file=sys.stderr)
        return 2
    blank = [x["unit"] for x in r if not x["sealed_test"]]
    if blank:
        print(f"ERROR: no sealed_test found for {', '.join(blank)} — the reconstruction "
              "failed; nothing written", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(r[0].keys()))
        w.writeheader()
        w.writerows(r)
    prov = P.block(inputs_path=None, extra={"rows": len(r), "range": f"{a.first}^..{a.last}",
                                             "label": "reconstructed"})
    out.with_suffix(".provenance.json").write_text(json.dumps(prov, indent=2))
    print(f"wrote {out}: {len(r)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
