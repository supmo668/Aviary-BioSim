# Submission fields — CoreWeave Hacks: Agent Loops Hackathon

Paste straight into the Create Project form. Nothing below needs editing.

---

## Project Name
```
Vision-to-Reality Loop
```
*(the codebase, skill and docs call it `v2r-loop`; the form spells it out so it reads cold.
Team is **BioSim**; the repo stays **Aviary-BioSim** — do not rename it, its URL is live
inside both published artifacts and the W&B project name.)*

## Tagline
```
Agents that measure, not agents that guess.
```

**How the three names divide the work** — keep them distinct and nothing needs reconciling:

| Name | Job |
|---|---|
| **BioSim** | the team, and the biology application the loop was proved on |
| **Vision-to-Reality Loop** (`v2r-loop`) | the product — what Best Loop Design is judging |
| **Aviary-BioSim** | the repository. Unchanged. |

## Description

```
v2r-loop takes one free-text vision and drives it to a reviewed branch of working,
individually-tested code. What makes the loop self-improving is that it cannot grade its
own homework: the implementer never sees its test, the test author never sees the
implementation, and a 451-line register CLI with no LLM in it re-runs the sealed test
before any unit may close.

We know that failure mode first-hand. An independent review found our own register
declared only `pyyaml` while being invoked with only `pyyaml` available — so
`python -m pytest` exited 1, our own table read exit 1 as "test failed", and every build
unit would have burned its attempt budget and parked WHILE THE SEALED TEST NEVER RAN ONCE.
Our 36-test suite passed the entire time, because the tests imported the module in-process
under an interpreter that happened to have pytest. The gate now ignores exit codes and
parses pytest's junit-xml, requiring tests>0, errors==0, skipped==0, passed>0.

Then we pointed the loop at biology. Drain 1 built a spend meter under that sealed gate;
that component then became a tool inside an aviary Environment whose other tools run
ESM-2 (650M) on GPU over real UniProt sequences. A second agent, given only "which
residues of human proinsulin are least tolerant of substitution", took 66 real
measurements and found the six disulfide cysteines — mean score -13.02 against -5.85 for
every other residue, with correct chain assignments (C31=B7, C43=B19, C109=A20).

The best result is one we did not design: having found the cysteines, the agent probed the
C-peptide — the segment cleaved out of mature insulin — and got +1.53, +1.08, -0.10. That
is the correct negative control for a position-specific effect, and nothing in the prompt
asked for one.

Nine real insulin orthologs were embedded: pig nearest human (0.55, it differs by one
residue), guinea pig furthest (2.69, beyond zebrafish and Xenopus) — the known
hystricomorph divergence, recovered from sequence alone.

Every stage of both agents is a @weave.op, so the full decision tree is queryable: which
hypotheses were discarded, on what stated grounds, and what each fork cost. 46,250
completion tokens end to end. 117 tests green. Zero fabricated numbers.

Honest limits, stated up front: ESM-2 has seen insulin, so this recovers known constraint
rather than discovering new biology; no wet experiment has been run; and a trace shows
what an agent SAID its reasons were, not what caused the output.
```

## Tech Stack

Add each as a tag:

```
Python · PyTorch · Transformers · ESM-2 · Aviary · MCP · Weights & Biases ·
W&B Weave · W&B Inference · marimo · Altair · pytest · uv · Claude Code ·
DeepSeek-V4-Pro · UniProt · Apple MPS · YAML · Git
```

If the field takes few tags, prioritise: **Aviary · W&B Weave · W&B Inference · marimo · MCP · ESM-2 · PyTorch · Python**

## Repository URL
```
https://github.com/supmo668/Aviary-BioSim
```

## Demo URL

**This is the one that goes in the form.** A separate artifact with the speaker notes
removed from the file entirely — not hidden, not toggled off. There is no key that reveals
them because there is nothing to reveal.

```
https://claude.ai/code/artifact/33a47af4-a12b-4bd3-82f7-6b07de4cedc8
```

### Your own link — keep this one private

Same seven slides, with the speaker notes still in. Press **`n`** to show them if a judge
asks for depth mid-answer. **Do not paste this into the form.**

```
https://claude.ai/code/artifact/67e77477-8d04-4984-8178-7849152bab06
```

### The other three deliverables

Put these in the description, or as extra links if the form accepts more than one.

```
Pre-registered study   https://claude.ai/code/artifact/df564d0d-8a96-41e0-9107-047b33d0c5e9
Interpretability tree  https://claude.ai/code/artifact/1514a892-2eaa-4cce-9385-8bd17303d9aa
marimo dashboard       https://claude.ai/code/artifact/a5dd195c-e3f5-4d6b-a41d-4ce2f1531c0b
```

The dashboard link is the **evidence for the marimo track** — put it somewhere a judge will
click. Without it the track rests on a Python file nobody will install.

**Share all five** from each artifact's share menu, then open them in a private window to
confirm. Artifacts are private by default; an unshared link shows a judge nothing.

---

## Tracks — select these four

| Track | Select | Why |
|---|---|---|
| **Best Loop Design** | ✅ | Everyone joins. Also our strongest claim: a gate the coordinator itself could not wave through. |
| **Best Use of Weave** | ✅ | Every stage of both agents is a `@weave.op`; the traces are the entire basis of the interpretability deliverable. We also found and fixed a real Weave defect — `weave.publish()` writes an object, not a call, so it succeeded while returning zero to the trace query. |
| **Best Use of marimo** | ✅ | `dashboard/v2r_dashboard.py` — reactive dashboard over the loop's own state files, shown running against the real run: [a5dd195c…](https://claude.ai/code/artifact/a5dd195c-e3f5-4d6b-a41d-4ce2f1531c0b) |
| **Most Production-Ready** | ✅ | 117 tests, sealed-referee gate, four ADRs, a glossary resolving four terminology collisions, and a component already ported upstream into a plugin framework. This is the 2-weeks-later award and the work genuinely stands up. |

**Do not select:**

| Track | Why not |
|---|---|
| Best Use of ARIA | We did not use it. Claiming it would be false. |
| Best Use of TypeSafe AI | Not used. |
| Best Social Media demo | We have a HeyGen presenter video and an X handle, but no social campaign. Weak claim; skip unless the form lets you join freely. |

---

## Socials

```
X         @mattmo_668
LinkedIn  linkedin.com/in/matthew-mo
```

---

## One honesty note about the venue

This is **CoreWeave Hacks**, and our GPU work ran on **Apple MPS locally** plus **W&B Inference** for serverless LLM calls — not on CoreWeave hardware. There is no CoreWeave track listed, so nothing here overclaims. If a judge asks where the GPU was, the answer is: ESM-2 650M on local MPS in 7 seconds, and W&B Inference for everything else, chosen specifically so no GPU sat on the critical path of an autonomous run.

---

## Still to do

- [ ] **Participant survey** — every member, on the platform. Blocks the submission from closing.
- [ ] **Screen recording** under 2:00 — shot list in [`docs/DEMO.md`](docs/DEMO.md)
- [ ] Confirm all five artifact links open in a private window (submission deck, presenter deck, study, interpretability, dashboard)
- [ ] Zoom installed, or https://share.zoom.us reachable, for the 3-minute room
