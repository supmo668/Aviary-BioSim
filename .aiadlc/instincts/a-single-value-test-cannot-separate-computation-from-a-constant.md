---
name: a-single-value-test-cannot-separate-computation-from-a-constant
confidence: 0.900
created: 2026-09-24T17:58:31Z
last_reinforced: 2026-09-24T17:58:31Z
ttl_days: 30
triggers: [science/tests, demo/tests, pytest, parametrize]
tags: [testing, mutation, method]
---

A single-value test cannot distinguish a correct computation from a constant that happens to equal it. Found live: a test asserted fetch_sequence requested https://rest.uniprot.org/uniprotkb/P01308.fasta, and a mutant that HARDCODED that exact URL passed it — the test fixed one input, so the two implementations were indistinguishable to it. Parametrizing over three accessions killed the mutant immediately.

The shape generalises well beyond URLs: any assertion pinning one input cannot separate f(x) from "return the value f(x) happens to produce". It is most dangerous where the single value is the obvious example everyone reaches for — the canonical id, the first record, the happy-path default — because that is exactly the constant a careless or malicious implementation would hardcode.

Rule: when a test asserts that a value was DERIVED from an input, parametrize over at least two inputs that produce different outputs. One value tests presence; two test derivation. Applies to computed paths, URLs, filenames, keys, ids, formatted messages and cache lookups alike.
