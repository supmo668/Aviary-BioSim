#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Seed a realistic multi-drain .v2r/ so the dashboard has a story to tell.

Shows the shape a real run has: a first drain that closes most units, a second
that recovers some of the parked ones under a fresh instinct pin, and a third
that closes nothing — the loop's own termination condition.
"""
import sys
from pathlib import Path

import yaml

UNITS = [
    ("U-001", "R1", "Environment.reset returns (observations, tools)", 1, "closed"),
    ("U-002", "R1", "Environment.step returns (obs, reward, done, truncated)", 1, "closed"),
    ("U-003", "R1", "step rejects a malformed ToolRequestMessage", 2, "closed"),
    ("U-004", "R1", "reset emits the tool list from the registry", 1, "closed"),
    ("U-005", "R2", "reward derives from the frozen evaluator, never inline", 1, "closed"),
    ("U-006", "R2", "reward is None when the evaluator abstains", 2, "closed"),
    ("U-007", "R2", "evaluator version is recorded on every step", 1, "closed"),
    ("U-008", "R3", "Frame.export serialises state without tools", 1, "closed"),
    ("U-009", "R3", "Frame round-trips through JSON unchanged", 1, "closed"),
    ("U-010", "R3", "export_frame is safe to call before reset", 2, "closed"),
    ("U-011", "R4", "TaskDataset yields one environment per task row", 1, "closed"),
    ("U-012", "R4", "get_new_env_by_idx is deterministic for a seed", 1, "closed"),
    ("U-013", "R4", "dataset length matches the source manifest", 1, "closed"),
    ("U-014", "R5", "SpendTracker.record accumulates per-call cost", 3, "closed"),
    ("U-015", "R5", "submit raises BudgetExceeded above the declared floor", 3, "closed"),
    ("U-016", "R5", "declared floor loads from the run config", 1, "closed"),
    ("U-017", "R5", "spend survives a process restart", 3, "closed"),
    ("U-018", "R6", "tools are exposed over MCP via reset/step, not per-tool", 2, "closed"),
    ("U-019", "R6", "MCP bridge rejects a call for an unregistered tool", 1, "closed"),
    ("U-020", "R6", "bridge surfaces step side effects, not tool returns", 3, "parked"),
    ("U-021", "R7", "co-folding scores cache by (ligand, target) pair", 1, "closed"),
    ("U-022", "R7", "cache miss falls back to the descriptor baseline", 2, "closed"),
    ("U-023", "R7", "both arms are always reported, never just the winner", 3, "parked"),
]

DRAINS = [
    # drain, pin, closed count, parked ids, outcome
    (1, None, 18, ["U-014", "U-015", "U-017", "U-020", "U-023"], "completed"),
    (2, "d4e5f6a1b2c3", 21, ["U-020", "U-023"], "completed"),
    (3, "9a8b7c6d5e4f", 21, ["U-020", "U-023"], "completed"),
]


def main(root: Path) -> int:
    v2r = root / ".v2r"
    v2r.mkdir(parents=True, exist_ok=True)
    ceilings = {"max_drains": 3, "max_attempts": 3, "max_wall_clock_s": 21600, "max_spend_usd": 25}

    units = [
        {
            "id": uid, "satisfies": req, "statement": stmt,
            "stub": f"skeleton/{req.lower()}.py::{uid.replace('-', '_')}",
            "sealed_test": f"tests/sealed/v2r/test_{uid.lower().replace('-', '')}.py",
            "sealed_test_sha": None, "state": state, "attempts": attempts,
            "pre_claim_sha": None,
            "evidence": f".v2r/parked/{uid}.out" if state == "parked" else None,
            "park_branch": f"park/{uid}" if state == "parked" else None,
        }
        for uid, req, stmt, attempts, state in UNITS
    ]
    yaml.safe_dump(
        {"version": 1,
         "run": {"drain": 3, "seed": 1337, "instinct_pin": DRAINS[-1][1], "ceilings": ceilings},
         "units": units},
        (v2r / "register.yaml").open("w"), sort_keys=False)

    closed_ids = [u["id"] for u in units if u["state"] == "closed"]
    for drain, pin, n_closed, parked, outcome in DRAINS:
        yaml.safe_dump(
            {"drain": drain, "register_sha": f"sha256:{'%064x' % (drain * 7919)}",
             "instinct_pin": pin, "seed": 1337, "ceilings": ceilings,
             "closed": closed_ids[:n_closed], "parked": parked, "outcome": outcome},
            (v2r / f"run-record-{drain}.yaml").open("w"), sort_keys=False)

    parked_dir = v2r / "parked"
    parked_dir.mkdir(exist_ok=True)
    (parked_dir / "U-020.out").write_text(
        "E   AssertionError: bridge returned the tool's value, not the step observation\n"
        "1 failed in 0.31s\n")
    (parked_dir / "U-023.out").write_text(
        "E   AssertionError: only the LBM arm was reported; descriptor arm missing\n"
        "1 failed in 0.28s\n")

    print(f"seeded {v2r}: {len(units)} units, {len(DRAINS)} drains")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
