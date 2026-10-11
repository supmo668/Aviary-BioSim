#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A4 — the discovery run, counted from its own artifact. Label: reported.

Counts only: how many measurements the agent chose, how many rounds, the completion
tokens per round, the model named, and which residue positions were measured. No
reasoning text, no result text and no identifier is copied out of the artifact.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

POSITION = re.compile(r"'position':\s*(\d+)")
# `requested` entries are JSON-quoted, the audit trail is repr-quoted: accept either.
REQUESTED_POSITION = re.compile(r"[\"']position[\"']:\s*(\d+)")
CONTROL_HEADING = re.compile(r"control", re.I)
VARIANT = re.compile(r"\b[A-Z](\d+)[A-Z]\b")


def requested_positions_per_round(artifact: dict) -> list[list[int]]:
    """Which positions each round ASKED for — the order the agent actually worked in."""
    return [sorted({int(m) for req in r.get("requested", []) for m in REQUESTED_POSITION.findall(req)})
            for r in artifact.get("rounds", [])]


def first_round_requesting(per_round: list[list[int]], positions) -> int | None:
    """The 1-based round that first requested ANY of `positions`, or None."""
    wanted = set(positions)
    for i, got in enumerate(per_round, 1):
        if wanted & set(got):
            return i
    return None


def controls_named_by_the_agent(artifact: dict) -> list[int] | None:
    """The positions the agent ITSELF put under a 'control' heading in its write-up.

    A4's rule holds: positions only, never the prose around them. The paper used to
    describe these as a region the agent probed; the agent named neither a region nor
    these positions as belonging to one, so what it did name is what the evidence
    carries (A7-1).
    """
    for r in artifact.get("rounds", []):
        lines = (r.get("reasoning") or "").splitlines()
        for i, line in enumerate(lines):
            if not (line.lstrip().startswith("#") and CONTROL_HEADING.search(line)):
                continue
            found: list[int] = []
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("#"):
                    break
                if nxt.lstrip().startswith(("-", "*")):
                    found += [int(m) for m in VARIANT.findall(nxt)]
            if found:
                return sorted(set(found))
    return None


def counts(artifact: dict) -> dict:
    trail = artifact.get("audit_trail", [])
    rounds = artifact.get("rounds", [])
    tokens = [r.get("completion_tokens") for r in rounds]
    positions = sorted({int(m) for entry in trail for m in POSITION.findall(entry)})
    return {
        "measurements": len(trail),
        "rounds": len(rounds),
        "requests_per_round": [len(r.get("requested", [])) for r in rounds],
        "completion_tokens_per_round": tokens,
        "completion_tokens_total": sum(t for t in tokens if isinstance(t, (int, float))),
        "rounds_without_a_token_count": sum(1 for t in tokens if not isinstance(t, (int, float))),
        "model": artifact.get("model"),
        "positions_measured": positions,
        "distinct_positions": len(positions),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="ABSOLUTE path to <science/out>/discovery")
    ap.add_argument("--science", default=P.evidence("science.json"),
                    help="A3c evidence; if present, its control positions are intersected")
    ap.add_argument("--out", default=P.evidence("agent-run.json"))
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="record tree_clean false instead of refusing (A7-2)")
    a = ap.parse_args(argv)
    # A7-2: the recorded git_sha only identifies the producing code on a clean tree.
    P.require_clean_tree(allow_dirty=a.allow_dirty_tree)
    inputs = P.require_inputs(a.inputs)
    path = inputs / "discovery.json"
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 2
    raw = path.read_bytes()
    artifact = json.loads(raw)
    c = counts(artifact)
    per_round = requested_positions_per_round(artifact)
    named = controls_named_by_the_agent(artifact)
    controls = None
    sci = Path(a.science)
    cpep_round = cys_round = None
    if sci.exists():
        s = json.loads(sci.read_text())
        head = s.get("headline", {})
        ctrl = sorted(int(p) for p in head.get("c_peptide_controls", {}))
        controls = {"c_peptide_positions_from_science_json": ctrl,
                    "measured_by_the_agent": [p for p in ctrl if p in c["positions_measured"]]}
        # The agent's OWN control list, classified against the region the scan annotates
        # — not against the list above, which is derived from the agent's positions and so
        # could only ever agree with itself (A7-1).
        lo, hi = head.get("c_peptide_region", [None, None])
        if named is not None and lo is not None:
            inside = [p for p in named if lo <= p <= hi]
            controls.update({
                "named_by_the_agent": named,
                "named_by_the_agent_count": len(named),
                "named_by_the_agent_in_c_peptide": inside,
                "named_by_the_agent_in_c_peptide_count": len(inside),
                "named_by_the_agent_outside_c_peptide": [p for p in named if not lo <= p <= hi],
                "region_named_by_the_agent": None,
            })
        if lo is not None:
            cpep_round = first_round_requesting(per_round, range(lo, hi + 1))
        cys_round = first_round_requesting(per_round, head.get("cysteine_positions", []))
    out = {
        "label": "reported (artifact counted, " + P.block(None)["recorded_at"][:10] + ")",
        **c,
        "requested_positions_per_round": per_round,
        "cysteines_first_requested_in_round": cys_round,
        "c_peptide_first_requested_in_round": cpep_round,
        "control_positions": controls if controls is not None else "pending: paper/evidence/science.json not present",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_bytes": len(raw),
        "artifact_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                                      .replace(microsecond=0).isoformat(),
        "provenance": P.block(inputs_path=inputs),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"{c['measurements']} measurements, {c['rounds']} rounds -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
