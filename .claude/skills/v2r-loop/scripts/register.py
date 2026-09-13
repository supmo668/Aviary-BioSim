#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Register CLI for /v2r-loop.

Owns every state transition. Contains no LLM call and no network call: the rest of
the system trusts this file's correctness, so it must be verifiable by reading it.

See docs/adr/0001-register-cli-owns-every-transition.md
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

V2R_DIR = Path(".v2r")
REGISTER = V2R_DIR / "register.yaml"

OPEN, CLAIMED, CLOSED, PARKED = "open", "claimed", "closed", "parked"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def unit_by_id(data: dict, unit_id: str) -> dict:
    for unit in data["units"]:
        if unit["id"] == unit_id:
            return unit
    raise KeyError(f"no such build unit: {unit_id}")


def next_open(data: dict) -> str | None:
    for unit in data["units"]:
        if unit["state"] == OPEN:
            return unit["id"]
    return None


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def head_sha() -> str:
    return git("rev-parse", "HEAD")


def cmd_claim(args) -> int:
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    if unit["state"] != OPEN:
        print(f"{unit['id']} is {unit['state']}, not open", file=sys.stderr)
        return 2
    unit["state"] = CLAIMED
    unit["pre_claim_sha"] = head_sha()
    save(REGISTER, data)
    print(f"claimed {unit['id']} at {unit['pre_claim_sha'][:8]}")
    return 0


def cmd_status(args) -> int:
    data = load(REGISTER)
    counts: dict[str, int] = {}
    for unit in data["units"]:
        counts[unit["state"]] = counts.get(unit["state"], 0) + 1
    print(f"drain {data['run']['drain']}  pin {data['run']['instinct_pin']}")
    for state in (OPEN, CLAIMED, CLOSED, PARKED):
        print(f"  {state:8} {counts.get(state, 0)}")
    return 0


def cmd_next(args) -> int:
    unit_id = next_open(load(REGISTER))
    if unit_id is None:
        return 1
    print(unit_id)
    return 0


PYTEST_PASSED = 0
PYTEST_FAILED = 1
EXIT_NO_SEALED_TEST = 90  # ours, deliberately outside pytest's 0-5 exit space
EXIT_CLOSED, EXIT_TEST_FAILED, EXIT_HALT = 0, 1, 3


def run_sealed_test(path: str) -> tuple[int, str]:
    """Run one sealed test. Returns (exit code, combined output).

    Exit 5 (no tests collected) is NOT a pass: a sealed test that collects
    nothing would otherwise close a build unit by never failing.
    """
    if not Path(path).exists():
        return EXIT_NO_SEALED_TEST, f"sealed test not found: {path}"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout + completed.stderr


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_seal(args) -> int:
    """Record the sealed test's digest. Run once, after the test-author writes it."""
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    if not Path(unit["sealed_test"]).exists():
        print(f"sealed test not found: {unit['sealed_test']}", file=sys.stderr)
        return 2
    unit["sealed_test_sha"] = sha256_file(unit["sealed_test"])
    save(REGISTER, data)
    print(f"sealed {unit['id']} {unit['sealed_test_sha'][:12]}")
    return 0


def cmd_close(args) -> int:
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)

    recorded = unit.get("sealed_test_sha")
    if recorded and Path(unit["sealed_test"]).exists():
        actual = sha256_file(unit["sealed_test"])
        if actual != recorded:
            print(
                f"HALT: sealed test for {unit['id']} changed after sealing "
                f"({recorded[:12]} -> {actual[:12]})",
                file=sys.stderr,
            )
            return EXIT_HALT

    code, output = run_sealed_test(unit["sealed_test"])

    if code not in (PYTEST_PASSED, PYTEST_FAILED):
        print(f"HALT: gate could not execute for {unit['id']} (exit {code})", file=sys.stderr)
        print(output, file=sys.stderr)
        return EXIT_HALT

    if code == PYTEST_FAILED:
        unit["attempts"] += 1
        save(REGISTER, data)
        print(f"{unit['id']} failed its sealed test (attempt {unit['attempts']})", file=sys.stderr)
        return EXIT_TEST_FAILED

    unit["state"] = CLOSED
    save(REGISTER, data)
    git("add", "-A")
    git("commit", "-q", "-m", f"{unit['id']} {unit['statement']} (satisfies {unit['satisfies']})")
    print(f"closed {unit['id']}")
    return EXIT_CLOSED


def cmd_park(args) -> int:
    """Retire one build unit. Preserve the attempt, restore the tree, record why.

    A park is local: it says nothing about any other unit. See ADR-0004.
    """
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    pre_claim = unit["pre_claim_sha"]
    if not pre_claim:
        print(f"{unit['id']} has no pre_claim_sha; was it claimed?", file=sys.stderr)
        return 2

    branch = f"park/{unit['id']}"
    evidence_src = Path(args.evidence).read_bytes()

    # Preserve the attempt on its own branch, then restore the tree.
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", f"parked attempt for {unit['id']}")
    git("branch", "-f", branch, "HEAD")
    git("reset", "-q", "--hard", pre_claim)

    parked_dir = V2R_DIR / "parked"
    parked_dir.mkdir(parents=True, exist_ok=True)
    evidence_dest = parked_dir / f"{unit['id']}.out"
    evidence_dest.write_bytes(evidence_src)

    unit["state"] = PARKED
    unit["park_branch"] = branch
    unit["evidence"] = str(evidence_dest)
    save(REGISTER, data)
    print(f"parked {unit['id']} -> {branch}; tree restored to {pre_claim[:8]}")
    return 0


def attempts_exhausted(unit: dict, data: dict) -> bool:
    """Per-unit budget. Exhausting it parks ONE unit; the drain continues."""
    return unit["attempts"] >= data["run"]["ceilings"]["max_attempts"]


def check_ceilings(data: dict, started_at: float, spend_usd: float) -> str | None:
    """Whole-drain budget. A breach halts the drain; it never parks a unit."""
    ceilings = data["run"]["ceilings"]
    if data["run"]["drain"] > ceilings["max_drains"]:
        return f"drain cap: {data['run']['drain']} > {ceilings['max_drains']}"
    elapsed = time.time() - started_at
    if elapsed > ceilings["max_wall_clock_s"]:
        return f"wall clock: {elapsed:.0f}s > {ceilings['max_wall_clock_s']}s"
    if spend_usd > ceilings["max_spend_usd"]:
        return f"spend: ${spend_usd:.2f} > ${ceilings['max_spend_usd']}"
    return None


def cmd_check(args) -> int:
    data = load(REGISTER)
    reason = check_ceilings(data, started_at=args.started_at, spend_usd=args.spend_usd)
    if reason:
        print(f"HALT: {reason}", file=sys.stderr)
        return EXIT_HALT
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="register")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="summarise register state").set_defaults(fn=cmd_status)
    sub.add_parser("next", help="print the next open build unit id").set_defaults(fn=cmd_next)

    claim = sub.add_parser("claim", help="claim the next build unit")
    claim.add_argument("unit")
    claim.set_defaults(fn=cmd_claim)

    seal = sub.add_parser("seal", help="record the sealed test digest after authoring")
    seal.add_argument("unit")
    seal.set_defaults(fn=cmd_seal)

    close = sub.add_parser("close", help="close a unit if its sealed test passes")
    close.add_argument("unit")
    close.set_defaults(fn=cmd_close)

    park = sub.add_parser("park", help="retire a unit, preserving the attempt")
    park.add_argument("unit")
    park.add_argument("--evidence", required=True, help="path to the failing test output")
    park.set_defaults(fn=cmd_park)

    check = sub.add_parser("check", help="halt if a declared ceiling is breached")
    check.add_argument("--started-at", type=float, required=True, dest="started_at")
    check.add_argument("--spend-usd", type=float, default=0.0, dest="spend_usd")
    check.set_defaults(fn=cmd_check)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
