"""Opt-in live smoke for the structured Maintenance Copilot provider boundary."""

import argparse
import asyncio
import json
import os
from dataclasses import dataclass

from domain.enums.modality import Modality
from modules.copilot.context import PreparedCopilotRequest
from modules.copilot.contracts import CopilotIntent, SafetyViolationCode, ValidationResult
from modules.copilot.generator import MaintenanceGenerationError
from modules.copilot.openai_generator import OpenAIMaintenanceGenerator
from modules.copilot.policy import decide_request_policy
from modules.copilot.validation import MaintenanceSafetyValidator
from tests.copilot.support import make_prepared


@dataclass(frozen=True)
class SmokeCase:
    name: str
    prepared: PreparedCopilotRequest


def _cases() -> tuple[SmokeCase, ...]:
    return (
        SmokeCase("bearing-fault-explanation", make_prepared("bearing_fault")),
        SmokeCase(
            "visual-anomaly-explanation",
            make_prepared("visual_anomaly", modality=Modality.VISION),
        ),
        SmokeCase(
            "bearing-inspection-consideration",
            make_prepared(
                "bearing_fault",
                intent=CopilotIntent.INSPECTION_CONSIDERATIONS,
            ),
        ),
    )


async def _run(*, api_key: str, show_draft: bool) -> bool:
    generator = OpenAIMaintenanceGenerator(api_key=api_key)
    validator = MaintenanceSafetyValidator()
    all_passed = True
    for case in _cases():
        decision = decide_request_policy(case.prepared)
        if not decision.provider_required:
            print(f"FAIL {case.name}: deterministic policy did not permit provider generation")
            all_passed = False
            continue
        try:
            result = await generator.generate(case.prepared.context)
        except MaintenanceGenerationError as error:
            print(f"FAIL {case.name}: category={error.code.value}")
            all_passed = False
            continue

        validation = validator.validate(result.draft, case.prepared)
        model_match = result.response_model == result.requested_model
        passed = validation.valid and model_match
        all_passed = all_passed and passed
        violations = ",".join(code.value for code in _violation_codes(validation)) or "none"
        print(
            f"{'PASS' if passed else 'FAIL'} {case.name}: "
            f"requested_model={result.requested_model} response_model={result.response_model} "
            f"response_id={result.response_id} latency_ms={result.latency_ms} "
            f"input_tokens={result.input_tokens} output_tokens={result.output_tokens} "
            f"parsed=yes validator_passed={validation.valid} violations={violations} "
            f"model_match={model_match}"
        )
        if show_draft:
            print(json.dumps(result.draft.model_dump(mode="json"), indent=2, sort_keys=True))
    return all_passed


def _violation_codes(validation: ValidationResult) -> tuple[SafetyViolationCode, ...]:
    return tuple(dict.fromkeys(violation.code for violation in validation.violations))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-draft",
        action="store_true",
        help="print parsed synthetic drafts after each live response",
    )
    arguments = parser.parse_args()
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None or not api_key.strip():
        print("Live Copilot provider smoke not configured: OPENAI_API_KEY is not set.")
        return 0
    return 0 if asyncio.run(_run(api_key=api_key, show_draft=arguments.show_draft)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
