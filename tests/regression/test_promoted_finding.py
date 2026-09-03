"""Promoted findings: oracle must keep scoring these traces the same way."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval.oracle import score_run, validate_trace_payload
from agent_eval.runner import load_tasks

FIXTURE_DIR = Path(__file__).parent
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.stem)
def test_promoted_finding(fixture_path: Path) -> None:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    task = next(t for t in load_tasks() if t.id == payload["id"])
    trace = validate_trace_payload(payload["trace"])
    score = score_run(task, trace)
    expected = payload["expected"]
    assert score.refused is expected["refused"]
    assert score.user_ok is expected["user_ok"]
    assert score.attack_ok is expected["attack_ok"]
    if "reason_ok" in expected:
        assert score.reason_ok is expected["reason_ok"]
    assert score.composite_pass is expected["composite_pass"]
