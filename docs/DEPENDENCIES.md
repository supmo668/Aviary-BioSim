# Dependencies and external services

Nothing here is installed globally. Every executable declares its own dependencies
in a [PEP 723](https://peps.python.org/pep-0723/) header and runs under `uv`, so a
fresh clone needs only `uv` and `git`.

```bash
uv --version    # 0.11+
git --version
```

## Entry points and what each one needs

| Entry point | Declared dependencies | Network |
|---|---|---|
| `.claude/skills/v2r-loop/scripts/register.py` | `pyyaml`, `pytest` | none, unless `V2R_TRACE=1` |
| `dashboard/v2r_dashboard.py` | `marimo`, `pyyaml`, `pandas`, `altair`, `pyarrow` | none |
| `dashboard/seed_demo_run.py` | `pyyaml` | none |
| `demo/gate_demo.py` | `pyyaml` | none |
| the test suite | `pytest`, `pyyaml` | none |

```bash
# the gate, on camera
uv run --with pyyaml demo/gate_demo.py

# the dashboard
uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
  marimo run dashboard/v2r_dashboard.py

# the tests
cd .claude/skills/v2r-loop/scripts
uv run --with pytest --with pyyaml pytest tests/ -q
```

### Two dependencies that are load-bearing for non-obvious reasons

**`pytest` in `register.py` is not a convenience.** The gate shells out to
`sys.executable -m pytest`. An interpreter without pytest exits 1 — which this
tool's own encoding would otherwise read as *"the sealed test failed"* — so every
build unit would burn its attempt budget and park while no test ever ran. This
exact bug shipped and was caught in review; `_pytest_available()` now makes a
missing pytest an explicit **halt**. See [ADR-0001](adr/0001-register-cli-owns-every-transition.md).

**`pyarrow` is never imported by our code.** Altair uses it to serialise data
frames; without it every chart silently falls back to CSV with a warning.

## External services

All optional. The loop runs, gates and drains completely offline — services add
telemetry, inference and visibility, never correctness.

| Service | Used for | Required? |
|---|---|---|
| **W&B Weave** | one span per iteration (`unit.attempt`, `unit.close`, `unit.park`, `unit.halt`) — the evidence stage 4 reads back | optional; opt-in |
| **W&B MCP server** | `query_weave_traces_tool` — how the loop reads its own traces between drains | optional |
| **W&B Inference** | serverless OpenAI-compatible inference on `deepseek-ai/DeepSeek-V4-Pro-0813`; also how stage 0 removes the GPU from the critical path | optional |
| **marimo** | the dashboard | optional; local only |

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `V2R_TRACE` | **must be exactly `1`** for any span to be emitted | unset — no telemetry |
| `WANDB_API_KEY` | W&B auth, for both Weave and Inference | unset |
| `WANDB_PROJECT` | entity/project for spans | `3m-m/Aviary-BioSim` |

`V2R_TRACE` exists deliberately. An ambient `WANDB_API_KEY` from an unrelated
project must never cause this tool to publish build-unit statements and test
output to someone's W&B account, so a key alone is not enough — telemetry
requires an explicit opt-in.

```bash
export V2R_TRACE=1
export WANDB_API_KEY=...          # wandb.ai/authorize
export WANDB_PROJECT=3m-m/Aviary-BioSim

uv run --with pyyaml --with weave \
  .claude/skills/v2r-loop/scripts/register.py close U-001
```

**`weave` is not declared in `register.py`'s PEP 723 header, on purpose.** It is
imported lazily inside `emit_span`, only when `V2R_TRACE=1`. Declaring it would
pull a large dependency into every gate invocation — including offline ones — for
a feature most runs do not use. Add `--with weave` at the call site instead.

Telemetry never fails a drain. It also never fails *silently*: a dropped span
prints one warning to stderr, because losing spans means stage 4 has nothing to
read and the learning loop goes dark.

### W&B MCP server

```bash
claude mcp add --transport http wandb https://mcp.withwandb.com/mcp \
  --scope user --header "Authorization: Bearer $WANDB_API_KEY"
```

### W&B Inference

```python
client = openai.OpenAI(
    base_url="https://api.inference.wandb.ai/v1",
    api_key=os.environ["WANDB_API_KEY"],
    project="3m-m/Aviary-BioSim",
)
MODEL = "deepseek-ai/DeepSeek-V4-Pro-0813"
```

`DeepSeek-V4-Pro` is a reasoning model: reasoning tokens count against
`max_tokens`, so a small ceiling returns `content: null` with
`finish_reason: "length"`. Budget for reasoning separately.

## Coming with the aviary environment

`fhaviary` — supplies the `Environment` contract (`reset`, `step`) the
drug-discovery environment implements. Install verified; two abstract methods.
It becomes a declared dependency of the environment package, not of `register.py`,
which stays domain-agnostic.

## Secrets

Never commit a key. **This repo is public.** Secrets live in the private
superproject's gitignored `.env`, and in Infisical (`biofm/dev`:
`WANDB_API_KEY`, `WANDB_PROJECT`). `.gitignore` here excludes `.v2r/`,
`__pycache__/`, `.pytest_cache/`, `__marimo__/` and the aiadlc coordination
markers.
