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
    return {
        "substitutions": len(subs),
        "cysteine_mean": round(mean(cys), 2),
        "other_mean": round(mean(other), 2),
        "cysteine_positions": sorted(seq_cys),
        "c_peptide_region": [cpep["start"], cpep["end"]],
        "c_peptide_controls": {str(p): round(ala[p], 2) for p in ctrl_pos if p in ala},
        "per_position_mean": [round(x["mean_score"], 4) for x in res["per_position"]],
    }


def compare(fresh: dict, published: dict) -> dict:
    keys = ("substitutions", "cysteine_mean", "other_mean", "cysteine_positions",
            "c_peptide_region", "c_peptide_controls")
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
    hub = Path(os.environ["HF_HOME"]) / "hub"
    weights = sorted(hub.rglob("*.safetensors")) or sorted(hub.rglob("*.bin"))
    if not weights:
        raise SystemExit(f"ERROR: no model weights found under {hub}")
    w = weights[0].resolve()
    return {"model_id": model_id, "revision": w.parent.name,
            "weights_file": w.name, "weights_bytes": w.stat().st_size,
            "weights_sha256": hashlib.sha256(w.read_bytes()).hexdigest()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="ABSOLUTE path to the published run's science/out")
    ap.add_argument("--agent-run", default="paper/evidence/agent-run.json")
    ap.add_argument("--out", default="paper/evidence/science.json")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if "HF_HOME" not in os.environ or "paper/.hf-cache" not in os.environ["HF_HOME"]:
        print("ERROR: set HF_HOME to <checkout>/paper/.hf-cache (isolated, gitignored)", file=sys.stderr)
        return 2
    inputs = P.require_inputs(a.inputs)
    published_res = json.loads((inputs / "esm" / "results.json").read_text())
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
    out["label"] = (f"measured (re-run, {out['provenance']['recorded_at'][:10]})"
                    if all(match.values()) else "MISMATCH — reported; see limitations")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(out["label"], "| headline:", out["headline"]["substitutions"], out["headline"]["cysteine_mean"],
          out["headline"]["other_mean"], out["headline"]["c_peptide_controls"], "| match:", match)
    return 0 if all(match.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
