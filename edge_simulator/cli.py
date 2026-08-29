import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from edge_simulator.client import SentinelAIClient, SimulatorError
from edge_simulator.config import SimulatorConfig
from edge_simulator.formatting import (
    format_dashboard_guidance,
    format_evidence,
    format_health,
    format_history,
    format_machines,
    format_outcome,
    format_report,
    format_scenarios,
)
from edge_simulator.scenarios import SCENARIOS, list_scenarios, run_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m edge_simulator",
        description="External-only SentinelAI edge simulator and end-to-end demo runner.",
    )
    parser.add_argument(
        "--api-base-url",
        help="Override SENTINELAI_API_BASE_URL for this invocation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="List the deterministic simulator scenarios.")
    commands.add_parser("health", help="Check the SentinelAI HTTP health endpoint.")
    commands.add_parser("machines", help="List machines through the public HTTP API.")

    run = commands.add_parser("run", help="Run one simulator scenario.")
    run.add_argument("scenario", choices=sorted(SCENARIOS))
    run.add_argument("--machine-id")
    run.add_argument("--asset", type=Path, help="Local replay asset for media scenarios.")

    report = commands.add_parser("report", help="Read one stored maintenance report.")
    report.add_argument("report_id")

    evidence = commands.add_parser("evidence", help="Read authoritative stored evidence lineage.")
    evidence.add_argument("report_id")

    history = commands.add_parser("history", help="Read a machine's stored maintenance history.")
    history.add_argument("--machine-id")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--offset", type=int, default=0)

    demo = commands.add_parser("demo", help="Run the bounded end-to-end time-series demo.")
    demo.add_argument("--machine-id")
    demo.add_argument(
        "--include-idempotency",
        action="store_true",
        help="Also run the exact-replay verification scenario.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print(format_scenarios(list_scenarios()))
        return 0

    try:
        config = SimulatorConfig.from_environment(args.api_base_url)
        with SentinelAIClient(config) as client:
            health = client.health()
            if args.command == "health":
                print(format_health(health, config.api_base_url))
                return 0
            return _dispatch_connected(args, client, config, health)
    except (SimulatorError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


def _dispatch_connected(
    args: argparse.Namespace,
    client: SentinelAIClient,
    config: SimulatorConfig,
    health: str,
) -> int:
    if args.command == "machines":
        print(format_health(health, config.api_base_url))
        print()
        print(format_machines(client.list_machines()))
        return 0
    if args.command == "report":
        print(format_report(client.get_report(args.report_id)))
        return 0
    if args.command == "evidence":
        print(format_evidence(client.get_evidence(args.report_id)))
        return 0
    if args.command == "history":
        machine = client.select_machine(args.machine_id)
        print(
            format_history(
                client.get_history(machine.machine_id, limit=args.limit, offset=args.offset)
            )
        )
        return 0
    if args.command == "run":
        machine = client.select_machine(args.machine_id)
        outcome = run_scenario(
            client,
            SCENARIOS[args.scenario],
            machine.machine_id,
            asset_path=args.asset,
        )
        print(format_outcome(outcome))
        print()
        print(format_dashboard_guidance(machine, outcome.receipt.report_id))
        return 0
    if args.command == "demo":
        return _run_demo(args, client, config, health)
    raise SimulatorError(f"Unsupported command: {args.command}")


def _run_demo(
    args: argparse.Namespace,
    client: SentinelAIClient,
    config: SimulatorConfig,
    health: str,
) -> int:
    machine = client.select_machine(args.machine_id)
    outcome = run_scenario(client, SCENARIOS["timeseries_healthy"], machine.machine_id)
    print(format_health(health, config.api_base_url))
    print()
    print(format_machines((machine,)))
    print()
    print(format_outcome(outcome))
    print()
    print(format_report(client.get_report(outcome.receipt.report_id)))
    print()
    print(format_evidence(client.get_evidence(outcome.receipt.report_id)))
    print()
    print(format_history(client.get_history(machine.machine_id)))
    if args.include_idempotency:
        replay = run_scenario(client, SCENARIOS["idempotent_replay"], machine.machine_id)
        print()
        print(format_outcome(replay))
    print()
    print(format_dashboard_guidance(machine, outcome.receipt.report_id))
    return 0
