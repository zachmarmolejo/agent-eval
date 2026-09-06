"""CLI: agent-eval run --split smoke|full|refuse|injection --model ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_eval.providers import Provider, ProviderError, get_provider
from agent_eval.report import archive_slug, format_trace_dump
from agent_eval.runner import (
    VALID_SPLITS,
    load_system_prompt,
    project_root,
    run_eval,
    write_results,
)


def load_project_env(path: Path | None = None) -> Path | None:
    """Load `.env` from the project root. Variables already in the process win."""
    target = path if path is not None else project_root() / ".env"
    if not target.is_file():
        return None
    load_dotenv(dotenv_path=target, override=False)
    return target


def _parse_ids(task: str | None, ids: str | None) -> list[str] | None:
    found: list[str] = []
    if task:
        found.append(task)
    if ids:
        found.extend(part.strip() for part in ids.split(",") if part.strip())
    return found or None


def _resolve_judge(spec: str | None, eval_provider: Provider) -> tuple[Provider | None, str | None]:
    if spec is None:
        return None, None
    if spec in {"same", ""}:
        return eval_provider, f"{eval_provider.name}:{eval_provider.model}"
    judge = get_provider(spec)
    return judge, f"{judge.name}:{judge.model}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-eval",
        description="Run the agent-eval oracle table. Default path needs no API keys.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    validate = sub.add_parser(
        "validate",
        help="validate a JSONL task dataset without running a model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    validate.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="JSONL task dataset; defaults to data/tasks.jsonl",
    )
    run = sub.add_parser(
        "run",
        help="score a split against a model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    run.add_argument(
        "--split",
        choices=VALID_SPLITS,
        default="full",
        help="full=all tasks; smoke=5 tagged; refuse / injection=those subsets",
    )
    run.add_argument(
        "--model",
        required=True,
        help="fake | openai:<id> | anthropic:<id> | ollama:<id>",
    )
    run.add_argument("--dataset", type=Path, default=None)
    run.add_argument(
        "--out",
        type=Path,
        default=Path("results/latest.md"),
        help="markdown table; json and traces are written next to it",
    )
    run.add_argument("--max-turns", type=int, default=6)
    run.add_argument(
        "--task",
        default=None,
        help="run a single task id (ignores --split)",
    )
    run.add_argument(
        "--ids",
        default=None,
        help="comma-separated task ids (ignores --split)",
    )
    run.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="run the selected tasks N times; prints median/min/max when N>1",
    )
    run.add_argument(
        "--dump-trace",
        action="store_true",
        help="print each final answer and tool list after the table",
    )
    run.add_argument(
        "--no-system",
        action="store_true",
        help="omit the default system prompt (measures the raw model)",
    )
    run.add_argument(
        "--system",
        type=Path,
        default=None,
        help="read the system prompt from this file instead of prompts/system.txt",
    )
    run.add_argument(
        "--judge",
        nargs="?",
        const="same",
        default=None,
        help="optional second-column refusal judge; omit a value to reuse --model",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "validate":
        try:
            from agent_eval.runner import validate_dataset

            count = len(validate_dataset(args.dataset))
        except (ValueError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"validated {count} tasks")
        return 0
    load_project_env()
    if args.cmd != "run":
        return 2
    try:
        ids = _parse_ids(args.task, args.ids)
        system_prompt = load_system_prompt(args.system, enabled=not args.no_system)
        provider = get_provider(args.model)
        judge, judge_label = _resolve_judge(args.judge, provider)
        result = run_eval(
            provider=provider,
            split=args.split,
            dataset=args.dataset,
            max_turns=args.max_turns,
            ids=ids,
            repeat=args.repeat,
            system_prompt=system_prompt,
            judge=judge,
            judge_label=judge_label,
        )
    except (ProviderError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    dest = write_results(result, args.out)
    sys.stdout.write(result.markdown())
    if args.dump_trace:
        sys.stdout.write("\n")
        for outcome in result.outcomes:
            sys.stdout.write(format_trace_dump(outcome))
            sys.stdout.write("\n")
    dated = dest.parent / archive_slug(result)
    print(f"wrote {dest}", file=sys.stderr)
    print(f"wrote {dest.with_suffix('.json')}", file=sys.stderr)
    print(f"wrote {dest.with_name(dest.stem + '-traces.jsonl')}", file=sys.stderr)
    print(f"archived {dated}/", file=sys.stderr)
    return 0
