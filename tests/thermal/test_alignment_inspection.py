import hashlib
import io
import math

import pytest

from scripts.inspect_cora_alignment import (
    DATASET_DOI,
    DATASET_TITLE,
    DATASET_VERSION,
    ManifestFile,
    _download_original,
    _read_numeric_vector,
    alignment_blockers,
    audit_manifest,
    ensure_payload_inspection_allowed,
    find_alignment_candidates,
    find_timing_files,
    parse_file_ddi,
    parse_version_manifest,
    validate_timing_vector,
)


def dataverse_entry(
    file_id: int,
    filename: str,
    *,
    original_filename: str | None = None,
) -> dict[str, object]:
    data_file: dict[str, object] = {
        "id": file_id,
        "filename": filename,
        "filesize": 10,
        "contentType": "text/tab-separated-values",
        "checksum": {"type": "MD5", "value": "abc"},
    }
    if original_filename is not None:
        data_file["originalFileName"] = original_filename
        data_file["originalFileSize"] = 11
    return {"dataFile": data_file}


def version_payload(files: list[dict[str, object]]) -> dict[str, object]:
    major, minor = DATASET_VERSION.split(".")
    return {
        "status": "OK",
        "data": {
            "versionNumber": int(major),
            "versionMinorNumber": int(minor),
            "datasetPersistentId": DATASET_DOI,
            "releaseTime": "2026-07-20T12:10:02Z",
            "license": {"name": "CC BY 4.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {
                            "typeName": "title",
                            "value": DATASET_TITLE,
                        }
                    ]
                }
            },
            "files": files,
        },
    }


def test_manifest_parsing_and_timing_classification_are_deterministic() -> None:
    payload = version_payload(
        [
            dataverse_entry(
                2,
                "BD_F5_T_TimeVi.tab",
                original_filename="BD_F5_T_TimeVi.csv",
            ),
            dataverse_entry(1, "H_F5_S.mat"),
        ]
    )

    manifest = parse_version_manifest(payload)  # type: ignore[arg-type]
    timing_files = find_timing_files(manifest.files)

    assert [file.file_id for file in manifest.files] == [2, 1]
    assert len(timing_files) == 1
    assert timing_files[0].experiment_id == "BD_F5_T"
    assert timing_files[0].modality == "Vi"
    assert timing_files[0].file.original_size == 11


def test_manifest_parsing_rejects_a_different_dataset_identity() -> None:
    payload = version_payload([dataverse_entry(1, "H_F5_S.mat")])
    payload["data"]["datasetPersistentId"] = "doi:10.0000/NOT-CORA"  # type: ignore[index]

    with pytest.raises(ValueError, match="dataset identity mismatch"):
        parse_version_manifest(payload)  # type: ignore[arg-type]


def test_manifest_parsing_rejects_a_different_version() -> None:
    payload = version_payload([dataverse_entry(1, "H_F5_S.mat")])
    payload["data"]["versionMinorNumber"] = 2  # type: ignore[index]

    with pytest.raises(ValueError, match="version mismatch"):
        parse_version_manifest(payload)  # type: ignore[arg-type]


def test_manifest_parsing_rejects_a_different_title() -> None:
    payload = version_payload([dataverse_entry(1, "H_F5_S.mat")])
    fields = payload["data"]["metadataBlocks"]["citation"]["fields"]  # type: ignore[index]
    fields[0]["value"] = "A different dataset"  # type: ignore[index]

    with pytest.raises(ValueError, match="dataset title"):
        parse_version_manifest(payload)  # type: ignore[arg-type]


def test_alignment_candidate_search_includes_manifest_metadata_fields() -> None:
    payload = version_payload([dataverse_entry(1, "notes.bin")])
    payload["data"]["files"][0]["description"] = "Camera trigger notes"  # type: ignore[index]
    manifest = parse_version_manifest(payload)  # type: ignore[arg-type]

    candidates = find_alignment_candidates(manifest.files)

    assert len(candidates) == 1
    assert candidates[0]["matched_terms"] == ["camera", "trigger"]


def test_f60_is_visible_in_metadata_but_payload_inspection_is_rejected() -> None:
    payload = version_payload(
        [
            dataverse_entry(
                1,
                "HB_F60_S_TimeVi.tab",
                original_filename="HB_F60_S_TimeVi.csv",
            )
        ]
    )
    manifest = parse_version_manifest(payload)  # type: ignore[arg-type]

    assert audit_manifest(manifest)["f60_timing_files_metadata_only"] == ["HB_F60_S_TimeVi.csv"]
    with pytest.raises(ValueError, match="F60 experiment payload"):
        ensure_payload_inspection_allowed("HB_F60_S_TimeVi.csv")


def test_f60_download_is_rejected_before_network_or_file_access(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = version_payload(
        [
            dataverse_entry(
                1,
                "HB_F60_S_Vx.tab",
                original_filename="HB_F60_S_Vx.csv",
            )
        ]
    )
    file = parse_version_manifest(payload).files[0]  # type: ignore[arg-type]
    destination = tmp_path / file.effective_filename
    network_requested = False

    def record_network_request(*_args: object, **_kwargs: object) -> None:
        nonlocal network_requested
        network_requested = True

    monkeypatch.setattr(
        "scripts.inspect_cora_alignment.urllib.request.urlopen",
        record_network_request,
    )

    with pytest.raises(ValueError, match="F60 experiment payload"):
        _download_original(file, destination)

    assert not network_requested
    assert not destination.exists()


def test_f60_guard_checks_both_stored_and_original_filenames(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = version_payload(
        [
            dataverse_entry(
                1,
                "HB_F60_S_Vx.tab",
                original_filename="unexpected_original_name.csv",
            )
        ]
    )
    file = parse_version_manifest(payload).files[0]  # type: ignore[arg-type]
    monkeypatch.setattr(
        "scripts.inspect_cora_alignment.urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("F60 caused a network request"),
    )

    with pytest.raises(ValueError, match="F60 experiment payload"):
        _download_original(file, tmp_path / file.effective_filename)


def test_file_ddi_parsing_binds_counts_to_the_manifest_file() -> None:
    file = ManifestFile(
        file_id=42,
        stored_filename="H_F5_S_Vx.tab",
        original_filename="H_F5_S_Vx.csv",
        stored_size=10,
        original_size=11,
        checksum_algorithm="MD5",
        checksum="abc",
        content_type="text/tab-separated-values",
        directory=None,
        description=None,
    )
    content = b"""\
<codeBook>
  <stdyDscr><citation><titlStmt><IDNo>10.34810/DATA2500</IDNo></titlStmt></citation></stdyDscr>
  <fileDscr ID="f42">
    <fileTxt>
      <fileName>H_F5_S_Vx.tab</fileName>
      <dimensns><caseQnty>8999999</caseQnty><varQnty>1</varQnty></dimensns>
    </fileTxt>
  </fileDscr>
  <dataDscr><var name="0.0125" /></dataDscr>
</codeBook>
"""

    summary = parse_file_ddi(content, file)

    assert summary == {
        "ddi_case_quantity": 8_999_999,
        "ddi_variable_quantity": 1,
        "numeric_variable_name": True,
        "inferred_original_numeric_value_count": 9_000_000,
    }


def test_valid_cached_download_is_verified_without_network(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"0\n1\n"
    file = _manifest_file_for_download(content)
    destination = tmp_path / file.effective_filename
    destination.write_bytes(content)
    monkeypatch.setattr(
        "scripts.inspect_cora_alignment.urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("valid cache caused a network request"),
    )

    _download_original(file, destination)

    assert destination.read_bytes() == content


def test_same_size_corrupt_cache_is_replaced(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"0\n1\n"
    file = _manifest_file_for_download(content)
    destination = tmp_path / file.effective_filename
    destination.write_bytes(b"9\n9\n")
    monkeypatch.setattr(
        "scripts.inspect_cora_alignment.urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(content),
    )

    _download_original(file, destination)

    assert destination.read_bytes() == content
    assert not destination.with_suffix(destination.suffix + ".part").exists()


def test_bad_download_checksum_removes_partial_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"0\n1\n"
    file = _manifest_file_for_download(content)
    destination = tmp_path / file.effective_filename
    monkeypatch.setattr(
        "scripts.inspect_cora_alignment.urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(b"9\n9\n"),
    )

    with pytest.raises(ValueError, match="checksum does not match"):
        _download_original(file, destination)

    assert not destination.exists()
    assert not destination.with_suffix(destination.suffix + ".part").exists()


def test_timing_vector_reader_rejects_multiple_columns(tmp_path) -> None:
    path = tmp_path / "time.csv"
    path.write_text("0,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one column"):
        _read_numeric_vector(path)


def _manifest_file_for_download(content: bytes) -> ManifestFile:
    return ManifestFile(
        file_id=42,
        stored_filename="BD_F5_T_TimeVi.csv",
        original_filename=None,
        stored_size=len(content),
        original_size=None,
        checksum_algorithm="MD5",
        checksum=hashlib.md5(content).hexdigest(),
        content_type="text/csv",
        directory=None,
        description=None,
    )


def test_timing_vector_validation_reports_observed_structure() -> None:
    summary = validate_timing_vector([0.0, 1 / 3000, 2 / 3000, 3 / 3000])

    assert summary["value_count"] == 4
    assert summary["first_value"] == 0.0
    assert summary["last_value"] == pytest.approx(0.001)
    assert summary["median_increment"] == pytest.approx(1 / 3000)


@pytest.mark.parametrize(
    "values, message",
    [
        ([0.0], "at least two"),
        ([0.0, math.nan], "finite"),
        ([0.0, 0.0], "strictly increasing"),
        ([1.0, 0.0], "strictly increasing"),
    ],
)
def test_timing_vector_validation_rejects_invalid_vectors(
    values: list[float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_timing_vector(values)


def test_alignment_is_blocked_when_manifest_and_clock_evidence_are_incomplete() -> None:
    payload = version_payload(
        [
            dataverse_entry(
                1,
                "BD_F5_T_TimeVi.tab",
                original_filename="BD_F5_T_TimeVi.csv",
            ),
            dataverse_entry(
                2,
                "HB_F60_S_TimeVi.tab",
                original_filename="HB_F60_S_TimeVi.csv",
            ),
        ]
    )
    manifest = parse_version_manifest(payload)  # type: ignore[arg-type]

    blockers = alignment_blockers(
        manifest.files,
        common_time_origin_documented=False,
        start_offset_documented=False,
        clock_relationship_documented=False,
    )

    assert blockers == (
        "stationary vibration timing vectors do not cover all 36 experiments",
        "thermal capture timestamps do not cover all 36 experiments",
        "a common thermal/DAS time origin is not documented",
        "the first thermal capture offset relative to vibration is not documented",
        "the camera/DAS clock relationship and drift handling are not documented",
    )
