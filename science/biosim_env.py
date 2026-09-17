#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["fhaviary", "torch", "transformers", "requests"]
# ///
"""BioSimEnv — an aviary Environment whose tools do real biology.

aviary's contract is two abstract methods. What matters here is what sits behind
them: `step` does not simulate, it runs ESM-2 over a real UniProt sequence and
returns the number that comes out. An agent using this environment is not
reasoning about protein stability, it is measuring it.

The environment refuses to run tools once recorded spend passes a ceiling, using
the SpendTracker built by /v2r-loop drain 1. Two halves, stated separately because
only one is sealed-tested:

- The COMPONENT — `SpendTracker` recording, totalling and refusing past its ceiling
  (`demo/spend_tracker.py`) — is covered by independent sealed tests.
- The ENFORCEMENT here is not covered by those tests; it is covered by
  `science/tests/test_biosim_env_budget.py`. `step()` checks the ceiling before every
  tool call, outside the tool-error handler, so an over-budget rollout stops with
  `BudgetExceeded` instead of reporting it as a tool failure and carrying on.

The environment does not observe model calls. Spend reaches the ledger only through
`charge()`, called by whatever pays for them — the rollout harness — so a harness
that never calls `charge()` gets no budget at all. The agent, the party being
metered, cannot write the ledger: it is offered a read-only `spend_remaining` tool,
and no tool that records spend.

The reward channel is wired to 0.0 deliberately. aviary carries a reward because
it is an RL gym; this is tool-mediated discovery, not training, and inventing a
scalar to fill the slot would be a fabricated signal.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from aviary.core import Environment, Message, Tool, ToolRequestMessage, ToolResponseMessage

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import esm_tool  # noqa: E402
from spend_tracker import SpendTracker  # noqa: E402


def _valid_cost(cost_usd) -> float:
    """A cost the ledger may accept: a finite, non-negative number, not a bool.

    Anything else is refused rather than coerced. A negative or NaN cost is not a
    rounding problem, it is a way to switch the budget off: a negative lowers the
    total below the ceiling, and a NaN total makes `total > ceiling` false forever.
    """
    if isinstance(cost_usd, bool):
        raise ValueError(f"cost_usd must be a number, not {cost_usd!r}")
    try:
        cost = float(cost_usd)
    except (TypeError, ValueError):
        raise ValueError(f"cost_usd must be a number, not {cost_usd!r}") from None
    if not math.isfinite(cost) or cost < 0:
        raise ValueError(f"cost_usd must be finite and non-negative, not {cost_usd!r}")
    return cost


class BioSimState:
    """What the environment knows. Hidden from the agent except via observations."""

    def __init__(self, max_rounds: int) -> None:
        self.round = 0
        self.max_rounds = max_rounds
        self.done = False
        self.scored: list[str] = []   # every tool result, in order — the audit trail


class BioSimEnv(Environment[BioSimState]):
    """A protein-variant workbench exposed as an aviary Environment."""

    def __init__(self, objective: str, ceiling_usd: float = 5.0, max_rounds: int = 6) -> None:
        self.objective = objective
        self.tracker = SpendTracker(ceiling_usd)
        self.state = BioSimState(max_rounds)
        self.tools: list[Tool] = []
        # name -> callable, held here rather than read back off Tool: aviary exposes
        # no public accessor for a Tool's function, only the private `_tool_fn`.
        self._fns: dict = {}

    def charge(self, call_id: str, cost_usd: float) -> None:
        """Record spend on the environment's own ledger — the harness path.

        Call this for every model call the rollout pays for. It records only;
        the refusal happens in `step()`, before the next tool runs. A nonsense cost
        raises ValueError here — a harness bug should be loud, not silently absorbed.
        """
        self.tracker.record(call_id, _valid_cost(cost_usd))

    def spend_remaining(self) -> float:
        """Report how much of the spend budget is left, in US dollars.

        Read-only: this reports the ledger and never writes it. The value is the
        ceiling minus recorded spend, never rounded up. Through the agent's tool it
        is never negative: step() refuses every tool call, this one included, once
        spend passes the ceiling, so an over-budget agent gets BudgetExceeded rather
        than a number. Harness callers can see a negative value.
        """
        return self.tracker.ceiling_usd - self.tracker.total()

    async def reset(self) -> tuple[list[Message], list[Tool]]:
        self.state = BioSimState(self.state.max_rounds)
        # One list builds both the offered tools and the callables that run them, so
        # the two cannot drift. No entry writes the ledger: spend is the harness's to
        # record, through charge().
        fns = [esm_tool.score_variant, esm_tool.embed_sequence, self.spend_remaining]
        self.tools = [Tool.from_function(fn) for fn in fns]
        self._fns = {tool.info.name: fn for tool, fn in zip(self.tools, fns)}
        obs = [Message(content=(
            f"{self.objective}\n\n"
            "You have tools that run a real protein language model (ESM-2) over real "
            "UniProt sequences. score_variant returns a log-likelihood ratio: negative "
            "means the model finds the substitution disruptive, and magnitude matters. "
            "Call a tool to obtain a number; do not guess one. "
            "spend_remaining reports how much of your budget is left. "
            f"You have {self.state.max_rounds} rounds."
        ))]
        return obs, self.tools

    async def step(self, action: Message) -> tuple[list[Message], float, bool, bool]:
        self.state.round += 1
        if not isinstance(action, ToolRequestMessage) or not action.tool_calls:
            return self.default_no_tool_calls_response

        valid, invalid = self.filter_invalid_tool_calls(action)
        responses: list[Message] = []
        for call in valid.tool_calls:
            # Refuse BEFORE the tool runs, and OUTSIDE the handler below. BudgetExceeded
            # is a RuntimeError, so a check inside that `except Exception` would turn the
            # refusal into a "tool error" string and let the rollout continue.
            self.tracker.check()
            fn = self._fns[call.function.name]
            try:
                result = fn(**call.function.arguments)
            except Exception as exc:  # a tool that fails says so; it never returns a number
                result = f"tool error: {type(exc).__name__}: {exc}"
            self.state.scored.append(f"{call.function.name}({call.function.arguments}) -> {result}")
            responses.append(ToolResponseMessage.from_call(call, str(result)))
        for call in invalid.tool_calls:
            responses.append(ToolResponseMessage.from_call(call, "no such tool"))

        truncated = self.state.round >= self.state.max_rounds
        self.state.done = truncated
        # Reward stays 0.0 on purpose — see the module docstring.
        return responses, 0.0, self.state.done, truncated

    def export_frame(self):
        from aviary.core import Frame
        return Frame(state={"round": self.state.round, "measurements": len(self.state.scored)},
                     info={"objective": self.objective})
