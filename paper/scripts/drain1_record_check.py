#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""A2b — what can be established about a recovered pass-1 record, and what cannot.

A 6-task record (`register.yaml`, `run-record-1.yaml`) was found, untracked, in a
worktree. This script records, for each task, whether the record's `pre_claim_sha` is
exactly the parent of that task's close commit (a consistency check against history);
runs the register tool's own `verify-record` on the run record and reports its exit code
as an INTERNAL-consistency result only (the register is the artifact under study, so it
cannot certify its own evidence, and the same tool writing the same record later would
pass too); records the files' digests and mtimes; copies them beside this evidence; and
states plainly that `register_sha` is PERMANENTLY unverifiable — the run-state directory
was never tracked, so the drain-start register was never committed by anyone.

It does NOT read the independent tests and does NOT check `sealed_test_sha`: that check
belongs to the referee or the coordinator, never to the agent under the seal.

Label (coordinator's ruling, 2026-09-26): "recovered record; pre-claim chain verified
N/6; write-time provenance not established".
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402
import drain1_from_git as D  # noqa: E402

DEFAULT_REGISTER = "/Users/mo/.claude/plugins/cache/aiadlc-plugins/aiadlc/0.69.0/tools/register"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()


def run_state_ever_tracked(dirname: str = ".v2r") -> bool:
    log = subprocess.run(["git", "log", "--all", "--oneline", "--", f"{dirname}/"],
                         capture_output=True, text=True).stdout.strip()
    return bool(log)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True, help="ABSOLUTE path to the recovered .v2r directory")
    ap.add_argument("--register", default=DEFAULT_REGISTER, help="the register tool with verify-record")
    ap.add_argument("--out", default="paper/evidence/drain1-record-check.json")
    ap.add_argument("--copy-to", default="paper/evidence/candidate-record")
    ap.add_argument("--first", default=D.FIRST)
    ap.add_argument("--last", default=D.LAST)
    a = ap.parse_args(argv)

    record = P.require_inputs(a.record)          # exit 2, naming the path, if missing/empty
    reg_file, run_file = record / "register.yaml", record / "run-record-1.yaml"
    for f in (reg_file, run_file):
        if not f.exists():
            print(f"ERROR: {f} does not exist", file=sys.stderr)
            return 2

    reg = yaml.safe_load(reg_file.read_text())
    run = yaml.safe_load(run_file.read_text())
    by_unit = {r["unit"]: r for r in D.rows(a.first, a.last)}
    units = []
    for u in reg.get("units", []):
        row = by_unit.get(u["id"])
        units.append({
            "unit": u["id"], "state": u.get("state"), "attempts": u.get("attempts"),
            "close_commit": row["commit"] if row else None,
            "pre_claim_sha_is_parent_of_close": bool(row and u.get("pre_claim_sha") == row["parent"]),
            "sealed_test_sha_checked": False,
        })
    matches = sum(1 for x in units if x["pre_claim_sha_is_parent_of_close"])

    verify = {"tool": a.register, "ran": False, "exit": None, "output_tail": ""}
    if a.register and Path(a.register).exists():
        r = subprocess.run([a.register, "verify-record", str(run_file)], capture_output=True, text=True)
        verify.update(ran=True, exit=r.returncode, output_tail=(r.stdout + r.stderr)[-600:])
    verify["meaning"] = ("exit 0: the record carries the register's provenance stamp and its digest "
                         "matches; exit 3: UNVERIFIED — which the tool itself defines as 'predates "
                         "provenance, or something else wrote it', NOT as forged. A record from the "
                         "first pass predates the stamp (it is YAML with no produced_by), so exit 3 is "
                         "the expected result and says nothing either way. Neither exit says WHEN a "
                         "record was written, and the register is the artifact under study.")
    verify["record_predates_provenance_format"] = not run_file.read_text().lstrip().startswith("{")

    copy_dir = Path(a.copy_to)
    copy_dir.mkdir(parents=True, exist_ok=True)
    copied = {}
    for f in (reg_file, run_file):
        dst = copy_dir / f.name
        shutil.copyfile(f, dst)          # copy only; never write the recovered record
        copied[f.name] = {"sha256": sha256(f), "bytes": f.stat().st_size, "mtime_utc": mtime(f),
                          "copied_to": str(dst)}

    tracked = run_state_ever_tracked(record.name)
    # register.py at the pass-end commit digests the register FILE when drain-end writes
    # the run record (`register_sha()` = sha256 of register.yaml, .claude/skills/v2r-loop/
    # scripts/register.py at 2e00aa3). So the value is checkable against the file beside it.
    reg_digest = "sha256:" + sha256(reg_file)
    reg_sha_matches = (run.get("register_sha") == reg_digest)
    out = {
        "label": f"recovered record; pre-claim chain verified {matches}/{len(units)}; "
                 "write-time provenance not established",
        "candidate": str(record.resolve()),
        "run_record": {k: run.get(k) for k in ("drain", "instinct_pin", "seed", "outcome")},
        "closed": run.get("closed", []), "parked": run.get("parked", []),
        "closed_count": len(run.get("closed", [])), "parked_count": len(run.get("parked", [])),
        "units_checked": len(units), "pre_claim_matches": matches, "units": units,
        "register_verify_record": verify,
        "register_sha": {
            "value": run.get("register_sha"),
            "digests": "register.yaml as it stood when drain-end wrote the run record "
                       "(register.py register_sha() at the pass-end commit)",
            "sha256_of_register_yaml_beside_it": reg_digest,
            "matches_register_file": reg_sha_matches,
            "meaning": ("a match binds the run record to the exact register file next to it — the "
                        "register has not changed since the record was written, or both were written "
                        "together. It is consistency, not write-time provenance: a later reconstruction "
                        "writing both files would also match."),
            "run_state_dir_ever_tracked": tracked,
            "note_on_history": ("the run-state directory is ignored by version control and "
                                "`git log --all -- <dir>/` is empty on every ref, so no committed copy "
                                "of the register exists to compare against; only the file beside the "
                                "record can be checked, and it is."),
        },
        "sealed_test_sha": {"checked": False,
                            "reason": "the agent may not read the independent tests; if this digest is "
                                      "ever checked it is checked by the referee or the coordinator"},
        "files": copied,
        "provenance": P.block(inputs_path=record, modules=("yaml",),
                              extra={"range": f"{a.first}^..{a.last}"}),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(out["label"], "->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
