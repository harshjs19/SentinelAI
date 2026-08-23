import argparse
import subprocess
from pathlib import Path

from modules.timeseries.config import DATASET_REVISION, DATASET_SOURCE

DEFAULT_DESTINATION = Path("datasets/utk_digital_twin_predictive_maintenance")


def download_dataset(destination: Path) -> None:
    if destination.exists():
        result = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        revision = result.stdout.strip()
        if revision != DATASET_REVISION:
            raise RuntimeError(
                f"Dataset exists at revision {revision}; expected {DATASET_REVISION}"
            )
        print(f"Dataset already prepared at {destination} ({revision})")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(destination)], check=True)
    subprocess.run(
        ["git", "-C", str(destination), "remote", "add", "origin", DATASET_SOURCE],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--depth",
            "1",
            "origin",
            DATASET_REVISION,
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"],
        check=True,
    )
    print(f"Prepared UTK dataset at {destination} ({DATASET_REVISION})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the pinned UTK predictive-maintenance dataset"
    )
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    download_dataset(args.destination)


if __name__ == "__main__":
    main()
