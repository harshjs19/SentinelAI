import ast
import subprocess
from pathlib import Path

import pytest

from edge_simulator.cli import build_parser, main

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_ROOT = REPOSITORY_ROOT / "edge_simulator"
PROHIBITED_IMPORT_ROOTS = {
    "ai_core",
    "backend",
    "domain",
    "inference",
    "modules",
    "shared",
}
MEDIA_SUFFIXES = {".wav", ".mp3", ".flac", ".jpg", ".jpeg", ".png", ".mp4", ".avi"}


def test_simulator_has_no_prohibited_internal_imports() -> None:
    imports: list[tuple[Path, str]] = []
    for path in SIMULATOR_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend((path, alias.name.split(".", 1)[0]) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((path, node.module.split(".", 1)[0]))

    violations = [(path.name, root) for path, root in imports if root in PROHIBITED_IMPORT_ROOTS]
    assert violations == []


def test_simulator_source_contains_no_hardware_or_streaming_dependencies() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in SIMULATOR_ROOT.rglob("*.py")
    )
    prohibited_dependencies = (
        "import gpio",
        "import picamera",
        "import paho",
        "import kafka",
        "import websockets",
        "from gpio",
        "from picamera",
        "from paho",
        "from kafka",
        "from websockets",
    )
    assert all(dependency not in source for dependency in prohibited_dependencies)


def test_cli_surface_matches_documented_commands() -> None:
    parser = build_parser()
    commands = next(
        action
        for action in parser._actions
        if action.dest == "command"  # noqa: SLF001
    )
    assert set(commands.choices) == {
        "list",
        "health",
        "machines",
        "run",
        "report",
        "evidence",
        "history",
        "demo",
    }


def test_list_command_is_offline_and_labels_all_inputs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["list"]) == 0
    output = capsys.readouterr().out
    assert output.count("SIMULATED INPUT") == 5
    assert output.count("RECORDED REPLAY") == 3
    assert "PHYSICAL LIVE SENSOR" not in output


def test_demo_asset_directories_are_targeted_by_gitignore() -> None:
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "demo_assets/audio/" in gitignore
    assert "demo_assets/vision/" in gitignore
    assert "demo_assets/thermal/" in gitignore


def test_no_recorded_media_is_tracked_in_demo_or_dataset_directories() -> None:
    result = subprocess.run(
        ["git", "ls-files", "demo_assets", "datasets"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_media = [
        path for path in result.stdout.splitlines() if Path(path).suffix.lower() in MEDIA_SUFFIXES
    ]
    assert tracked_media == []


def test_documentation_keeps_physical_hardware_and_provider_boundaries_explicit() -> None:
    documentation = (REPOSITORY_ROOT / "docs" / "edge_simulator.md").read_text(encoding="utf-8")
    normalized = " ".join(documentation.split())
    assert "PHYSICAL LIVE SENSOR" in documentation
    assert "RaspberryPiSource" in documentation
    assert "no Raspberry Pi deployment claim" in normalized
    assert "No `OPENAI_API_KEY` is needed" in documentation
    assert "no fusion" in documentation.lower()
