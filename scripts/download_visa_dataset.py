import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

VISA_ARCHIVE_URL = "https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar"
VISA_ARCHIVE_BYTES = 1_929_840_640
OFFICIAL_SPLIT_URL = (
    "https://raw.githubusercontent.com/amazon-science/spot-diff/main/split_csv/1cls.csv"
)


def prepare_visa_pcb1(dataset_root: Path) -> dict[str, object]:
    dataset_root.mkdir(parents=True, exist_ok=True)
    archive = dataset_root / "VisA_20220922.tar"
    archive_hash_file = dataset_root / "VisA_20220922.tar.sha256"
    archive_sha256 = _verified_download(
        VISA_ARCHIVE_URL,
        archive,
        archive_hash_file,
        expected_bytes=VISA_ARCHIVE_BYTES,
    )

    with tarfile.open(archive, mode="r:") as tar:
        members = tuple(_pcb1_members(tar))
        if not members:
            raise ValueError("Official VisA archive contains no PCB1 members")
        tar.extractall(dataset_root, members=members, filter="data")

    pcb1_roots = sorted(
        path for path in dataset_root.rglob("*") if path.is_dir() and path.name.lower() == "pcb1"
    )
    if len(pcb1_roots) != 1:
        raise ValueError("Expected exactly one extracted VisA PCB1 directory")
    pcb1_root = pcb1_roots[0]
    if not (pcb1_root / "image_anno.csv").is_file():
        raise ValueError("Extracted VisA PCB1 data is incomplete")

    split_path = dataset_root / "split_csv" / "1cls.csv"
    split_sha256 = _verified_download(
        OFFICIAL_SPLIT_URL,
        split_path,
        split_path.with_suffix(".csv.sha256"),
    )
    result = {
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_sha256,
        "pcb1_root": str(pcb1_root),
        "extracted_member_count": len(members),
        "official_split": str(split_path),
        "official_split_sha256": split_sha256,
    }
    (dataset_root / "preparation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _verified_download(
    url: str,
    destination: Path,
    checksum_path: Path,
    expected_bytes: int | None = None,
) -> str:
    if destination.is_file() and checksum_path.is_file():
        expected_hash = checksum_path.read_text(encoding="utf-8").strip().split()[0]
        if (expected_bytes is None or destination.stat().st_size == expected_bytes) and (
            _sha256(destination) == expected_hash
        ):
            return expected_hash
    if destination.is_file() and (
        expected_bytes is None or destination.stat().st_size == expected_bytes
    ):
        checksum = _sha256(destination)
        checksum_path.write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
        return checksum

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if expected_bytes is not None and temporary.stat().st_size != expected_bytes:
        raise ValueError("Downloaded VisA archive has an unexpected size")
    temporary.replace(destination)
    checksum = _sha256(destination)
    checksum_path.write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
    return checksum


def _pcb1_members(tar: tarfile.TarFile) -> tuple[tarfile.TarInfo, ...]:
    selected: list[tarfile.TarInfo] = []
    for member in tar.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise ValueError("Unsafe member found in official VisA archive")
        if any(part.lower() == "pcb1" for part in path.parts):
            selected.append(member)
    return tuple(selected)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the official VisA PCB1 subset")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/visa"))
    args = parser.parse_args()
    print(json.dumps(prepare_visa_pcb1(args.dataset_root), indent=2))


if __name__ == "__main__":
    main()
