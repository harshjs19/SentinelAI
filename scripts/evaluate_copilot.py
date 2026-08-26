import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from evaluation.copilot_v1 import (  # noqa: E402
    MAX_REPETITIONS,
    add_post_hardening_result,
    build_evaluation_result,
    load_cases,
    run_live_evaluation,
    run_offline_evaluation,
    write_json,
    write_review_packet,
)
from modules.copilot.generator import MaintenanceGenerationError  # noqa: E402
from modules.copilot.openai_generator import OpenAIMaintenanceGenerator  # noqa: E402

DEFAULT_CASES_PATH = REPOSITORY_ROOT / "evaluation" / "copilot_cases.json"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "evaluation" / "copilot_runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the bounded synthetic Maintenance Copilot V1 evaluation.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline-only",
        action="store_true",
        help="Run only deterministic offline adversarial evaluation (the safe default).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Also run the explicit live OpenAI evaluation after the offline suite.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        choices=range(1, MAX_REPETITIONS + 1),
        default=MAX_REPETITIONS,
        metavar="{1,2,3}",
        help="Live repetitions per frozen case; formal promotion requires 3.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Explicit path for sanitized machine-readable results; otherwise do not write.",
    )
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=DEFAULT_REVIEW_DIRECTORY,
        help="Ignored directory for the local live human-review packet.",
    )
    parser.add_argument(
        "--show-progress",
        action="store_true",
        help="Print case/repetition progress without printing prompts or drafts.",
    )
    parser.add_argument(
        "--post-hardening",
        action="store_true",
        help="Append the one allowed complete post-hardening run to an existing baseline.",
    )
    return parser.parse_args()


async def evaluate(args: argparse.Namespace) -> tuple[dict[str, object], Path | None]:
    cases = load_cases(DEFAULT_CASES_PATH)
    offline = await run_offline_evaluation(cases)
    live = None
    review_path = None
    live_execution_status = "DEFERRED_NOT_RUN" if args.post_hardening else "NOT_REQUESTED"
    if args.live:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key.strip():
            live_execution_status = "NOT_RUN_MISSING_CREDENTIALS"
        else:
            try:
                generator = OpenAIMaintenanceGenerator(api_key=api_key)
                live, review_records = await run_live_evaluation(
                    cases,
                    generator,
                    repetitions=args.repetitions,
                    api_key=api_key,
                    show_progress=args.show_progress,
                )
            except MaintenanceGenerationError as error:
                live_execution_status = f"NOT_RUN_PROVIDER_{error.code.value.upper()}"
            else:
                live_execution_status = "COMPLETED"
                review_path = write_review_packet(args.review_dir, review_records)
    result = build_evaluation_result(
        repository_root=REPOSITORY_ROOT,
        cases=cases,
        offline=offline,
        live=live,
        live_execution_status=live_execution_status,
    )
    return result, review_path


def main() -> int:
    args = parse_args()
    if args.post_hardening and args.output is None:
        raise SystemExit("--post-hardening requires --output")
    result, review_path = asyncio.run(evaluate(args))
    if args.output is not None:
        output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
        if output.exists():
            existing = json.loads(output.read_text(encoding="utf-8"))
            if args.post_hardening:
                result = add_post_hardening_result(existing, result)
            elif existing.get("baseline", {}).get("live_execution_status") == "COMPLETED":
                raise SystemExit(
                    "Refusing to overwrite a completed frozen baseline; use "
                    "--post-hardening for the one allowed rerun"
                )
        write_json(output, result)
        print(f"Sanitized results: {output}")
    active_run = result["post_hardening"] or result["baseline"]
    print(f"Offline status: {active_run['offline']['status']}")
    print(f"Live execution: {active_run['live_execution_status']}")
    print(f"Overall automated status: {result['overall_automated_status']}")
    if review_path is not None:
        print(f"Ignored human-review packet: {review_path}")
    return 0 if result["overall_automated_status"] in ("PASS", "LIVE_NOT_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
