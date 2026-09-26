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
    ap.add_argument("--science", default="paper/evidence/science.json",
                    help="A3c evidence; if present, its control positions are intersected")
    ap.add_argument("--out", default="paper/evidence/agent-run.json")
    a = ap.parse_args(argv)
    inputs = P.require_inputs(a.inputs)
    path = inputs / "discovery.json"
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 2
    raw = path.read_bytes()
    artifact = json.loads(raw)
    c = counts(artifact)
    controls = None
    sci = Path(a.science)
    if sci.exists():
        s = json.loads(sci.read_text())
        ctrl = sorted(int(p) for p in s.get("headline", {}).get("c_peptide_controls", {}))
        controls = {"c_peptide_positions_from_science_json": ctrl,
                    "measured_by_the_agent": [p for p in ctrl if p in c["positions_measured"]]}
    out = {
        "label": "reported (artifact counted, " + P.block(None)["recorded_at"][:10] + ")",
        **c,
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
