#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "transformers", "requests"]
# ///
"""Real protein-language-model computation on real sequences.

No mock data and no synthetic sequences: every sequence is fetched from UniProt
and every number below is produced by running ESM-2 over it. The functions here
are the ones exposed to the agent as aviary Tools.

Scoring is the standard masked-marginal: mask position i, run the model once,
and read the log-probability the model assigns to each amino acid at that
position. score(mut) = log P(mut) - log P(wt). One forward pass per position
covers all 19 substitutions there, so a 110-residue protein costs 110 passes.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests
import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

MODEL_ID = os.environ.get("ESM_MODEL", "facebook/esm2_t33_650M_UR50D")
CACHE = Path(__file__).parent / "out" / "seqs"
AA = "ACDEFGHIKLMNPQRSTVWY"

# UniProtKB's own accession grammar (the pattern UniProt publishes), anchored.
# The accession is chosen by an untrusted agent and is interpolated into BOTH a
# cache path and a request URL, so it is validated once, here, before either.
ACCESSION = re.compile(
    r"\A(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\Z"
)


def valid_accession(accession: object) -> str:
    """Return `accession` if it is a UniProtKB accession; raise ValueError otherwise.

    Rejecting is the whole point: `../../x` escapes the cache directory and reads
    any .json on the host, and a value carrying `/`, `?` or `#` steers the UniProt
    request somewhere other than the entry asked for. Nothing is sanitised or
    trimmed — a value that is not an accession is refused, not repaired.
    """
    match = ACCESSION.match(accession) if isinstance(accession, str) else None
    if match is None:
        raise ValueError(
            f"not a UniProt accession: {accession!r} "
            "(expected e.g. P01308 — 6 or 10 uppercase alphanumerics)"
        )
    # Return the MATCHED TEXT, not the caller's object. isinstance admits str
    # subclasses, and a subclass can override __format__/__str__ so the f-string
    # below builds a different path than the regex just inspected. re gives back a
    # plain str, so the value that was validated is the value that gets used.
    return match.group(0)

_model = None
_tok = None
_device = None


def device() -> str:
    global _device
    if _device is None:
        _device = "mps" if torch.backends.mps.is_available() else (
            "cuda" if torch.cuda.is_available() else "cpu")
    return _device


def load_model():
    """Load ESM-2 once per process, onto the GPU where one exists."""
    global _model, _tok
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForMaskedLM.from_pretrained(MODEL_ID).to(device()).eval()
    return _model, _tok


def fetch_sequence(accession: str) -> dict:
    """Fetch one UniProt entry. Cached on disk; never fabricated."""
    accession = valid_accession(accession)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{accession}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    r = requests.get(f"https://rest.uniprot.org/uniprotkb/{accession}.fasta", timeout=30)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    header = lines[0]
    seq = "".join(lines[1:])
    name = header.split("OS=")[0].split("|")[-1].strip()
    organism = header.split("OS=")[1].split("OX=")[0].strip() if "OS=" in header else "?"
    rec = {"accession": accession, "name": name, "organism": organism,
           "sequence": seq, "length": len(seq)}
    cached.write_text(json.dumps(rec, indent=2))
    return rec


@torch.no_grad()
def position_logprobs(sequence: str) -> list[dict]:
    """Masked-marginal log-probabilities for every position in the sequence.

    Returns one dict per residue: its 1-based position, the wild-type residue,
    and log P for each of the 20 amino acids at that position with the site
    masked. This is the raw material for every substitution score.
    """
    model, tok = load_model()
    dev = device()
    enc = tok(sequence, return_tensors="pt").to(dev)
    ids = enc["input_ids"]
    n = len(sequence)
    out = []
    aa_ids = {a: tok.convert_tokens_to_ids(a) for a in AA}

    for i in range(n):
        masked = ids.clone()
        masked[0, i + 1] = tok.mask_token_id          # +1: leading <cls>
        logits = model(input_ids=masked, attention_mask=enc["attention_mask"]).logits
        lp = torch.log_softmax(logits[0, i + 1], dim=-1)
        out.append({
            "pos": i + 1,
            "wt": sequence[i],
            "logp": {a: float(lp[aa_ids[a]]) for a in AA},
        })
    return out


def substitution_scores(sequence: str, logprobs: list[dict] | None = None) -> list[dict]:
    """Every single substitution, scored. Negative = model finds it disruptive."""
    lps = logprobs if logprobs is not None else position_logprobs(sequence)
    rows = []
    for entry in lps:
        wt, lp = entry["wt"], entry["logp"]
        if wt not in lp:
            continue
        for mut in AA:
            if mut == wt:
                continue
            rows.append({"pos": entry["pos"], "wt": wt, "mut": mut,
                         "score": lp[mut] - lp[wt]})
    return rows


@torch.no_grad()
def embed(sequence: str) -> list[float]:
    """Mean-pooled final-layer representation, excluding the special tokens."""
    model, tok = load_model()
    enc = tok(sequence, return_tensors="pt").to(device())
    hidden = model(**enc, output_hidden_states=True).hidden_states[-1][0]
    return hidden[1:-1].mean(dim=0).float().cpu().tolist()


# ── the two operations the agent sees as aviary Tools ────────────────────────
def score_variant(accession: str, position: int, mutant: str) -> str:
    """Score one amino-acid substitution in a real protein with ESM-2.

    Args:
        accession: UniProt accession of the protein, for example P01308 for human insulin.
        position: 1-based residue position in the full sequence to substitute.
        mutant: Single-letter amino acid code to substitute in at that position.
    """
    rec = fetch_sequence(accession)
    seq = rec["sequence"]
    if not 1 <= position <= len(seq):
        return f"position {position} is outside {accession} (length {len(seq)})"
    wt = seq[position - 1]
    if mutant not in AA:
        return f"{mutant!r} is not one of the 20 amino acids"
    lp = position_logprobs(seq[: position] + seq[position:])[position - 1]["logp"]
    score = lp[mutant] - lp[wt]
    return (f"{accession} {wt}{position}{mutant}: score {score:.3f} "
            f"(negative means the model finds the substitution disruptive)")


def embed_sequence(accession: str) -> str:
    """Compute an ESM-2 embedding for a real protein and report its identity.

    Args:
        accession: UniProt accession of the protein to embed, for example P01308.
    """
    rec = fetch_sequence(accession)
    vec = embed(rec["sequence"])
    return (f"{accession} ({rec['organism']}, {rec['length']} aa) embedded: "
            f"{len(vec)}-dimensional representation")
