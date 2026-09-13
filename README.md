# v2r-loop — vision to reality

**One prompt states a vision. The loop returns a reviewed branch of working, individually-tested code — and gets better at it each pass.**

```
/v2r-loop "Build an aviary Environment for drug-discovery world-modelling,
           wrapping a frozen evaluator as the reward channel"
```

That string is the only parameter. There are no flags.

---

## The problem with self-improving loops

Most agent loops grade their own homework. The agent writes the code, the agent runs the check, the agent reports success. When the check is weak — or silently broken — nothing notices, and the loop confidently improves at producing work that passes a test nobody enforced.

v2r-loop is built so that **cannot** happen. The agent that does the work is structurally incapable of recording that the work passed.

- The **implementer** never sees the test it must satisfy.
- The **test-author** never sees the implementation, and writes only from the unit's statement plus a committed interface skeleton.
- The **register CLI** — 400 lines, no LLM, no network in its decision path — re-runs the sealed test itself and refuses to close a unit on anything less than an observed pass.

We did not get this right by design alone. An independent review of our own trust core found that `register.py` declared only `pyyaml` as a dependency while being invoked as `uv run --with pyyaml` — so `python -m pytest` exited 1, our table read 1 as *"test failed"*, and **every unit would have burned its attempts and parked while the sealed test never ran once**. Our 36-test suite passed throughout, because the tests imported the module in-process under an interpreter that happened to have pytest.

The gate now ignores exit codes entirely. It parses pytest's junit-xml and requires `tests > 0`, `errors == 0`, `skipped == 0`, `passed > 0`. Anything else halts. A sealed test that collects nothing, or whose tests are all skipped, can never close a unit.

## How the loop runs

```
/v2r-loop "<vision>"
   │
   │  ATTENDED HEAD — a vision is not a specification
   ├─ /research          ground the open questions
   ├─ /grill-with-docs   decide the boundary, fix the vocabulary
   ├─ spec.md            standing requirements R1..Rn — never closed
   ├─ /writing-plans     the ordered implementation plan
   └─ register + skeleton   build units U-001..U-0nn, committed stubs
   │
   ⏸  ONE approval — scope frozen, ceilings declared, PR authorised
   │
   │  UNATTENDED BODY
   ├─ claim → sealed test → implement → gate re-runs the test
   │     pass  → commit, close
   │     budget spent → preserve attempt on park/U-nnn, restore tree, park
   │
   └─ between drains: read own Weave traces → capture instincts → retry only
                      what parked → stop when a drain closes nothing new
```

**Every commit on the branch is green by construction**, because a parked unit's code is reverted out of the tree and preserved on its own branch. The history is bisectable at behaviour granularity.

## Two ideas worth stealing

**Requirements are standing; build units are derived.** A requirement like *"Modal spend is tracked and the run halts before exceeding the declared credit"* is never *done* — it must hold across every later refactor. Marking it closed stops it being enforced. So requirements stay open forever and build units, which close exactly once, carry `satisfies: R9` back to them. ([ADR-0002](docs/adr/0002-requirements-standing-build-units-derived.md))

**A self-improving loop that refuses to improve mid-run.** Instincts are hash-pinned at drain start. Adopting them mid-drain would build `U-001` and `U-023` with materially different agents, so the same register replayed would produce different code with no recoverable cause. The pin is free: the instinct store is in-repo, so it is `git rev-parse HEAD:.aiadlc/instincts`. ([ADR-0003](docs/adr/0003-instincts-pinned-per-drain.md))

## See it

```bash
uv run --with pyyaml dashboard/seed_demo_run.py .
uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
  marimo run dashboard/v2r_dashboard.py
```

The dashboard reads a real `.v2r/` run directory. Green grows and amber shrinks across drains, and the delta line names the termination condition: *"drain 2 → 3: closed nothing new — loop terminates."* The loop stops because it stopped improving, not because a timer expired.

## Run the tests

```bash
cd .claude/skills/v2r-loop/scripts
uv run --with pytest --with pyyaml pytest tests/ -q      # 42 passed
```

`tests/test_register_gate.py` is the interesting file: every test there encodes a distinct way the gate could silently stop being a gate.

## Status, stated honestly

**Built and tested:** the register CLI and its ten transitions, the sealed-referee gate with its refusal matrix, park-and-revert, ceilings, run records, the instinct pin, Weave span emission, the marimo dashboard, and an end-to-end drain that proves the green-commit invariant.

**Designed, not yet run end-to-end with live subagents:** the full attended head (stages 1–2) and a multi-drain autonomous run against a real register. The drain mechanics are exercised by tests and by manual runs under the documented invocation.

**The first real target:** an [aviary](https://github.com/Future-House/aviary) `Environment` for drug-discovery world-modelling. Aviary supplies the `reset`/`step`/`Frame` contract; what it has no public example of is a chemistry or assay environment, which is the gap this repo aims at next.

## Documents

| | |
|---|---|
| [`docs/spec.md`](docs/spec.md) | the approved design |
| [`docs/CONTEXT.md`](docs/CONTEXT.md) | glossary — four terminology collisions resolved before they cost a drain |
| [`docs/adr/`](docs/adr/) | four decisions, each with the alternative that was priced and declined |
| [`docs/plan.md`](docs/plan.md) | the implementation plan this repo was built from |

## Licence

MIT
