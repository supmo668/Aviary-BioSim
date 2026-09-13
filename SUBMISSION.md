# AGI House submission — BioSim

**Team:** BioSim
**Member:** Mangyin Mo — [linkedin.com/in/matthew-mo](https://www.linkedin.com/in/matthew-mo)
**Repo:** https://github.com/supmo668/Aviary-BioSim (public)
**Tracks:** Best Use of Weave · Best Use of marimo · Best Loop Design

---

## Summary (2–3 sentences)

**v2r-loop** takes a single free-text vision and drives it to a reviewed branch of working, individually-tested code: an attended head turns the vision into a specification, a plan and a committed interface skeleton, then an unattended body drains it one testable behaviour at a time. What makes the loop self-improving is that it **cannot grade its own homework** — the implementer never sees its test, the test-author never sees the implementation, and a 400-line register CLI with no LLM in it re-runs the sealed test itself before any unit may close. Between drains it reads its own Weave traces, captures what it learned, retries only what failed, and stops when a drain closes nothing new.

## What it does / what it's useful for

Autonomous coding loops fail quietly. The usual failure is not bad code — it is a **gate that silently stops being a gate**, after which the loop confidently improves at satisfying a check nobody is enforcing.

v2r-loop makes that structurally impossible, and the payoff is that a run can be left alone. You are involved exactly twice: you write one sentence, and you approve one artifact set. After that the loop builds, tests, fails, preserves its failures, learns, retries, and stops itself.

**We hit this exact failure in our own build, which is the best evidence we have.** An independent review found `register.py` declared only `pyyaml` while being invoked as `uv run --with pyyaml` — so `python -m pytest` exited 1, our own table read 1 as *"test failed"*, and every unit would have burned its attempt budget and parked **while the sealed test never executed a single assertion**. Our 36-test suite passed the whole time, because the tests imported the module in-process under an interpreter that already had pytest. The gate now ignores exit codes and parses pytest's junit-xml, requiring `tests > 0`, `errors == 0`, `skipped == 0`, `passed > 0`.

## How it's built

**The loop.** `register.py` owns every state transition — `status next claim seal close park check drain-start drain-end pin`. It contains no LLM call, and no network call in its decision path. `close` re-runs the sealed test and refuses on anything less than an observed pass. `park` preserves the failed attempt on `park/U-nnn`, resets the tree to the unit's pre-claim SHA, and records the evidence — so **every commit on the branch is green by construction** and the history is bisectable at behaviour granularity.

**Agent protocol — MCP.** The loop consumes the Weights & Biases MCP server to read its own execution traces between drains (`query_weave_traces_tool`). The target environment exposes `reset`/`step` over MCP rather than one endpoint per tool — deliberately, because aviary's own `make_tool_server` documents that calling tools directly bypasses the side effects that live in `step`.

**Agent application framework.** Claude Code skills and subagents. Each build unit is discharged by two isolated subagents — a test-author given only the unit statement and the interface skeleton, and an implementer given only the statement and the stub. Neither sees the other's output. The attended head composes three existing skills in order: `/research`, `/grill-with-docs`, `/writing-plans`.

**RL environment — aviary.** [Future-House/aviary](https://github.com/Future-House/aviary) supplies the contract the first real target implements: `Environment.reset() -> (Messages, list[Tool])`, `step(action) -> (obs, reward, done, truncated)`, and `Frame` for state export. Aviary ships `gsm8k`, `hotpotqa`, `labbench`, `lfrqa` and `notebook` — there is **no public chemistry or assay environment**, which is the gap this repo targets next.

**Reproducibility.** Instincts are hash-pinned per drain, so any run is attributable to exactly one builder. The pin costs nothing: the instinct store is in-repo, so it is `git rev-parse HEAD:.aiadlc/instincts`.

## Sponsor tools and protocols used

| Sponsor tool | How we used it |
|---|---|
| **W&B Weave** | `register.py` emits a span on every iteration outcome — `unit.attempt` (with the failing pytest output), `unit.close`, `unit.park`, `unit.halt`. This is the loop's evidence base: stage 4 reads these traces back to decide what it learned. Weave does **not** capture this automatically — it auto-traces SDK calls, and our implementers are Claude Code subagents — so we instrument the register explicitly. Telemetry is fire-and-forget and requires explicit `V2R_TRACE=1` opt-in, and can never change a verdict. |
| **W&B MCP server** | Connected over HTTP at user scope. `query_weave_traces_tool` is how the loop reads its own traces between drains — which units parked, at which attempt, on what failure. This is the input to the self-improvement step. |
| **W&B Inference** | Serverless OpenAI-compatible inference on `deepseek-ai/DeepSeek-V4-Pro-0813`, verified live. This is also how the loop's **stage 0 unblocks GPU access**: serverless inference removes the GPU from the critical path entirely, which is the single most common human blocker in an autonomous run. |
| **marimo** | `dashboard/v2r_dashboard.py` — a reactive dashboard over `register.yaml` and the run records. Stat tiles, a stacked bar per drain, per-unit attempt counts, standing-requirement coverage, and the parked units with their real assertion failures. It is how the loop's self-correction becomes visible in ten seconds instead of a terminal scrollback. |
| **MCP (agent protocol)** | Consumed for trace reading (above); and the target environment's tools are exposed over MCP through `reset`/`step`, not per-tool. |

## Why this is a good loop

- **Self-correcting by construction, not by intention.** Three independent precedents — a frozen evaluator, a validation sentinel, signed receipts — all say the same thing: the actor doing the work must not record that the work passed. We enforce it mechanically.
- **It knows when to stop.** A drain that closes zero new units ends the loop. Not a timeout, not a fixed iteration count — an actual convergence signal.
- **It refuses to improve mid-run.** Adopting instincts mid-drain would make a run unattributable. Learning is adopted only between drains, under a recorded pin.
- **It fails safely.** A parked unit leaves no code in the tree, its attempt survives on a branch, and its evidence is recorded. A ceiling breach halts the whole drain with everything preserved and resumable.
- **Scope cannot creep.** The approved register is the contract. No later drain may add a unit that was not in it.

## Status, stated honestly

**Built and tested** (42 tests, all passing): the register CLI and its ten transitions, the sealed-referee gate and its refusal matrix, park-and-revert, ceilings, run records, the instinct pin, Weave span emission, the marimo dashboard, an end-to-end drain proving the green-commit invariant.

**Designed, not yet run end-to-end with live subagents:** the full attended head and a multi-drain autonomous run against a real register. Drain mechanics are exercised by tests and by manual runs under the documented invocation.

## Demo

```bash
uv run --with pyyaml dashboard/seed_demo_run.py .
uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
  marimo run dashboard/v2r_dashboard.py

cd .claude/skills/v2r-loop/scripts
uv run --with pytest --with pyyaml pytest tests/ -q      # 42 passed
```
