#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["openai", "weave"]
# ///
"""A traced scientific-reasoning pipeline.

Every stage is a @weave.op over W&B Inference, so the chain from research
question to experimental design is captured automatically — no instrumentation.
This is the half of the system Claude Code subagents cannot give us: weave
auto-patches the OpenAI SDK, so an OpenAI-compatible endpoint traces for free.

The point is not that a model can write about insulin. It is that afterwards you
can read back exactly which hypotheses it considered, which it discarded, and on
what stated grounds — and check that against known biology, because recombinant
insulin is about as well-characterised as biology gets.

Run:  uv run science/pipeline.py
Out:  science/out/*.json  (traced stage outputs)  +  science/out/paper.md
"""
import json
import os
import sys
from pathlib import Path

import openai
import weave

MODEL = os.environ.get("WANDB_INFERENCE_MODEL", "deepseek-ai/DeepSeek-V4-Pro-0813")
PROJECT = os.environ.get("WANDB_PROJECT", "3m-m/Aviary-BioSim")
OUT = Path(__file__).parent / "out"

TOPIC = (
    "Improving the soluble yield of correctly-folded recombinant human insulin "
    "produced in microbial hosts"
)

client = openai.OpenAI(
    base_url="https://api.inference.wandb.ai/v1",
    api_key=os.environ["WANDB_API_KEY"],
    project=PROJECT,
)

SYSTEM = (
    "You are a careful molecular biologist designing a study. You state what is "
    "actually known and cite real, checkable literature by author and year. You "
    "distinguish established fact from inference, and you never invent a citation. "
    "When you discard an option you say why, in one sentence."
)


def ask(prompt: str, max_tokens: int = 20000) -> str:
    """One inference call, with the reasoning budget escalated rather than guessed.

    DeepSeek-V4-Pro is a reasoning model and reasoning tokens are billed against
    max_tokens, so a ceiling sized for the ANSWER returns empty content with
    finish_reason='length'. Rather than pick a number and hope, double and retry.
    """
    budget = max_tokens
    for attempt in range(3):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": prompt}],
            max_tokens=budget,
        )
        choice = resp.choices[0]
        if choice.message.content:
            usage = resp.usage
            print(f"    ok  budget={budget:<6} used={usage.completion_tokens:<6} "
                  f"chars={len(choice.message.content)}", file=sys.stderr)
            return choice.message.content.strip()
        print(f"    reasoning consumed budget={budget} "
              f"(finish_reason={choice.finish_reason}) — doubling", file=sys.stderr)
        budget *= 2
    raise RuntimeError(f"no content after 3 escalations up to {budget // 2} tokens")


@weave.op()
def frame_question(topic: str) -> str:
    return ask(
        f"Topic: {topic}\n\n"
        "State ONE precise, falsifiable research question this topic reduces to. "
        "Then in 3-4 sentences say why this question and not an adjacent one — "
        "what makes it tractable and what makes it worth answering. Under 200 words."
    )


@weave.op()
def ground_literature(question: str) -> str:
    return ask(
        f"Research question: {question}\n\n"
        "Summarise what is genuinely established about this, in 400-600 words. "
        "Cover: the standard production routes and where each loses yield; the "
        "specific step that dominates the loss; and the two or three interventions "
        "already known to help. Cite real work by author and year. Mark anything "
        "you are inferring rather than reporting as [inference]."
    )


@weave.op()
def generate_hypotheses(question: str, background: str) -> str:
    return ask(
        f"Question: {question}\n\nBackground:\n{background}\n\n"
        "Propose exactly THREE candidate hypotheses that could improve the outcome. "
        "For each: a one-line statement, the mechanism you believe drives it, the "
        "single strongest piece of prior evidence for it, and the most likely reason "
        "it fails. Number them H1, H2, H3. Under 500 words."
    )


@weave.op()
def select_hypothesis(hypotheses: str) -> str:
    """The interpretability-relevant step: what was discarded, and why."""
    return ask(
        f"Candidate hypotheses:\n{hypotheses}\n\n"
        "Choose ONE to take forward. State the choice, then justify it against the "
        "other two explicitly — for each rejected hypothesis, one sentence on why it "
        "loses. Weigh: strength of prior evidence, cost to test, and how "
        "interpretable a negative result would be. Under 300 words."
    )


@weave.op()
def design_experiments(selection: str, background: str) -> str:
    return ask(
        f"Selected hypothesis and rationale:\n{selection}\n\nBackground:\n{background}\n\n"
        "Design the study. Give: the primary measurable outcome and how it is assayed; "
        "the experimental arms including the comparator; the controls, and what each "
        "control rules out; sample size reasoning; and the explicit result that would "
        "FALSIFY the hypothesis. Be concrete about methods. 600-900 words."
    )


@weave.op()
def draft_paper(question, background, hypotheses, selection, design) -> str:
    return ask(
        "Write a research paper in Markdown from the material below. Sections: "
        "Abstract, 1. Introduction, 2. Hypothesis, 3. Materials and Methods, "
        "4. Expected Results, 5. Discussion (including limitations and what would "
        "falsify the hypothesis), 6. References.\n\n"
        "Be honest that no data has been collected: Expected Results states what "
        "would be observed if the hypothesis holds and if it does not. Do not present "
        "predictions as findings. References must be real work you are confident "
        "exists, by author, year and title.\n\n"
        f"QUESTION:\n{question}\n\nBACKGROUND:\n{background}\n\n"
        f"HYPOTHESES:\n{hypotheses}\n\nSELECTION:\n{selection}\n\nDESIGN:\n{design}",
        max_tokens=40000,
    )


@weave.op()
def run_study(topic: str) -> dict:
    question = frame_question(topic)
    background = ground_literature(question)
    hypotheses = generate_hypotheses(question, background)
    selection = select_hypothesis(hypotheses)
    design = design_experiments(selection, background)
    paper = draft_paper(question, background, hypotheses, selection, design)
    return {
        "topic": topic, "question": question, "background": background,
        "hypotheses": hypotheses, "selection": selection, "design": design,
        "paper": paper,
    }


def main() -> int:
    weave.init(PROJECT)
    OUT.mkdir(exist_ok=True)
    result = run_study(TOPIC)
    for key, value in result.items():
        if key != "paper":
            (OUT / f"{key}.md").write_text(value if isinstance(value, str) else str(value))
    (OUT / "paper.md").write_text(result["paper"])
    (OUT / "study.json").write_text(json.dumps(result, indent=2))
    for key, value in result.items():
        print(f"  {key:12} {len(str(value)):>6} chars")
    print(f"\nwrote {OUT}")
    print(f"traces: https://wandb.ai/{PROJECT}/weave")
    return 0


if __name__ == "__main__":
    sys.exit(main())
