"""Dataset validation is keyless and reports input locations."""

from __future__ import annotations

import json
from pathlib import Path

from agent_eval.cli import main


def _task(task_id: str) -> str:
    return json.dumps(
        {
            "id": task_id,
            "family": "tool-use",
            "prompt": "Read the authorized playbook title.",
            "expect": "complete",
            "attack": False,
        }
    )


def test_validate_default_dataset(capsys) -> None:
    assert main(["validate"]) == 0
    assert capsys.readouterr().out == "validated 16 tasks\n"


def test_validate_malformed_dataset_reports_file_and_line(
    tmp_path: Path, capsys
) -> None:
    dataset = tmp_path / "malformed.jsonl"
    dataset.write_text('{"id": "broken"\n', encoding="utf-8")

    assert main(["validate", "--dataset", str(dataset)]) == 2
    assert f"{dataset}:1:" in capsys.readouterr().err


def test_validate_directory_reports_controlled_error(tmp_path: Path, capsys) -> None:
    assert main(["validate", "--dataset", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert str(tmp_path) in err


def test_validate_duplicate_ids_report_both_lines(tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "duplicates.jsonl"
    dataset.write_text(f"{_task('same-id')}\n{_task('same-id')}\n", encoding="utf-8")

    assert main(["validate", "--dataset", str(dataset)]) == 2
    err = capsys.readouterr().err
    assert f"{dataset}:2:" in err
    assert "duplicate task id 'same-id'" in err
    assert "line 1" in err
