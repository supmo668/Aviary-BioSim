#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["fhaviary", "torch", "transformers", "requests", "openai", "weave"]
# ///
"""The discovery loop: an agent measuring, not guessing.

The agent is given BioSimEnv's tools and an objective. It chooses which residues
to probe, the environment runs ESM-2 on the real sequence, and the agent sees
the actual number before choosing again. Every round is a @weave.op, so the
trace records which measurement it asked for and what it did with the answer.

Nothing here is seeded with the expected result. The agent is pointed at a
question whose answer is independently known — that the disulfide cysteines are
load-bearing — and has to find it by measuring.

Spend is metered by the harness, not by the agent: every model call is charged to
the environment's ledger from the provider's own token counts, and the rollout
refuses before paying for another call once the ceiling is passed. The operator
must declare their provider's price per million tokens in BIOSIM_USD_PER_1M_TOKENS.
There is no default and no figure in this repo, because a guessed or zero price
would make the budget guard pass while metering nothing.
"""
import json
import math
import os
import sys
from pathlib import Path

import openai
import weave
from aviary.core import Message, ToolCall, ToolRequestMessage

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from biosim_env import BioSimEnv  # noqa: E402
from spend_tracker import BudgetExceeded  # noqa: E402

MODEL = os.environ.get("WANDB_INFERENCE_MODEL", "deepseek-ai/DeepSeek-V4-Pro-0813")
PROJECT = os.environ.get("WANDB_PROJECT", "3m-m/Aviary-BioSim")
OUT = Path(__file__).parent / "out" / "discovery"


def usd_per_1m_tokens() -> float:
    """The declared token price. Refuses to guess: no price means no budget guard."""
    raw = os.environ.get("BIOSIM_USD_PER_1M_TOKENS")
    # Empty counts as unset: BIOSIM_USD_PER_1M_TOKENS="$PRICE" with PRICE unset is "".
    if raw is None or not raw.strip():
        sys.exit("BIOSIM_USD_PER_1M_TOKENS is not set. Declare the model's price per "
                 "million tokens; the budget cannot be enforced without it.")
    try:
        price = float(raw)
    except ValueError:
        sys.exit(f"BIOSIM_USD_PER_1M_TOKENS={raw!r} is not a number.")
    if not (math.isfinite(price) and price > 0):
        sys.exit(f"BIOSIM_USD_PER_1M_TOKENS={raw!r} must be finite and positive; a zero or infinite price meters nothing.")
    return price

OBJECTIVE = (
    "Human preproinsulin is UniProt P01308, 110 residues. Identify which residues "
    "are least tolerant of substitution, and say what that implies about how the "
    "protein folds. Probe specific positions with score_variant and reason from the "
    "numbers you get back. Do not assert a score you have not measured."
)

client = openai.OpenAI(
    base_url="https://api.inference.wandb.ai/v1",
    api_key=os.environ["WANDB_API_KEY"],
    project=PROJECT,
)


def openai_tools(tools):
    return [{"type": "function", "function": {
        "name": t.info.name,
        "description": t.info.description,
        "parameters": t.info.parameters.model_dump(exclude_none=True),
    }} for t in tools]


@weave.op()
def agent_turn(messages: list, tools: list) -> dict:
    """One model call. Returns the assistant message as a plain dict."""
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, tools=tools, max_tokens=20000)
    m = resp.choices[0].message
    return {
        "content": m.content,
        "tool_calls": [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                       for c in (m.tool_calls or [])],
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
    }


def paid_turn(env: BioSimEnv, price: float, call_id: str, messages: list, tools: list) -> dict:
    """Refuse before paying for a model call once over budget; charge it after."""
    env.tracker.check()
    turn = agent_turn(messages, tools)
    tokens = turn["prompt_tokens"] + turn["completion_tokens"]
    env.charge(call_id, tokens * price / 1_000_000)
    return turn


@weave.op()
async def measure(env: BioSimEnv, calls: list) -> list:
    """Hand the agent's chosen measurements to the environment and run them.

    Returns one result per requested call, in the order the agent asked for them,
    matched by call id. The environment answers valid calls before invalid ones, so
    pairing its responses by position would give one call's result to another.

    Each call's arguments are parsed on their own: a model that emits truncated or
    non-object JSON gets a tool error for that call, and the rest of the batch runs.
    """
    results: dict = {}
    requests = []
    for c in calls:
        try:
            args = json.loads(c["arguments"] or "{}")
            if not isinstance(args, dict):
                raise ValueError(f"expected a JSON object, got {type(args).__name__}")
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            results[c["id"]] = f"tool error: unparseable arguments: {exc}"
            continue
        requests.append(ToolCall.from_name(c["name"], id=c["id"], **args))
    if requests:
        obs, reward, done, truncated = await env.step(
            ToolRequestMessage(content=None, tool_calls=requests))
        for o in obs:
            results[o.tool_call_id] = o.content
    return [results.get(c["id"], "tool error: no response") for c in calls]


@weave.op()
async def run_discovery() -> dict:
    price = usd_per_1m_tokens()
    env = BioSimEnv(OBJECTIVE, max_rounds=5)
    obs, tools = await env.reset()
    schema = openai_tools(tools)

    messages = [{"role": "system", "content":
                 "You are a protein scientist with a measurement instrument. Measure before "
                 "you claim. Probe deliberately: a hypothesis about which positions matter is "
                 "worth more than a scan."},
                {"role": "user", "content": obs[0].content}]

    transcript = []
    stopped = None
    for rnd in range(1, env.state.max_rounds + 1):
        try:
            turn = paid_turn(env, price, f"round-{rnd}", messages, schema)
        except BudgetExceeded as exc:
            stopped = str(exc)
            break
        if turn["content"]:
            print(f"\n── round {rnd} ──\n{turn['content'][:700]}", flush=True)
        if not turn["tool_calls"]:
            transcript.append({"round": rnd, "reasoning": turn["content"], "measurements": []})
            break

        names = [f"{c['name']}({c['arguments']})" for c in turn["tool_calls"]]
        print(f"   measuring: {'; '.join(n[:70] for n in names)}", flush=True)
        try:
            results = await measure(env, turn["tool_calls"])
        except BudgetExceeded as exc:
            stopped = str(exc)
            transcript.append({"round": rnd, "reasoning": turn["content"],
                               "requested": names, "refused": stopped})
            break
        for r in results:
            print(f"     -> {r}", flush=True)

        messages.append({"role": "assistant", "content": turn["content"] or "",
                         "tool_calls": [{"id": c["id"], "type": "function",
                                         "function": {"name": c["name"],
                                                      "arguments": c["arguments"]}}
                                        for c in turn["tool_calls"]]})
        for c, r in zip(turn["tool_calls"], results):
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": str(r)})

        transcript.append({"round": rnd, "reasoning": turn["content"],
                           "requested": names, "results": results,
                           "completion_tokens": turn["completion_tokens"]})

    conclusion = None
    if stopped is None:
        messages.append({"role": "user", "content":
                         "State your conclusion from the numbers you measured. Name the positions, "
                         "quote their scores, and say what it implies about the fold. Be brief."})
        try:
            final = paid_turn(env, price, "conclusion", messages, schema)
            conclusion = final["content"]
            print(f"\n── conclusion ──\n{conclusion}", flush=True)
        except BudgetExceeded as exc:
            stopped = str(exc)
    if stopped:
        print(f"\n── stopped: {stopped} ──", flush=True)

    return {"objective": OBJECTIVE, "model": MODEL, "rounds": transcript,
            "conclusion": conclusion, "audit_trail": env.state.scored,
            "spend_usd": env.tracker.total(), "ceiling_usd": env.tracker.ceiling_usd,
            "stopped": stopped}


def main() -> int:
    import asyncio
    weave.init(PROJECT)
    OUT.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run_discovery())
    (OUT / "discovery.json").write_text(json.dumps(result, indent=2))
    print(f"\nwrote {OUT / 'discovery.json'}  ({len(result['audit_trail'])} measurements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
