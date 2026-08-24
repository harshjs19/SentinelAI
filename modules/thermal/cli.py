import argparse
import json
from pathlib import Path

from modules.thermal.config import ThermalTrainingConfig
from modules.thermal.training import train_thermal_baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the SentinelAI Thermal V1 baseline")
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    defaults = ThermalTrainingConfig()
    config = ThermalTrainingConfig(
        dataset_root=args.dataset_root or defaults.dataset_root,
        device=args.device,
        batch_size=args.batch_size,
    )
    result = train_thermal_baseline(config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
