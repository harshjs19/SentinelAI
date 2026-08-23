from pathlib import Path

from modules.vision.data import VisionSample, split_normal_training


def test_fit_calibration_split_is_deterministic_and_keeps_sequence_blocks_together() -> None:
    samples = tuple(
        VisionSample(Path(f"pcb1/Data/Images/Normal/{index:04d}.JPG"), None, "train", "normal")
        for index in range(40)
    )

    first_fit, first_calibration = split_normal_training(samples, 0.8, 42)
    second_fit, second_calibration = split_normal_training(samples, 0.8, 42)
    fit_blocks = {int(sample.image_path.stem) // 10 for sample in first_fit}
    calibration_blocks = {int(sample.image_path.stem) // 10 for sample in first_calibration}

    assert first_fit == second_fit
    assert first_calibration == second_calibration
    assert fit_blocks.isdisjoint(calibration_blocks)
    assert len(first_fit) + len(first_calibration) == 40
