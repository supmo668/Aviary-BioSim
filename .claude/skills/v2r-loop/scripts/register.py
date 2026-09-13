#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "pytest"]
# ///
# pytest is a HARD dependency, not a convenience: the gate shells out to
# `sys.executable -m pytest`, and an interpreter without it makes every sealed
# test look like a failing one. See docs/adr/0001 and the _pytest_available check.
#
# `weave` is deliberately NOT declared here. It is imported lazily inside
# emit_span and only when V2R_TRACE=1, so the gate stays fast and works offline.
# To emit spans, add it at the call site:
#     uv run --with pyyaml --with weave register.py close U-001
# See docs/DEPENDENCIES.md.
"""Register CLI for /v2r-loop.

Owns every state transition. The rest of the system trusts this file without a
human reading the register, so it must be verifiable by reading it.

Contains no LLM call. The only network path is `emit_span`, which is fire-and-forget
telemetry emitted strictly AFTER a decision is made, requires explicit opt-in via
V2R_TRACE=1, and can never change a verdict.

See docs/adr/0001-register-cli-owns-every-transition.md
"""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
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


PASS, FAIL, HALT = "pass", "fail", "halt"
EXIT_CLOSED, EXIT_TEST_FAILED, EXIT_HALT = 0, 1, 3


def _pytest_available() -> bool:
    """Can the interpreter we shell out to actually import pytest?

    Not hypothetical: under `uv run --with pyyaml register.py` it cannot, and
    `python -m pytest` then exits 1 — indistinguishable from a failing test.
    A gate that never ran must never look like a gate that ran and failed.
    """
    probe = subprocess.run(
        [sys.executable, "-c", "import pytest"], capture_output=True, text=True
    )
    return probe.returncode == 0


def _parse_junit(xml_path: Path) -> dict[str, int] | None:
    """Exact counts from pytest's own report. None if it wrote nothing."""
    if not xml_path.exists():
        return None
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return None
    get = lambda k: int(suite.get(k, 0))  # noqa: E731
    total, failures, errors, skipped = get("tests"), get("failures"), get("errors"), get("skipped")
    return {
        "tests": total,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": total - failures - errors - skipped,
    }


def run_sealed_test(path: str) -> tuple[str, str]:
    """Run one sealed test and return (verdict, output), verdict in {pass, fail, halt}.

    The verdict comes from pytest's junit-xml counts, NOT from its exit code.
    Exit codes conflate too much: a missing pytest, an empty file and a real
    failure all surface as 1 or 0. A unit may only close when at least one
    assertion actually passed and nothing was skipped.
    """
    if not Path(path).exists():
        return HALT, f"sealed test not found: {path}"
    if not _pytest_available():
        return HALT, f"pytest is not importable by {sys.executable}; the gate cannot execute"

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "report.xml"
        completed = subprocess.run(
            [
                sys.executable, "-m", "pytest", path,
                "-q", "--no-header", "-p", "no:cacheprovider",
                f"--junitxml={xml_path}",
            ],
            capture_output=True,
            text=True,
        )
        counts = _parse_junit(xml_path)

    output = completed.stdout + completed.stderr
    if counts is None:
        return HALT, f"pytest produced no report (exit {completed.returncode})\n{output}"
    if counts["errors"]:
        return HALT, f"sealed test errored during collection or setup\n{output}"
    if counts["tests"] == 0:
        return HALT, f"sealed test collected nothing\n{output}"
    if counts["skipped"]:
        return HALT, f"sealed test skipped {counts['skipped']} of {counts['tests']} tests\n{output}"
    if counts["failures"]:
        return FAIL, output
    if counts["passed"] == 0:
        return HALT, f"sealed test asserted nothing\n{output}"
    return PASS, output


_SPAN_SINK = None  # tests install a callable here; production resolves weave lazily
_SPAN_WARNED = False


def emit_span(name: str, **attrs) -> None:
    """Record one iteration span.

    Never raises — a drain must not die on telemetry. But it does not fail
    silently either: a dropped span means stage 4 has no evidence to read, so
    the first failure is reported once on stderr.
    """
    global _SPAN_WARNED
    payload = {"name": name, **attrs}
    if _SPAN_SINK is not None:
        _SPAN_SINK(payload)
        return
    # Explicit opt-in. An ambient WANDB_API_KEY from an unrelated project must
    # never cause this file to publish unit statements and test output.
    if os.environ.get("V2R_TRACE") != "1" or not os.environ.get("WANDB_API_KEY"):
        return
    try:
        import weave

        weave.init(os.environ.get("WANDB_PROJECT", "3m-m/Aviary-BioSim"))
        weave.publish(payload, name=name)
    except Exception as exc:  # noqa: BLE001 — telemetry is never load-bearing
        if not _SPAN_WARNED:
            print(f"weave span dropped ({type(exc).__name__}: {exc}); "
                  f"stage 4 will have no evidence for this drain", file=sys.stderr)
            _SPAN_WARNED = True
        return


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
    """Close a build unit — but only by observing its sealed test pass, here, now."""
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)

    if unit["state"] != CLAIMED:
        print(f"{unit['id']} is {unit['state']}, not claimed", file=sys.stderr)
        return 2

    recorded = unit.get("sealed_test_sha")
    if recorded and Path(unit["sealed_test"]).exists():
        actual = sha256_file(unit["sealed_test"])
        if actual != recorded:
            print(
                f"HALT: sealed test for {unit['id']} changed after sealing "
                f"({recorded[:12]} -> {actual[:12]})",
                file=sys.stderr,
            )
            emit_span("unit.halt", unit=unit["id"], reason="sealed-test-modified")
            return EXIT_HALT

    verdict, output = run_sealed_test(unit["sealed_test"])

    if verdict == HALT:
        print(f"HALT: gate could not execute for {unit['id']}", file=sys.stderr)
        print(output, file=sys.stderr)
        emit_span("unit.halt", unit=unit["id"], reason="gate-unexecutable")
        return EXIT_HALT

    if verdict == FAIL:
        unit["attempts"] += 1
        save(REGISTER, data)
        print(f"{unit['id']} failed its sealed test (attempt {unit['attempts']})", file=sys.stderr)
        emit_span("unit.attempt", unit=unit["id"], attempts=unit["attempts"], output=output[-2000:])
        return EXIT_TEST_FAILED

    # Commit FIRST, persist the closed state only once it is durable. The reverse
    # order can leave the register claiming `closed` with no commit behind it.
    try:
        git("add", "-A")
        git("commit", "-q", "-m",
            f"{unit['id']} {unit['statement']} (satisfies {unit['satisfies']})")
    except (subprocess.CalledProcessError, KeyError) as exc:
        print(f"HALT: could not commit {unit['id']}: {exc}", file=sys.stderr)
        emit_span("unit.halt", unit=unit["id"], reason="commit-failed")
        return EXIT_HALT

    unit["state"] = CLOSED
    save(REGISTER, data)
    print(f"closed {unit['id']}")
    emit_span("unit.close", unit=unit["id"], satisfies=unit["satisfies"], attempts=unit["attempts"])
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
    emit_span("unit.park", unit=unit["id"], attempts=unit["attempts"], branch=branch)
    return 0


INSTINCT_STORE = ".aiadlc/instincts"


def instinct_pin() -> str | None:
    """Tree SHA of the instinct store — an exact, already-versioned identifier.

    See ADR-0003: the store is in-repo and not gitignored, so the pin needs no
    new machinery. Returns None before any instinct has been captured.
    """
    try:
        return git("rev-parse", f"HEAD:{INSTINCT_STORE}")
    except subprocess.CalledProcessError:
        return None


def register_sha() -> str:
    return "sha256:" + hashlib.sha256(REGISTER.read_bytes()).hexdigest()


def cmd_pin(args) -> int:
    print(instinct_pin() or "")
    return 0


def cmd_drain_start(args) -> int:
    data = load(REGISTER)
    data["run"]["drain"] = args.drain
    data["run"]["seed"] = args.seed
    data["run"]["instinct_pin"] = instinct_pin()
    save(REGISTER, data)
    print(f"drain {args.drain} seed {args.seed} pin {data['run']['instinct_pin']}")
    return 0


def cmd_drain_end(args) -> int:
    data = load(REGISTER)
    record = {
        "drain": data["run"]["drain"],
        "register_sha": register_sha(),
        "instinct_pin": data["run"]["instinct_pin"],
        "seed": data["run"]["seed"],
        "ceilings": data["run"]["ceilings"],
        "closed": [u["id"] for u in data["units"] if u["state"] == CLOSED],
        "parked": [u["id"] for u in data["units"] if u["state"] == PARKED],
        "outcome": args.outcome,
    }
    save(V2R_DIR / f"run-record-{record['drain']}.yaml", record)
    print(f"drain {record['drain']} {args.outcome}: "
          f"{len(record['closed'])} closed, {len(record['parked'])} parked")
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

    start = sub.add_parser("drain-start", help="pin the instinct set and open a drain")
    start.add_argument("--drain", type=int, required=True)
    start.add_argument("--seed", type=int, required=True)
    start.set_defaults(fn=cmd_drain_start)

    end = sub.add_parser("drain-end", help="write the run record")
    end.add_argument("--outcome", choices=["completed", "halted"], required=True)
    end.set_defaults(fn=cmd_drain_end)

    sub.add_parser("pin", help="print the instinct pin").set_defaults(fn=cmd_pin)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
