import argparse
import json

from modules.vision.config import VisionTrainingConfig
from modules.vision.training import train_vision


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate Vision V1 on VisA PCB1")
    parser.parse_args()
    outcome = train_vision(VisionTrainingConfig())
    print(
        json.dumps(
            {
                "global": outcome.global_evaluation.to_dict(),
                "patch": outcome.patch_evaluation.to_dict(),
                "localization": outcome.localization_evaluation.to_dict(),
                "artifact": outcome.artifact_path,
                "evaluation": outcome.evaluation_path,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
