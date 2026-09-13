#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "transformers", "requests", "numpy"]
# ///
"""Stage A — the real computation behind every figure.

Runs ESM-2 over real UniProt sequences and writes the numbers to JSON. Nothing
downstream invents a value; the charts read this file.

The question it answers is the computational counterpart of the pre-registered
study: that design asks whether the ER's capacity to FORM proinsulin's disulfide
bonds limits yield. Here we ask whether a protein language model, trained only
on sequences, treats the six cysteines that make those bonds as load-bearing.

The expected direction is established independently — human INS cysteine
mutations cause permanent neonatal diabetes through proinsulin misfolding, and
the mouse Akita Ins2 C96Y allele is the classic disulfide-disrupting case. We
run it and report what comes out.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import esm_tool as E  # noqa: E402

OUT = Path(__file__).parent / "out" / "esm"

# Accessions only. The LABEL is never hardcoded — it comes from the organism
# UniProt returns, because a guessed label on a real sequence is a fabricated
# figure. Two earlier guesses were wrong (P01334 is a rattlesnake fragment, not
# chicken; P12706 is Xenopus, not zebrafish) and the data caught them.
ORTHOLOGS = ["P01308", "P01326", "P01322", "P01315", "P01317",
             "P01329", "P67970", "O73727", "P12706"]

MIN_FULL_LENGTH = 90  # preproinsulin is ~105-110 aa; shorter entries are fragments

# Chain boundaries of human preproinsulin (UniProt P01308), 1-based.
REGIONS = [("signal peptide", 1, 24), ("B chain", 25, 54),
           ("C peptide", 57, 87), ("A chain", 90, 110)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"device: {E.device()}   model: {E.MODEL_ID}", flush=True)

    # ---- real sequences ----
    seqs = {}
    for acc in ORTHOLOGS:
        try:
            rec = E.fetch_sequence(acc)
        except Exception as exc:
            print(f"  {acc:8} FETCH FAILED — omitted ({exc})", flush=True)
            continue
        if rec["length"] < MIN_FULL_LENGTH:
            print(f"  {acc:8} {rec['organism']:24} {rec['length']:>4} aa  "
                  f"DROPPED (fragment)", flush=True)
            continue
        # Label from the organism the database returned, never from a guess.
        genus, _, species = rec["organism"].partition(" ")
        rec["label"] = f"{genus[0]}. {species.split()[0]}" if species else rec["organism"]
        rec["organism_full"] = rec["organism"]
        seqs[acc] = rec
        print(f"  {acc:8} {rec['organism']:24} {rec['length']:>4} aa", flush=True)

    human = seqs["P01308"]
    seq = human["sequence"]
    cys = [i + 1 for i, a in enumerate(seq) if a == "C"]
    print(f"\nhuman preproinsulin: {len(seq)} aa, cysteines at {cys}", flush=True)

    # ---- full single-substitution scan (110 forward passes) ----
    print("\nscanning every substitution…", flush=True)
    lps = E.position_logprobs(seq)
    subs = E.substitution_scores(seq, lps)
    print(f"  {len(subs)} substitutions scored in {time.time() - t0:.0f}s", flush=True)

    # per-position sensitivity = mean score over the 19 substitutions there
    per_pos = []
    for p in range(1, len(seq) + 1):
        rows = [r["score"] for r in subs if r["pos"] == p]
        per_pos.append({"pos": p, "wt": seq[p - 1],
                        "mean_score": float(np.mean(rows)),
                        "min_score": float(np.min(rows)),
                        "is_cys": seq[p - 1] == "C"})

    cys_scores = [r["score"] for r in subs if seq[r["pos"] - 1] == "C"]
    non_cys = [r["score"] for r in subs if seq[r["pos"] - 1] != "C"]

    # matched comparison: only positions outside the signal peptide, so the
    # contrast is within the mature protein rather than against a cleaved leader
    mature = [r for r in subs if r["pos"] >= 25]
    cys_mature = [r["score"] for r in mature if seq[r["pos"] - 1] == "C"]
    non_cys_mature = [r["score"] for r in mature if seq[r["pos"] - 1] != "C"]

    # ---- ortholog embeddings ----
    print("\nembedding orthologs…", flush=True)
    emb = {}
    for acc, rec in seqs.items():
        emb[acc] = E.embed(rec["sequence"])
        print(f"  {acc} {rec['label']}", flush=True)

    accs = list(emb)
    M = np.array([emb[a] for a in accs])
    Mc = M - M.mean(axis=0)
    U, S, Vt = np.linalg.svd(Mc, full_matrices=False)
    coords = U[:, :2] * S[:2]
    var = (S**2 / (S**2).sum())[:2]
    hi = accs.index("P01308")
    dist = {accs[i]: float(np.linalg.norm(M[i] - M[hi])) for i in range(len(accs))}

    result = {
        "model": E.MODEL_ID, "device": E.device(),
        "runtime_s": round(time.time() - t0, 1),
        "sequences": {a: {k: v for k, v in r.items() if k != "sequence"}
                      for a, r in seqs.items()},
        "human_sequence": seq,
        "cysteine_positions": cys,
        "regions": [{"name": n, "start": s, "end": e} for n, s, e in REGIONS],
        "per_position": per_pos,
        "substitutions": subs,
        "summary": {
            "n_substitutions": len(subs),
            "cys_mean_all": float(np.mean(cys_scores)),
            "non_cys_mean_all": float(np.mean(non_cys)),
            "cys_mean_mature": float(np.mean(cys_mature)),
            "non_cys_mean_mature": float(np.mean(non_cys_mature)),
            "n_cys_subs_mature": len(cys_mature),
            "n_non_cys_subs_mature": len(non_cys_mature),
        },
        "embedding": {
            "accessions": accs,
            "labels": [seqs[a]["label"] for a in accs],
            "coords": coords.tolist(),
            "explained_variance": var.tolist(),
            "distance_to_human": dist,
        },
    }
    (OUT / "results.json").write_text(json.dumps(result, indent=2))

    s = result["summary"]
    print(f"\n{'─'*58}\nRESULT (mature protein, positions 25-110)")
    print(f"  cysteine substitutions      n={s['n_cys_subs_mature']:<5} mean {s['cys_mean_mature']:+.3f}")
    print(f"  non-cysteine substitutions  n={s['n_non_cys_subs_mature']:<5} mean {s['non_cys_mean_mature']:+.3f}")
    print(f"  difference                  {s['cys_mean_mature'] - s['non_cys_mean_mature']:+.3f}")
    print(f"\nwrote {OUT / 'results.json'}  ({result['runtime_s']}s on {E.device()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
