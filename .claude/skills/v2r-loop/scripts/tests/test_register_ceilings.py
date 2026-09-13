import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_within_ceilings_returns_none(register_data):
    assert register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0) is None


def test_wall_clock_breach_is_reported(register_data):
    started = time.time() - 99_999
    reason = register.check_ceilings(register_data, started_at=started, spend_usd=0.0)
    assert reason is not None
    assert "wall clock" in reason


def test_spend_breach_is_reported(register_data):
    reason = register.check_ceilings(register_data, started_at=time.time(), spend_usd=999.0)
    assert reason is not None
    assert "spend" in reason


def test_drain_cap_breach_is_reported(register_data):
    register_data["run"]["drain"] = 4
    reason = register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0)
    assert reason is not None
    assert "drain" in reason


def test_attempts_exhausted_is_a_separate_predicate(register_data):
    unit = register_data["units"][0]
    unit["attempts"] = 3
    assert register.attempts_exhausted(unit, register_data) is True
    unit["attempts"] = 2
    assert register.attempts_exhausted(unit, register_data) is False


def test_exhausted_attempts_do_not_breach_a_ceiling(register_data):
    register_data["units"][0]["attempts"] = 99
    assert register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0) is None
