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

The tool list also carries the SpendTracker built by /v2r-loop drain 1, exposed
through `as_tool()`. Every model call the agent makes is metered by a component
that an independent sealed test proved correct.

The reward channel is wired to 0.0 deliberately. aviary carries a reward because
it is an RL gym; this is tool-mediated discovery, not training, and inventing a
scalar to fill the slot would be a fabricated signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

from aviary.core import Environment, Message, Tool, ToolRequestMessage, ToolResponseMessage

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import esm_tool  # noqa: E402
from spend_tracker import SpendTracker  # noqa: E402


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

    async def reset(self) -> tuple[list[Message], list[Tool]]:
        self.state = BioSimState(self.state.max_rounds)
        self.tools = [
            Tool.from_function(esm_tool.score_variant),
            Tool.from_function(esm_tool.embed_sequence),
            self.tracker.as_tool(),
        ]
        obs = [Message(content=(
            f"{self.objective}\n\n"
            "You have tools that run a real protein language model (ESM-2) over real "
            "UniProt sequences. score_variant returns a log-likelihood ratio: negative "
            "means the model finds the substitution disruptive, and magnitude matters. "
            "Call a tool to obtain a number; do not guess one. "
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
            fn = {t.info.name: t._tool_fn for t in self.tools}[call.function.name]
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
