import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

DOWNLOAD_URL = "https://zenodo.org/api/records/6529888/files/bearing.zip/content"
EXPECTED_MD5 = "6381a00f9efc0ced779c8ad847e4ff59"


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_bearing_subset(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "bearing.zip"
    if not archive.is_file() or _md5(archive) != EXPECTED_MD5:
        partial = archive.with_suffix(".zip.part")
        with urllib.request.urlopen(DOWNLOAD_URL) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        if _md5(partial) != EXPECTED_MD5:
            raise ValueError("Downloaded MIMII DG bearing archive checksum does not match Zenodo")
        partial.replace(archive)

    extracted = destination / "bearing"
    if not extracted.is_dir():
        destination_root = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination_root):
                    raise ValueError(f"Unsafe archive member: {member.filename}")
            bundle.extractall(destination)
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the official MIMII DG bearing subset")
    parser.add_argument("--destination", type=Path, default=Path("datasets/mimii_dg"))
    args = parser.parse_args()
    path = download_bearing_subset(args.destination)
    print(f"MIMII DG bearing subset ready at {path}")


if __name__ == "__main__":
    main()
