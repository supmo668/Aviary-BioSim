---
name: v2r-watch-the-run-a-push-triggers
confidence: 0.800
created: 2026-10-30T17:04:01Z
last_reinforced: 2026-10-30T17:04:01Z
ttl_days: 30
triggers: [.github/workflows, paper/claims.py, paper/main.tex, tools/git-push]
tags: [ci, publication, engine-mismatch]
---

A push that touches a gated surface is not finished until the run it triggered reaches a
terminal state and I have reported it. My paper-arxiv-check CI went red at 12:19 on a U+2212
that pdflatex cannot set, and nobody heard for ~4 hours; the CTO found it by sweeping. I had
the run id in hand at push time and chose not to look.

Report red PROMPTLY, green with its assertion output, never silence.

The defect underneath is worth its own line, because it recurs in content and in
configuration: a local engine more permissive than the target engine produces green builds
that fail at the venue. tectonic (XeTeX) accepts U+2212; pdflatex, which arXiv runs, is fatal
on it. The same shape produced the CTO's own `-pdf` trap. When the local check and the venue
check use different engines, only the venue's engine is evidence.
