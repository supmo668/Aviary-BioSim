#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""The gate, on camera, in ten seconds.

Three sealed tests against three build units. One genuinely passes. One is
entirely skipped. One collects nothing. Only the first may close a unit — the
other two are gates that did not actually gate, and both must HALT.

Run:  uv run --with pyyaml demo/gate_demo.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REGISTER = Path(__file__).resolve().parents[1] / ".claude/skills/v2r-loop/scripts/register.py"

G, Y, R, D, B = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m"
X = "\033[0m"

CASES = [
    ("U-001", "a test that genuinely passes",
     "def test_records_cost():\n    assert True\n"),
    ("U-002", "a test that is entirely SKIPPED",
     'import pytest\n\n@pytest.mark.skip(reason="not implemented yet")\n'
     "def test_records_cost():\n    assert False\n"),
    ("U-003", "a test that COLLECTS NOTHING",
     "# the author never wrote an assertion\n"),
]


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "config", "user.email", "demo@example.com"],
                    ["git", "config", "user.name", "demo"]):
            sh(cmd, repo)
        (repo / "README.md").write_text("seed\n")
        sh(["git", "add", "-A"], repo)
        sh(["git", "commit", "-q", "-m", "seed"], repo)

        (repo / "gate").mkdir()
        (repo / ".v2r").mkdir()
        units = []
        for uid, _label, body in CASES:
            (repo / "gate" / f"test_{uid.lower().replace('-', '')}.py").write_text(body)
            units.append({
                "id": uid, "satisfies": "R1", "statement": f"SpendTracker behaviour {uid}",
                "stub": "skeleton/spend_tracker.py", "state": "open", "attempts": 0,
                "sealed_test": f"gate/test_{uid.lower().replace('-', '')}.py",
                "sealed_test_sha": None, "pre_claim_sha": None,
                "evidence": None, "park_branch": None,
            })
        yaml.safe_dump(
            {"version": 1,
             "run": {"drain": 1, "seed": 1337, "instinct_pin": None,
                     "ceilings": {"max_drains": 3, "max_attempts": 3,
                                  "max_wall_clock_s": 21600, "max_spend_usd": 25}},
             "units": units},
            (repo / ".v2r" / "register.yaml").open("w"), sort_keys=False)

        print(f"\n{B}The gate decides whether a build unit may close.{X}")
        print(f"{D}Three sealed tests. Only one of them actually tested anything.{X}\n")

        for uid, label, _ in CASES:
            sh(["uv", "run", "--with", "pyyaml", str(REGISTER), "claim", uid], repo)
            sh(["uv", "run", "--with", "pyyaml", str(REGISTER), "seal", uid], repo)
            done = sh(["uv", "run", "--with", "pyyaml", str(REGISTER), "close", uid], repo)
            rc = done.returncode
            if rc == 0:
                verdict, colour = "CLOSED   committed to the branch", G
            elif rc == 3:
                verdict, colour = "HALT     the gate could not gate", R
            else:
                verdict, colour = f"exit {rc}", Y
            print(f"  {B}{uid}{X}  {label:36} {colour}{verdict}{X}")

        closed = [
            u["id"] for u in
            yaml.safe_load((repo / ".v2r" / "register.yaml").read_text())["units"]
            if u["state"] == "closed"
        ]
        log = sh(["git", "log", "--oneline"], repo).stdout.strip().splitlines()

        print(f"\n{D}  closed: {closed or 'none'}{X}")
        print(f"{D}  commits on the branch:{X}")
        for line in log:
            print(f"{D}    {line}{X}")
        print(f"\n{B}A test that never asserted anything can never close a unit.{X}")
        print(f"{D}No agent is trusted to report this. The gate re-runs the test itself.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
