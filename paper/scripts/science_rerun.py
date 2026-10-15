#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "transformers", "requests", "numpy"]
# ///
"""A3c — the protein-model experiment re-run over the hash-verified input.

Runs science/run_experiment.py exactly as published (loaded by path; it writes its own
results.json under THIS checkout's gitignored science/out/), then computes the headline
numbers from the fresh output AND from the published output (--inputs) with the same
code, and compares them. Label `measured (re-run, <date>)` only if every headline value
matches; otherwise the mismatch is recorded and the caller flags the coordinator before
any prose. Model id, revision, weights digest, device, seed, torch/transformers versions
and the uv version are recorded beside the numbers. No sequence string is written.

Isolation: HF_HOME must point at paper/.hf-cache (gitignored); nothing is installed
globally — uv supplies torch/transformers for this run only.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from statistics import mean

# No bytecode. Importing a sibling writes a .pyc whose co_filename is this machine's
# absolute path, and that file is gitignored, so review and every payload scan are blind
# to it. One such file reached a declared artifact directory once.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def headline(res: dict, agent_positions: list[int]) -> dict:
    """The paper's science numbers, from a results.json — the same code for both sides.

    The C-peptide controls are the positions the discovery agent measured that fall in the
    C-peptide region as results.json defines it (`regions`), with the scan's alanine score
    there: derived, never typed in.
    """
    subs = res["substitutions"]
    seq_cys = set(res["cysteine_positions"])
    cys = [s["score"] for s in subs if s["pos"] in seq_cys]
    other = [s["score"] for s in subs if s["pos"] not in seq_cys]
    cpep = next(r for r in res["regions"] if r["name"].lower().startswith("c pep"))
    ctrl_pos = sorted(p for p in agent_positions if cpep["start"] <= p <= cpep["end"])
    ala = {s["pos"]: s["score"] for s in subs if s["mut"] == "A"}
    # The mature protein: everything after the signal peptide, as results.json's own
    # regions define it. The published summary reports both the all-positions and the
    # mature-only means; the paper must map each number to the one it actually is.
    signal = next(r for r in res["regions"] if r["name"].lower().startswith("signal"))
    mature_from = signal["end"] + 1
    cys_m = [s["score"] for s in subs if s["pos"] in seq_cys and s["pos"] >= mature_from]
    other_m = [s["score"] for s in subs if s["pos"] not in seq_cys and s["pos"] >= mature_from]
    return {
        "substitutions": len(subs),
        "cysteine_mean": round(mean(cys), 2),
        "other_mean": round(mean(other), 2),
        "mature_from_position": mature_from,
        "cysteine_mean_mature": round(mean(cys_m), 2),
        "other_mean_mature": round(mean(other_m), 2),
        "n_substitutions_mature": len(cys_m) + len(other_m),
        "cysteine_positions": sorted(seq_cys),
        "c_peptide_region": [cpep["start"], cpep["end"]],
        "c_peptide_controls": {str(p): round(ala[p], 2) for p in ctrl_pos if p in ala},
        "per_position_mean": [round(x["mean_score"], 4) for x in res["per_position"]],
    }


def compare(fresh: dict, published: dict) -> dict:
    keys = ("substitutions", "cysteine_mean", "other_mean", "cysteine_positions",
            "c_peptide_region", "c_peptide_controls",
            "mature_from_position", "cysteine_mean_mature", "other_mean_mature", "n_substitutions_mature")
    return {k: fresh[k] == published[k] for k in keys}


def run_experiment(seed: int) -> Path:
    import torch
    torch.manual_seed(seed)
    spec = importlib.util.spec_from_file_location("run_experiment_rerun", REPO / "science" / "run_experiment.py")
    mod = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        spec.loader.exec_module(mod)
        rc = mod.main()
    finally:
        sys.path[:] = saved
    if rc != 0:
        raise SystemExit(f"ERROR: run_experiment.main() returned {rc}")
    return mod.OUT / "results.json"


def model_facts(model_id: str) -> dict:
    # Only the named model's snapshots: the hub may cache others. The revision and file name
    # are read from the snapshot path BEFORE resolving — the snapshot entry is a symlink into
    # blobs/, whose directory and file names are content hashes, not the revision (QG Q2).
    snaps = Path(os.environ["HF_HOME"]) / "hub" / f"models--{model_id.replace('/', '--')}" / "snapshots"
    weights = sorted(snaps.glob("*/*.safetensors")) or sorted(snaps.glob("*/*.bin"))
    if not weights:
        raise SystemExit(f"ERROR: no weights for {model_id} under {snaps}")
    w, blob = weights[0], weights[0].resolve()
    return {"model_id": model_id, "revision": w.parent.name,
            "weights_file": w.name, "weights_bytes": blob.stat().st_size,
            "weights_sha256": hashlib.sha256(blob.read_bytes()).hexdigest()}


def verdict(match: dict, per_position_mean_matches: bool, day: str):
    """The evidence label and exit code. The paper states that every headline value AND every
    per-position mean matched; both must hold for the file to call itself measured (QG Q6)."""
    if all(match.values()) and per_position_mean_matches:
        return f"measured (re-run, {day})", 0
    return "MISMATCH — reported; see limitations", 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="ABSOLUTE path to the published run's science/out")
    ap.add_argument("--agent-run", default=P.evidence("agent-run.json"))
    ap.add_argument("--out", default=P.evidence("science.json"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="record tree_clean false instead of refusing (A7-2)")
    a = ap.parse_args(argv)
    # A7-2: the recorded git_sha only identifies the producing code on a clean tree.
    P.require_clean_tree(allow_dirty=a.allow_dirty_tree)
    if "HF_HOME" not in os.environ or "paper/.hf-cache" not in os.environ["HF_HOME"]:
        print("ERROR: set HF_HOME to <checkout>/paper/.hf-cache (isolated, gitignored)", file=sys.stderr)
        return 2
    inputs = P.require_inputs(a.inputs)
    published_res = json.loads((inputs / "esm" / "results.json").read_text())
    # agent_run.py writes this file (and reads science.json back for its controls), so a
    # clean rebuild runs agent_run first; a missing file is a named error, exit 2 (QG F08).
    if not Path(a.agent_run).is_file():
        print(f"ERROR: --agent-run {a.agent_run} does not exist; run paper/scripts/agent_run.py first",
              file=sys.stderr)
        return 2
    agent_positions = json.loads(Path(a.agent_run).read_text())["positions_measured"]

    fresh_path = run_experiment(a.seed)
    fresh_res = json.loads(fresh_path.read_text())
    fresh, published = headline(fresh_res, agent_positions), headline(published_res, agent_positions)
    match = compare(fresh, published)
    import torch
    uv = subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()
    out = {
        "label": None,
        **model_facts(fresh_res["model"]),
        "device": fresh_res["device"], "seed": a.seed,
        "runtime_s": fresh_res["runtime_s"],
        "headline": {k: v for k, v in fresh.items() if k != "per_position_mean"},
        "per_position_mean": fresh["per_position_mean"],
        "published": {k: v for k, v in published.items() if k != "per_position_mean"},
        "published_runtime_s": published_res.get("runtime_s"),
        "published_device": published_res.get("device"),
        "match": match,
        "per_position_mean_matches": fresh["per_position_mean"] == published["per_position_mean"],
        "provenance": P.block(inputs_path=inputs, modules=("torch", "transformers", "numpy", "requests"),
                              extra={"uv": uv, "hf_home": os.environ["HF_HOME"],
                                     "fresh_results_path": str(fresh_path),
                                     "cwd": str(Path.cwd())}),
    }
    out["label"], rc = verdict(match, out["per_position_mean_matches"], out["provenance"]["recorded_at"][:10])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(out["label"], "| headline:", out["headline"]["substitutions"], out["headline"]["cysteine_mean"],
          out["headline"]["other_mean"], out["headline"]["c_peptide_controls"], "| match:", match)
    return rc


if __name__ == "__main__":
    sys.exit(main())
