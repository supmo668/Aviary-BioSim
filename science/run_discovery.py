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
"""
import json
import os
import sys
from pathlib import Path

import openai
import weave
from aviary.core import Message, ToolCall, ToolRequestMessage

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from biosim_env import BioSimEnv  # noqa: E402

MODEL = os.environ.get("WANDB_INFERENCE_MODEL", "deepseek-ai/DeepSeek-V4-Pro-0813")
PROJECT = os.environ.get("WANDB_PROJECT", "3m-m/Aviary-BioSim")
OUT = Path(__file__).parent / "out" / "discovery"

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
        "completion_tokens": resp.usage.completion_tokens,
    }


@weave.op()
async def measure(env: BioSimEnv, calls: list) -> list:
    """Hand the agent's chosen measurements to the environment and run them."""
    action = ToolRequestMessage(content=None, tool_calls=[
        ToolCall.from_name(c["name"], **json.loads(c["arguments"] or "{}")) for c in calls])
    obs, reward, done, truncated = await env.step(action)
    return [o.content for o in obs]


@weave.op()
async def run_discovery() -> dict:
    env = BioSimEnv(OBJECTIVE, max_rounds=5)
    obs, tools = await env.reset()
    schema = openai_tools(tools)

    messages = [{"role": "system", "content":
                 "You are a protein scientist with a measurement instrument. Measure before "
                 "you claim. Probe deliberately: a hypothesis about which positions matter is "
                 "worth more than a scan."},
                {"role": "user", "content": obs[0].content}]

    transcript = []
    for rnd in range(1, env.state.max_rounds + 1):
        turn = agent_turn(messages, schema)
        if turn["content"]:
            print(f"\n── round {rnd} ──\n{turn['content'][:700]}", flush=True)
        if not turn["tool_calls"]:
            transcript.append({"round": rnd, "reasoning": turn["content"], "measurements": []})
            break

        names = [f"{c['name']}({c['arguments']})" for c in turn["tool_calls"]]
        print(f"   measuring: {'; '.join(n[:70] for n in names)}", flush=True)
        results = await measure(env, turn["tool_calls"])
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

    messages.append({"role": "user", "content":
                     "State your conclusion from the numbers you measured. Name the positions, "
                     "quote their scores, and say what it implies about the fold. Be brief."})
    final = agent_turn(messages, schema)
    print(f"\n── conclusion ──\n{final['content']}", flush=True)

    return {"objective": OBJECTIVE, "model": MODEL, "rounds": transcript,
            "conclusion": final["content"], "audit_trail": env.state.scored}


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
