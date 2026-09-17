# AGI House submission — BioSim

**Team:** BioSim
**Member:** Mangyin Mo — [linkedin.com/in/matthew-mo](https://www.linkedin.com/in/matthew-mo) · X [@mattmo_668](https://x.com/mattmo_668)
**Repo:** https://github.com/supmo668/Aviary-BioSim (public)
**Tracks:** Best Use of Weave · Best Use of marimo · Best Loop Design

**Deliverables**
| | |
|---|---|
| Presentation deck | https://claude.ai/code/artifact/67e77477-8d04-4984-8178-7849152bab06 |
| Pre-registered study | https://claude.ai/code/artifact/df564d0d-8a96-41e0-9107-047b33d0c5e9 |
| Interpretability report | https://claude.ai/code/artifact/1514a892-2eaa-4cce-9385-8bd17303d9aa |
| marimo dashboard | https://claude.ai/code/artifact/a5dd195c-e3f5-4d6b-a41d-4ce2f1531c0b |
| Weave traces | `3m-m/Aviary-BioSim` |

---

## Summary

**v2r-loop** takes one free-text vision and drives it to a reviewed branch of working, individually-tested code. What makes it self-improving is that it **cannot grade its own homework**: the implementer never sees its test, the test author never sees the implementation, and a 451-line register CLI with no LLM in it re-runs the sealed test before any unit may close. Today the loop built a spend meter under that gate — and then that component became the budget guard inside an **aviary `Environment`** whose tools run **ESM-2 on GPU over real UniProt sequences**, where a second agent found insulin's disulfide constraint by taking 66 real measurements and running controls nobody asked it to run.

## What it does

Autonomous coding loops fail quietly. The usual failure is not bad code — it is a **gate that silently stops being a gate**, after which the loop confidently improves at satisfying a check nobody enforces.

**This happened to us, and it is our best evidence.** An independent review found `register.py` declared only `pyyaml` while being invoked as `uv run --with pyyaml`. So `python -m pytest` exited **1**, our own table read exit 1 as *"test failed"*, and every unit would have burned its attempt budget and parked **while the sealed test never executed a single assertion**. Our 36-test suite passed the whole time, because the tests imported the module in-process under an interpreter that already had pytest. The gate now ignores exit codes entirely and parses pytest's junit-xml, requiring `tests > 0`, `errors == 0`, `skipped == 0`, `passed > 0`.

## How it's built

**The loop.** `register.py` owns every transition — `status next claim seal close park check drain-start drain-end pin`. `close` re-runs the sealed test and refuses anything less than an observed pass. `park` preserves the failed attempt on `park/U-nnn`, resets the tree to the unit's pre-claim SHA, and records evidence — so **every commit on the branch is green by construction**.

**RL environment — aviary.** [Future-House/aviary](https://github.com/Future-House/aviary) supplies the contract. `BioSimEnv` implements both abstract methods; `step()` runs a protein language model rather than a simulation. Its tool list is `score_variant`, `embed_sequence` (ESM-2 650M on Apple MPS over UniProt) and `spend_remaining`, a read-only view of the budget. The budget itself is drain 1's `SpendTracker`, and only the harness writes it, through `charge()` for every model call it pays for: `step()` refuses to run a tool once spend passes the ceiling. The agent is the party being metered, so it is offered no tool that writes the ledger. The reward channel is wired to `0.0` deliberately: aviary carries a reward because it is an RL gym, this is tool-mediated discovery, and inventing a scalar would be a fabricated signal.

**Agent protocol — MCP.** The W&B MCP server is how the loop reads its own execution traces between drains. The environment's tools are exposed through `reset`/`step`, not one endpoint per tool — deliberately, because aviary's own `make_tool_server` documents that calling tools directly bypasses the side effects that live in `step`.

**Agent framework.** Claude Code skills and subagents. Each build unit is discharged by two isolated subagents; neither sees the other's output. The attended head composes `/research`, `/grill-with-depth` and `/writing-plans` in order.

## Results — every number from a run that happened

| | |
|---|---|
| Substitutions scored (ESM-2, real sequences) | **2,090** |
| Six disulfide cysteines, mean score | **−13.02** |
| Every other residue, mean score | **−5.85** |
| Full 110-residue scan on Apple MPS | **7 s** |
| Agent-chosen measurements | **66** |
| Tests green across the loop | **168** |

**Two known outcomes recovered from sequence alone.** *Sus scrofa* sits nearest human (0.55) — porcine insulin differs by a single residue, which is why it was the therapeutic before recombinant. *Cavia porcellus* sits furthest (2.69), beyond zebrafish and *Xenopus* — the known hystricomorph divergence.

**The best result we did not design.** Having found the cysteines, the agent probed the C-peptide — cleaved out of mature insulin, poorly conserved — and got Gln62A **+1.53**, Pro79A **+1.08**, Glu83A **−0.10**. That is the correct negative control for a position-specific effect, and nothing in the prompt asked for one. It also named the second tier unprompted: Leu30, Leu35, Leu105, Phe48, Phe49, Tyr50 — the buried hydrophobic core.

## Sponsor tools and protocols

| Sponsor tool | How we used it |
|---|---|
| **W&B Weave** | Every pipeline stage and every agent round is a `@weave.op`, so the full decision tree is queryable. This is the input to the between-drain learning step and the entire basis of the interpretability report. **A real finding:** our register originally used `weave.publish()`, which writes an *object* rather than a call — it succeeded, printed a confident URL, and returned **zero** to the trace query. Fixed; the query now returns 19. Instrumented and readable are different properties. |
| **W&B MCP server** | `query_weave_traces_tool` and `count_weave_traces_tool` are how the loop reads its own traces back between drains — and how we verified the fix above by querying rather than by reading code. |
| **W&B Inference** | Serverless OpenAI-compatible inference on `deepseek-ai/DeepSeek-V4-Pro-0813` for all agent reasoning, 46,250 completion tokens end to end. It is also how **stage 0 unblocks GPU access**: serverless takes the GPU off the critical path, the most common human blocker in an autonomous run. |
| **marimo** | `dashboard/v2r_dashboard.py` — reactive dashboard over `register.yaml` and the run records: stat tiles, a stacked bar per drain, per-unit attempt counts, requirement coverage, and parked units with their real assertion failures. |
| **MCP (protocol)** | Consumed for trace reading; the environment's tools are exposed through `reset`/`step` rather than per-tool. |

## Why this is a good loop

- **Self-correcting by construction.** Three independent precedents in our tooling say the same thing: the actor doing the work must not record that the work passed. We enforce it mechanically.
- **It knows when to stop.** A drain closing zero new units ends the loop — a convergence signal, not a timeout.
- **It refuses to improve mid-run.** Instincts are pinned per drain — approximately, since hooks rewrite the store (see the limitation below); adopting them mid-drain would make the run unattributable.
- **Our own agent corrected us, twice.** It refused a scope change the coordinator asked for — quoting the rule that only the human gate fixes scope — and routed it to the human. It then refused to manufacture a park for the demo, because an engineered park is indistinguishable from an earned one in the register.

## Status, stated honestly

**Built, tested and run:** the register CLI and its ten transitions; the sealed-referee gate and its refusal matrix; park-and-revert; ceilings; run records; the instinct pin; Weave tracing; the marimo dashboard; `BioSimEnv` against aviary's contract; the ESM-2 experiment; the traced discovery loop; all three deliverables. **168 tests green** — 42 register, 51 science, and 75 sealed component tests last run at drain 1's close (`demo/spend_tracker.py` is unchanged since).

**Built and tested, not yet run end to end:** `BioSimEnv`'s budget enforcement. The discovery loop refuses to start without a declared token price, and none has been supplied yet. The 66-measurement run above predates it, so its traces show the earlier tool list, which still offered the agent `record`.

**The limitation that matters most.** Three defects surfaced today, and they are one shape:
a mechanism reported success while the property it existed to guarantee was absent.
`weave.publish()` succeeded and printed a confident URL while nothing could read the traces.
The register pinned three inputs and not the per-unit prompts, which is where the difficulty
actually lives. The instinct pin was computed correctly and does not identify what it names,
because Stop-hook reinforcement rewrites the store's frontmatter whether or not anything was
learned. **All three were caught by hand, not by the loop.** The sealed gate is built to catch
a build unit that fails; it is blind to a mechanism that passes for the wrong reason. We think
that is the honest frontier of this design, and we would rather state it than have a judge
find it. It is also not only ours: applying the same lens to a mature, pre-existing quality
gate elsewhere in our tooling found a suite of entirely skipped tests signing green — it had
a self-test, and the self-test passed. The pattern is not a story about code written in a day.

**Not claimed:** ESM-2 has certainly seen insulin — this is recovery of known constraint, not discovery of new biology. No wet experiment has been run. A trace shows what an agent *said* its reasons were, not what caused the output. The register pins the instinct set, seed and register hash but **not the per-unit prompts**, which is where difficulty actually lives — our own worker agent found this, and we narrowed the documented claim from reproduction to attribution rather than leave an overclaim in a public repo.

## Run it

```bash
# Everything below runs from the repository root.
uv run --with pytest --with pyyaml pytest .claude/skills/v2r-loop/scripts/tests -q   # 42 passed
uv run --with pytest --with pyyaml --with fhaviary --with openai --with weave \
  pytest science/tests -q                                    # 51 passed

uv run --with pyyaml demo/gate_demo.py                       # the gate refusing, in 10 s

uv run --with pyyaml dashboard/seed_demo_run.py .
uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
  marimo run dashboard/v2r_dashboard.py

uv run science/run_experiment.py                             # the real ESM-2 scan
# The discovery loop meters every model call and has no default price. Set PRICE to your
# provider's USD price per 1M tokens, and WANDB_API_KEY for inference, or it will not start.
BIOSIM_USD_PER_1M_TOKENS="${PRICE:?set PRICE to the USD price per 1M tokens from your provider}" \
  uv run science/run_discovery.py                            # the traced agent loop
```
