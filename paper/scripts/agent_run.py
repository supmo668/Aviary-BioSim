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
# A substitution token: wild-type letter, position, mutant letter. Harvested matches are
# intersected with the positions the agent actually measured, because this shape also fits a
# cross-reference or a panel label ("Figure S2B", "Table T4C") and those inflated the count
# of named controls — a number the abstract now prints (QG F7).
VARIANT = re.compile(r"\b[A-Z](\d+)[A-Z]\b")
FENCE = ("```", "~~~")
BULLET = ("-", "*", "+")


def requested_positions_per_round(artifact: dict) -> list[list[int]]:
    """Which positions each round ASKED for — the order the agent actually worked in."""
    out = []
    for r in artifact.get("rounds", []):
        found: set[int] = set()
        for req in r.get("requested", []):
            text = req if isinstance(req, str) else json.dumps(req)
            found |= {int(m) for m in REQUESTED_POSITION.findall(text)}
        out.append(sorted(found))
    return out


def first_round_requesting(per_round: list[list[int]], positions) -> int | None:
    """The 1-based round that first requested ANY of `positions`, or None."""
    wanted = set(positions)
    if not wanted:
        return None
    for i, got in enumerate(per_round, 1):
        if wanted & set(got):
            return i
    return None


def first_round_requesting_all(per_round: list[list[int]], positions) -> int | None:
    """The 1-based round that requested EVERY one of `positions`, or None.

    The paper's sentence is "round 1 requested the six cysteines and two C-peptide positions
    together", which an any-of fact cannot support: it would read the same if one cysteine
    came in round 1 and the rest in round 4 (QG F6).
    """
    wanted = set(positions)
    if not wanted:
        return None
    for i, got in enumerate(per_round, 1):
        if wanted <= set(got):
            return i
    return None


def controls_named_by_the_agent(artifact: dict, measured: list[int] | None = None):
    """The positions the agent ITSELF put under a 'control' heading in its write-up.

    A4's rule holds: positions only, never the prose around them. The paper used to describe
    these as a region the agent probed; the agent named neither a region nor these positions
    as belonging to one, so what it did name is what the evidence carries (A7-1).

    Returns (positions, provenance-of-the-extraction) or (None, None) when no control
    heading was found. The LAST matching heading wins, because the paper reports this as the
    agent's final write-up and an earlier scratch list silently replaced it (QG F7).
    """
    hit = None
    for ridx, r in enumerate(artifact.get("rounds", []), 1):
        lines = (r.get("reasoning") or "").splitlines()
        in_fence = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(FENCE):
                in_fence = not in_fence
                continue
            # A `#` comment inside a fenced code block is not a heading; treating it as one
            # let a code comment supply the published count (QG F7).
            if in_fence or not stripped.startswith("#") or not CONTROL_HEADING.search(line):
                continue
            level = len(stripped) - len(stripped.lstrip("#"))
            found: list[int] = []
            scanned = 0
            sub_fence = False
            for nxt in lines[i + 1:]:
                ns = nxt.lstrip()
                if ns.startswith(FENCE):
                    sub_fence = not sub_fence
                    continue
                if sub_fence:
                    continue
                # Stop only at a heading of the same or higher level, so a sub-heading inside
                # the control section does not truncate the list.
                if ns.startswith("#") and (len(ns) - len(ns.lstrip("#"))) <= level:
                    break
                if ns.startswith(BULLET) or re.match(r"\d+[.)]\s", ns) or ns.startswith("|"):
                    scanned += 1
                    found += [int(m) for m in VARIANT.findall(nxt)]
            if found:
                hit = (sorted(set(found)), {"round": ridx, "heading": stripped,
                                            "list_lines_scanned": scanned})
    if hit is None:
        return None, None
    positions, prov = hit
    if measured is not None:
        kept = [p for p in positions if p in set(measured)]
        prov["discarded_not_measured"] = [p for p in positions if p not in set(measured)]
        positions = kept
    return positions, prov


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
    named, named_prov = controls_named_by_the_agent(artifact, c["positions_measured"])
    controls = None
    sci = Path(a.science)
    PENDING = "pending: paper/evidence/science.json not present"
    cpep_round = cys_round = cys_all_round = PENDING
    science_digest = None
    if sci.exists():
        science_bytes = sci.read_bytes()
        # science.json lives under paper/evidence/, which the tree check exempts, so its
        # state is NOT covered by tree_clean; the digest is what pins the region annotation
        # these fields were classified against (QG F2).
        science_digest = hashlib.sha256(science_bytes).hexdigest()
        s = json.loads(science_bytes)
        head = s.get("headline", {})
        ctrl = sorted(int(p) for p in head.get("c_peptide_controls", {}))
        controls = {"c_peptide_positions_from_science_json": ctrl,
                    "measured_by_the_agent": [p for p in ctrl if p in c["positions_measured"]]}
        region = head.get("c_peptide_region")
        if not (isinstance(region, list) and len(region) == 2
                and all(isinstance(v, int) for v in region)):
            print(f"ERROR: {sci} headline.c_peptide_region is not a pair of integers: "
                  f"{region!r}", file=sys.stderr)
            return 2
        lo, hi = region
        # The agent's OWN control list, classified against the region the scan annotates
        # — not against `ctrl` above, which is derived from the agent's own positions and so
        # could only ever agree with itself (A7-1).
        if named is not None:
            inside = [p for p in named if lo <= p <= hi]
            controls.update({
                "named_by_the_agent": named,
                "named_by_the_agent_count": len(named),
                "named_by_the_agent_in_c_peptide": inside,
                "named_by_the_agent_in_c_peptide_count": len(inside),
                "named_by_the_agent_outside_c_peptide": [p for p in named if not lo <= p <= hi],
                "named_by_the_agent_extraction": named_prov,
            })
        cpep_round = first_round_requesting(per_round, range(lo, hi + 1))
        cys = head.get("cysteine_positions", [])
        cys_round = first_round_requesting(per_round, cys)
        cys_all_round = first_round_requesting_all(per_round, cys)
    # Built ONCE: two calls meant two git invocations and let the label's date and
    # provenance.recorded_at straddle UTC midnight, a skew claims.py would not catch.
    prov = P.block(inputs_path=inputs)
    out = {
        "label": "reported (artifact counted, " + prov["recorded_at"][:10] + ")",
        **c,
        "requested_positions_per_round": per_round,
        "cysteines_first_requested_in_round": cys_round,
        "all_cysteines_requested_in_round": cys_all_round,
        "c_peptide_first_requested_in_round": cpep_round,
        "control_positions": controls if controls is not None else PENDING,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_bytes": len(raw),
        "artifact_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                                      .replace(microsecond=0).isoformat(),
        "science_json_sha256": science_digest,
        "provenance": prov,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out = P.redact(out)                  # the artifact's own fields name things too (QG F13)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"{c['measurements']} measurements, {c['rounds']} rounds -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
