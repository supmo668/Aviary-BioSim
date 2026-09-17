"""The discovery harness meters model calls itself and stops at the ceiling.

The model is stubbed; nothing here reaches the network or loads ESM-2.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_biosim_env_budget as envtests  # noqa: E402  installs the esm_tool stub

os.environ.setdefault("WANDB_API_KEY", "test-not-a-real-key")
import run_discovery  # noqa: E402

BudgetExceeded = envtests.BudgetExceeded


@pytest.mark.parametrize("raw", [None, "0", "-1", "abc"])
def test_an_undeclared_or_meaningless_price_refuses_to_start(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("BIOSIM_USD_PER_1M_TOKENS", raising=False)
    else:
        monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", raw)
    with pytest.raises(SystemExit):
        run_discovery.usd_per_1m_tokens()


def test_a_declared_price_is_used(monkeypatch):
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", "2.5")
    assert run_discovery.usd_per_1m_tokens() == 2.5


def _turn(calls=None):
    return {"content": "thinking", "prompt_tokens": 600_000, "completion_tokens": 400_000,
            "tool_calls": calls or []}


def test_each_model_call_is_charged_from_the_providers_token_counts(monkeypatch):
    env = envtests._env(ceiling=100.0)
    monkeypatch.setattr(run_discovery, "agent_turn", lambda m, t: _turn())
    run_discovery.paid_turn(env, 3.0, "round-1", [], [])
    assert env.tracker.total() == pytest.approx(3.0)  # 1M tokens at $3 / 1M


def test_over_budget_the_harness_refuses_before_paying_for_another_call(monkeypatch):
    env = envtests._env(ceiling=1.0)
    env.charge("earlier", 5.0)
    paid = []
    monkeypatch.setattr(run_discovery, "agent_turn", lambda m, t: paid.append(1) or _turn())
    with pytest.raises(BudgetExceeded):
        run_discovery.paid_turn(env, 3.0, "round-2", [], [])
    assert paid == []


def test_a_real_rollout_stops_at_the_ceiling(monkeypatch):
    """End to end: an agent that would measure forever is stopped by spend."""
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", "1.0")
    monkeypatch.setattr(run_discovery.BioSimEnv.__init__, "__defaults__", (2.5, 5))
    call = {"id": "c1", "name": "score_variant",
            "arguments": '{"accession": "P01308", "mutation": "C7S"}'}
    model_calls = []
    monkeypatch.setattr(run_discovery, "agent_turn",
                        lambda m, t: model_calls.append(1) or _turn([call]))
    envtests.CALLS.clear()

    result = asyncio.run(run_discovery.run_discovery())

    assert result["stopped"], "the rollout must record why it stopped"
    assert result["conclusion"] is None
    # $1 per model call against a $2.50 ceiling: calls 1-3 are paid, the third crosses,
    # so its measurement is refused and no further model call is made.
    assert len(model_calls) == 3
    assert envtests.CALLS == ["score_variant:C7S"] * 2
    refused = result["rounds"][-1]
    assert refused["round"] == 3 and "refused" in refused, \
        "the refused measurement must be visible in the transcript, not silently skipped"
    assert result["spend_usd"] == pytest.approx(3.0)
    assert result["ceiling_usd"] == pytest.approx(2.5)
