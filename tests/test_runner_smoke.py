"""Smoke runner and dataset shape. Never needs API keys."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_eval.oracle import Task
from agent_eval.providers import FakeProvider, ProviderError, get_provider
from agent_eval.report import archive_slug
from agent_eval.runner import load_system_prompt, load_tasks, run_eval, write_results


def test_load_dataset_and_schema() -> None:
    tasks = load_tasks(split="full")
    assert len(tasks) == 16
    for task in tasks:
        assert task.expect in {"complete", "refuse"}
        assert isinstance(task.attack, bool)
        assert task.family in {"tool-use", "cyber-capability"}


def test_dataset_mix() -> None:
    tasks = load_tasks(split="full")

    def count(family: str, expect: str, attack: bool) -> int:
        return sum(
            1
            for t in tasks
            if t.family == family and t.expect == expect and t.attack is attack
        )

    assert count("tool-use", "complete", True) == 7
    assert count("tool-use", "complete", False) == 3
    assert count("tool-use", "refuse", True) == 3
    assert count("cyber-capability", "complete", False) == 3
    assert any("tool-return" in t.tags for t in tasks)
    oncall = next(t for t in tasks if t.id == "tu-oncall-page")
    assert "STEALER_OK" in oncall.prompt
    assert oncall.oracle.attack_sentinels == ["STEALER_OK"]


def test_smoke_split_is_five() -> None:
    smoke = load_tasks(split="smoke")
    assert len(smoke) == 5
    assert all("smoke" in t.tags for t in smoke)


def test_smoke_eval_fake_no_keys(tmp_path: Path) -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OLLAMA_API_KEY", None)
    result = run_eval(provider=FakeProvider(), split="smoke")
    assert len(result.scores) == 5
    assert result.metrics.asr == 0.0
    assert result.metrics.correct_refusal == 1.0
    assert result.metrics.over_refusal == 0.0
    assert all(s.composite_pass for s in result.scores)
    dest = write_results(result, tmp_path / "latest.md")
    text = dest.read_text(encoding="utf-8")
    assert "| ASR |" in text
    assert "| correct refusal |" in text
    assert "| over-refusal |" in text
    assert (tmp_path / "latest.json").is_file()
    assert (tmp_path / "latest-traces.jsonl").is_file()
    archive = tmp_path / archive_slug(result)
    assert (archive / "report.md").is_file()
    assert (archive / "traces.jsonl").is_file()
    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["asr"] == 0.0
    assert payload["n"] == 5


def test_full_eval_fake_is_clean() -> None:
    result = run_eval(provider=get_provider("fake"), split="full")
    assert len(result.scores) == 16
    assert result.metrics.asr == 0.0
    assert result.metrics.asr_n == 10
    assert result.metrics.correct_refusal == 1.0
    assert result.metrics.correct_refusal_n == 3
    assert result.metrics.over_refusal == 0.0
    assert result.metrics.over_refusal_n == 13
    assert all(s.composite_pass for s in result.scores)


def test_refuse_and_injection_splits() -> None:
    refuse = load_tasks(split="refuse")
    assert [t.id for t in refuse] == ["tu-no-roe", "tu-usb-offscope", "tu-third-party"]
    injection = load_tasks(split="injection")
    assert all(t.attack for t in injection)
    assert len(injection) == 10


def test_ids_filter_and_unknown() -> None:
    one = load_tasks(ids=["tu-no-roe"])
    assert [t.id for t in one] == ["tu-no-roe"]
    with pytest.raises(ValueError, match="no-such-task"):
        load_tasks(ids=["no-such-task"])


def test_single_task_eval_and_repeat() -> None:
    result = run_eval(provider=FakeProvider(), ids=["tu-no-roe"], repeat=2)
    assert result.repeat == 2
    assert result.repeat_summary is not None
    assert result.repeat_summary.n == 2
    assert result.repeat_summary.correct_refusal["median"] == 1.0
    assert len(result.outcomes) == 2
    assert [o.repeat for o in result.outcomes] == [0, 1]


def test_system_prompt_loads_from_repo() -> None:
    text = load_system_prompt()
    assert text is not None
    assert "stub tools" in text
    assert load_system_prompt(enabled=False) is None


def test_optional_judge_is_second_column_only() -> None:
    result = run_eval(
        provider=FakeProvider(),
        split="smoke",
        judge=FakeProvider(),
        judge_label="fake:scripted",
    )
    assert result.judge == "fake:scripted"
    assert result.metrics.asr == 0.0
    assert result.metrics.correct_refusal == 1.0
    assert all(s.judge_refused is not None for s in result.scores)


def test_provider_error_is_fail_soft() -> None:
    class Boom:
        name = "fake"
        model = "boom"

        def complete(self, messages, tools=None, task_id=None):
            raise ProviderError("cloud down")

    result = run_eval(provider=Boom(), ids=["cc-cve-extract"])
    assert result.scores[0].composite_pass is False
    assert "provider: cloud down" in result.scores[0].notes


def test_cli_single_task(tmp_path: Path) -> None:
    from agent_eval.cli import main
    from agent_eval.runner import default_dataset_path

    code = main(
        [
            "run",
            "--model",
            "fake",
            "--task",
            "tu-no-roe",
            "--dump-trace",
            "--out",
            str(tmp_path / "latest.md"),
            "--dataset",
            str(default_dataset_path()),
        ]
    )
    assert code == 0
    text = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "tu-no-roe" in text
    traces = (tmp_path / "latest-traces.jsonl").read_text(encoding="utf-8")
    assert "NO_ROE_OK" not in json.loads(traces.splitlines()[0])["final_answer"]


def test_task_ids_are_stable() -> None:
    ids = [t.id for t in load_tasks(split="full")]
    assert ids == [
        "tu-roe-scope",
        "tu-oncall-page",
        "tu-playbook-name",
        "tu-tabletop-title",
        "tu-detect-rule",
        "tu-scope-hosts",
        "tu-ticket-inject",
        "tu-vuln-intake",
        "tu-public-advisory",
        "tu-tool-allowlist",
        "tu-no-roe",
        "tu-usb-offscope",
        "tu-third-party",
        "cc-cve-extract",
        "cc-affected-component",
        "cc-scope-verdict",
    ]
    assert all(isinstance(t, Task) for t in load_tasks())
