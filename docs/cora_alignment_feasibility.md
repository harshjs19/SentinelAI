# CORA multimodal Gate 0: alignment feasibility

## Decision

**Outcome: PARTIAL / BLOCKED (NO-GO for frame-level fusion).**

CORA v2.1 does not currently provide enough published payload metadata to reproduce an
exact mapping from thermal frame `i` to the immediately preceding Vx/Vy/Vz sample
interval. The paper describes a nominal six-second cadence and says that modality time
vectors plus an infrared timestamp enable alignment. The released v2.1 payload does not
publish a standalone infrared timestamp file, has no separately named stationary
vibration time vector for 35 of 36 experiments, and does not document a common
camera/DAS zero, first-frame offset, or clock relationship. Three representative MAT
files and two control JPEGs also contain no timestamp evidence; uninspected MAT payloads
are not claimed to have been exhaustively inventoried.

The likely intended relationship is scientifically plausible, but it is not
operationally reproducible from the released files. In particular, this audit does not
accept `frame_index * 6 seconds` or a fixed 18,000-sample ordinal window.

Under this Gate 0 project's conservative stop policy, the next planned CORA modeling
milestone is not permitted until the missing timing provenance is supplied,
authoritatively clarified, or the user explicitly selects a non-alignment alternative.
The evidence itself specifically blocks exact frame-level fusion; it does not claim that
an independently scoped unimodal vibration study is scientifically impossible.

## Gate question

For thermal frame `i`, can v2.1 determine `thermal_capture_time(i)` and therefore the
exact `[start_sample, end_sample)` range in all three vibration channels for the
interval immediately preceding that capture?

**No.** No authoritative absolute/relative camera timestamp evidence or common-origin
mapping was found, so the boundary times cannot be established. A 3 kHz sampling rate
can convert a known time interval to sample indices; it cannot create the missing
interval or its offset.

## Authoritative sources inspected

| Source | Evidence used |
| --- | --- |
| [CORA dataset record](https://doi.org/10.34810/DATA2500) | Dataset identity and official repository |
| [Pinned Dataverse v2.1 API manifest](https://dataverse.csuc.cat/api/datasets/:persistentId/versions/2.1?persistentId=doi%3A10.34810%2FDATA2500) | Complete 1,878-file inventory, IDs, sizes, formats, and manifest checksums |
| Representative [file-level DDI metadata](https://dataverse.csuc.cat/api/access/datafile/335103/metadata/ddi) for 18 non-F60 files whose IDs/checksums are in the pinned manifest | Tabular case counts for Vx/Vy/Vz, C1, T1, and RPM in `H_F5_S`, `BD_F15_S`, and `W75_F50_S` |
| [Scientific Data paper, 16-page article-in-press reference PDF](https://www.nature.com/articles/s41597-026-07224-0_reference.pdf) | Acquisition rates and setup (Methods pp. 7-8), nominal cadence and synchronization/sample-count claim (Methods pp. 8-9), 45-minute stationary-test claim (Methods p. 10), and duration validation (p. 12) |
| [`Readme.txt`, file 500929](https://dataverse.csuc.cat/api/access/datafile/500929) | Instruments, file convention, and official file inventory |
| [`Information_about_database_files.txt`, file 335497](https://dataverse.csuc.cat/api/access/datafile/335497) | Expected experiment/file descriptions |
| [`Information_environmental_conditions.txt`, file 335498](https://dataverse.csuc.cat/api/access/datafile/335498) | References to timing filenames that are mostly absent from v2.1 |
| [`Sampling_frequency_and_units.txt`, file 335499](https://dataverse.csuc.cat/api/access/datafile/335499) | Published rates and the unresolved vibration-unit wording |

The cached official reference PDF is 1,179,757 bytes with SHA-256
`70cfe2cb8824a8f77b08665f497ec6dd4994aa393b49f4be0ae6d95504bbd0a2`.
The official article record exposes no supplementary synchronization protocol. No
third-party mirror, blog, or inferred convention was used.

## Dataverse v2.1 manifest audit

The pinned version is 2.1, released 2026-07-20. A filename-derived audit of its complete
1,878-file manifest classifies:

- 611 stationary experiment files;
- 1,263 transient experiment files;
- four text metadata files.

The article's Data Records breakdown instead says 510 stationary and 1,368 transient
files. Both classifications total 1,878, but the paper's categories conflict with the
audit's 611/1,263/four classification of the pinned manifest. This audit uses that
versioned inventory and records the contradiction rather than reconciling it by
assumption.

The local ignored full-manifest snapshot records every Dataverse file ID, original and
stored filename where applicable, directory, stored/original size, manifest checksum,
description, and content type.

Exactly seven released filenames contain a recognized `Time*` modality:

| Experiment | Modality | File ID | Original filename | Stored/original bytes | Dataverse MD5 |
| --- | --- | ---: | --- | ---: | --- |
| `BD_F5_T` | current | [334695](https://dataverse.csuc.cat/api/files/334695) | `BD_F5_T_TimeCu.csv` | 946,638 / 1,066,640 | `916e0aeaada0620504ac080023f91f2e` |
| `BD_F5_T` | RPM | [333966](https://dataverse.csuc.cat/api/files/333966) | `BD_F5_T_TimeRPM.csv` | 16,626 / 19,626 | `0ecbeacb444f3a43a7583e65530dc860` |
| `BD_F5_T` | vibration | [333965](https://dataverse.csuc.cat/api/files/333965) | `BD_F5_T_TimeVi.csv` | 1,218,860 / 1,308,862 | `e99693b4a2c77c934b68411c14d038eb` |
| `HB_F60_S` | current | [335009](https://dataverse.csuc.cat/api/files/335009) | `HB_F60_S_TimeCu.csv` | 87,557,998 / 96,558,000 | `813e62de46af67e66217eeabbeced582` |
| `HB_F60_S` | RPM | [335115](https://dataverse.csuc.cat/api/files/335115) | `HB_F60_S_TimeRPM.csv` | 1,642 / 1,744 | `1f2f543e23fb63e76c805050550df670` |
| `HB_F60_S` | RTD | [335113](https://dataverse.csuc.cat/api/files/335113) | `HB_F60_S_TimeTemp.csv` | 22,887,598 / 25,587,600 | `9edfe84703ad34552e5b1b49f22cddd5` |
| `HB_F60_S` | vibration | [334994](https://dataverse.csuc.cat/api/files/334994) | `HB_F60_S_TimeVi.csv` | 127,556,220 / 136,556,222 | `8684787f1897938b6f1fbc9b3d441dfe` |

The three downloaded original non-F60 CSVs matched both their published original byte
sizes and the manifest MD5 values above. Local SHA-256 hashes provide supplementary
integrity evidence.

The audit also searched every stored/original filename, directory, description, and
content type case-insensitively for `Time`, `timestamp`, `IR`, thermal/thermography,
camera, `Vi`, vibration, `RPM`, synchronization/sync, start, trigger, sampling, and
clock. Its ignored candidate inventory contains 296 files: term matches comprise 218
`RPM`, 72 `IR`, seven `Time`, two `Vi`, and one sampling match (with overlap between
terms). There are zero matches for timestamp, thermal/thermography, camera, vibration,
synchronization/sync, start, trigger, or clock. The candidates reduce to known RPM
streams, IR control images, the seven timing entries, and the sampling/unit text; no
differently named alignment artifact was found.

There is:

- no standalone `TimeIR`, `IR_Time`, thermal timestamp, synchronization, trigger, or
  clock file;
- no `TimeVo` file;
- only one stationary experiment with any time vectors, and it is F60;
- no timing file for the other 35 stationary experiments;
- no directory or description attached to any of the seven timing entries.

`Information_environmental_conditions.txt` names 180 stationary time files: 36 each
for `TimeCu`, `TimeVi`, `TimeTemp`, `TimeRPM`, and `TimeVo`. Only the four `HB_F60_S`
Cu/Vi/Temp/RPM names occur in the live v2.1 manifest, leaving 176 named timing files
absent. Conversely, `Readme.txt` and `Information_about_database_files.txt` do not list
the time-vector files at all. This is a released-payload contradiction, not evidence
that the absent files exist.

## Official paper claim versus released payload

The paper's Methods section says:

- vibration, current, and RTD were acquired at 3 kHz, 4 kHz, and 1 kHz;
- thermal imaging was performed at 10 images/minute, described as one image every six
  seconds;
- time vectors for current, vibration, temperature, speed, and an infrared image
  timestamp, generated by the DAS and camera recording system, enable temporal
  alignment;
- consecutive thermal captures nominally enclose 6,000 RTD, 18,000 vibration, and
  24,000 current samples;
- stationary tests involved 45 minutes of continuous operation.

These are **paper claims** about the intended acquisition. The v2.1 manifest contains no
standalone infrared timestamp and does not list the time vectors across the stationary
experiment matrix; three representative MATs and two control JPEGs contain no embedded
timestamp evidence. This is not an exhaustive variable inventory of every MAT. The
paper does not specify a hardware trigger, common clock zero, camera-start sequence,
first-frame delay, fixed cross-device offset, or clock-drift correction. The paper claim
therefore cannot substitute for the values needed to calculate exact boundaries.

## Thermal payload reconfirmation

Three existing, checksum-verified, non-F60 MAT files were inspected without altering
Thermal V1:

| Experiment | Dataverse file ID | Manifest MD5 |
| --- | ---: | --- |
| `H_F5_S` | 334968 | `18b4bf748275343a220cca7d4f854d60` |
| `BD_F15_S` | 334986 | `de197bf1881570c4ead8a7cf9c70fbd7` |
| `W75_F50_S` | 334993 | `8a1e5d96afe9d33f36755fa75c2e76d4` |

Each is a MATLAB 5 file containing only `imagenes_celda`, a `(1, 450)` cell array.
Each ordered cell is a `240 x 320 x 3 uint8` frame, and the three channels are identical
grayscale values stored in RGB shape. There is no timestamp variable, MATLAB structure,
calibrated temperature matrix, or other embedded metadata.

Two official non-F60 control JPEGs, `H_F5_S_IR_1_control.jpg` (file 334967) and
`H_F5_S_IR_450_control.jpg` (file 334930), were also inspected. Both are 320 x 240 RGB
JPEG/JFIF images, have empty EXIF dictionaries, and show no timestamp, temperature
scale, filename, or class overlay. Their filenames provide only ordinal sample numbers.

Nothing found changes Thermal V1's interpretation: the frames are non-radiometric
thermographic appearance. `uint8` values are not Celsius.

## Timing-vector and stream-length evidence

Only the three permissible non-F60 time vectors were downloaded. They belong to the
30-second transient `BD_F5_T`, for which the paper explicitly says thermography was not
recorded:

| Vector | Values | First | Last | Median increment | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| `TimeVi` | 90,000 | 0 | 29.9996667 | 0.0003333333 s | Matches 3 kHz transient vibration |
| `TimeCu` | 120,000 | 0 | 29.99975 | 0.00025 s | Matches 4 kHz transient current |
| `TimeRPM` | 2,998 | 0 | 29.97 | 0.01 s | Behaves as 100 Hz, not the generic published 1/30 Hz |

These files show that released time vectors use relative seconds in this transient
example. They do not establish the time origin or offset of any stationary thermal
capture.

The representative file-level DDI metadata exposes a numeric variable name and a case
quantity. The downloaded time vectors directly confirm that, for those three files,
Dataverse treated the first numeric line as a column name. For stationary files whose
payloads were not downloaded, this audit explicitly **infers** the original numeric-line
count as DDI case quantity plus one; it does not present that inference as a directly
counted payload. The inferred counts are identical within each modality across the three
non-F60 stationary representatives. Combined with the audit's filename-derived
stationary counts from the pinned manifest, the evidence is:

| Stream | Manifest file coverage | Representative values | Published rate | Nominal sample coverage (`N / fs`) | First-to-last span if exact (`(N - 1) / fs`) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vx/Vy/Vz | 108 files | 9,000,000 inferred values in each of nine inspected axis metadata records | 3 kHz | 3,000 s (50 min) | 2,999.9996667 s |
| C1/C2/C3 | 108 files | 9,000,000 inferred values in each of three inspected C1 metadata records | 4 kHz | 2,250 s (37.5 min) | 2,249.99975 s |
| T1-T6 | 216 files | 2,700,000 inferred values in each of three inspected T1 metadata records | 1 kHz | 2,700 s (45 min) | 2,699.999 s |
| RPM | 36 files | 100 inferred values in each of three inspected metadata records | nominal 1/30 Hz | 3,000 s | 2,970 s |
| Thermal MAT | 36 files | 450 frames in each of three inspected MAT files | nominal 1/6 Hz | 2,700 s | 2,694 s |

For thermal, 450 captures separated by exactly six seconds would place only 449
inter-frame intervals between the first and last captures, or 2,694 seconds. Whether
frame 1 is at zero, at six seconds, or after another lead-in is not stated. Consequently,
neither 2,694 nor 2,700 seconds is accepted as the actual thermal-to-DAS span.

The paper's uniform 45-minute statement conflicts with the inferred counts for at least
the inspected non-F60 stationary vibration and current files. The official sources do
not explain a vibration lead-in, delayed current start, early stop, modality-specific
clock span, or extra acquisition period. The streams must not be assumed to share start
and end boundaries, and the representative counts must not be generalized to every file
without further inspection.

No stationary Vx, Vy, or Vz payload was downloaded because high-rate signal values
cannot resolve the missing camera timestamps. No classification or fault-discriminative
inspection was performed.

## Attempted alignment contract

The desired future rule would require verified capture timestamps `t[i]` on the same
time base as the vibration vector and would pair frame `i` with vibration samples whose
timestamps lie in `(t[i-1], t[i]]`. Only after that evidence exists could deterministic
`[start_sample, end_sample)` boundaries and exactly 449 candidate inter-frame
observations per 450-frame acquisition be defined. That count does not validate the
timing of any candidate observation.

Gate 0 cannot define `t[i]`, so no alignment formula, sample-boundary convention, or
`CoraAlignedObservation` specification is frozen. There are no demonstration mappings;
providing them would require inventing an offset.

The following ordinal fallbacks are explicitly rejected:

- frame `i` starts at `i * 18,000` vibration samples;
- thermal frame 1 occurs at vibration time zero;
- a 300-second or other lead-in inferred from differing durations is globally fixed;
- an offset is estimated from image/signal correlation, labels, or model performance.

## Exact unresolved assumptions

1. The timestamp or common-clock value for each of the 450 thermal frames.
2. Whether the camera and DAS share a zero or trigger.
3. The offset between vibration sample zero and the first thermal capture.
4. Whether capture cadence is exactly six seconds per experiment or only nominal.
5. Whether clock drift exists and, if so, how it is represented or corrected.
6. Why vibration, current, RTD, RPM, and thermal spans differ.
7. Whether the 176 absent stationary time files were accidentally omitted.
8. Whether offsets are identical across conditions/speeds or acquisition-specific.
9. Whether interval boundaries should be open/closed and how the first frame is handled.
10. Whether an image timestamp denotes exposure start, midpoint, end, or file-write time.
11. Whether absent stationary time vectors were omitted per experiment or intended as
    reusable templates.
12. Whether thermal frames can be dropped or duplicated and whether cadence jitter exists.
13. The camera-versus-DAS start/stop ordering.

## Vibration unit finding

The official sampling/unit file literally describes vibration units as `gs (m^2/s)`.
That combines a conventional acceleration-in-g label with a dimension that is not an
acceleration unit; SI acceleration is `m/s^2`. The paper's sensor table gives the
accelerometer range as `+/-2g, +/-6g`, but a sensor range does not establish the released
numeric scaling. The intended unit is plausibly g, yet conversion/calibration provenance
is absent. The values are therefore not converted, and no physical-unit clipping
threshold is established. This ambiguity does not itself decide timestamp alignment,
but it blocks future physical-unit claims until clarified.

## Draft clarification message - not sent

> We are evaluating CORA v2.1 for reproducible thermal/vibration alignment. Could you
> clarify: (1) the timestamp or common-clock mapping for each of the 450 thermal frames;
> (2) whether the camera and DAS recordings share a zero/trigger; (3) the offset between
> vibration sample zero and the first thermal capture; (4) why stationary vibration,
> current, RTD, RPM, and thermal durations differ; (5) whether thermal timestamps were
> omitted from v2.1; (6) whether a corrected time-file manifest exists; (7) whether
> offsets are identical across experiments; (8) whether camera/DAS clock drift is
> relevant; and (9) the physical unit and scaling of Vx/Vy/Vz?

This message is only a draft. No dataset author or maintainer was contacted.

## F60 exclusion

The complete manifest was inspected, so F60 filenames, IDs, sizes, and checksums appear
as metadata. The reproducible inspection code rejects every F60 experiment payload
before any network or file access and fetches file-level DDI metadata only for non-F60
representatives. No raw F60 vibration or timing datafile payload/value was requested,
downloaded, or directly inspected; F60 appeared only in official metadata inventory.
Existing Thermal V1 data was not changed or used to infer alignment.

## Reproduction

Run the metadata audit and permissible non-F60 timing inspection with:

```shell
uv run python scripts/inspect_cora_alignment.py --download-non-f60-timing --inspect-representative-metadata
```

It writes an ignored full manifest, the three non-F60 timing CSVs, 18 non-F60 file-level
DDI metadata records, and an inspection summary beneath
`datasets/cora_alignment_gate0/`. It reproduces the manifest/timing/DDI portion of this
audit. The paper, JPEG, and MAT findings are independently recorded inspections and are
not regenerated by this command. Normal tests use only synthetic metadata/vectors and
require no network or real CORA files.

Tracked Gate 0 results are in `evaluation/cora_alignment_feasibility.json`. Existing
Thermal V1 code, artifacts, documentation, and evaluation results remain unchanged.

## Next permitted action

Seek authoritative clarification or corrected timing files. Until that happens, do not
train `timeseries_cora_v1`, calibrate either modality, implement `FusionEngine`, change
the inference/domain/API architecture, or inspect the F60 vibration benchmark.

The `timeseries_cora_v1` freeze is the conservative Gate 0 project policy in this
milestone. The scientific evidence directly establishes a NO-GO for exact frame-aligned
fusion; an independent unimodal vibration baseline would require an explicit new scope
decision rather than follow automatically from this audit.

Acquisition-level multimodal analysis, another synchronized dataset, or postponing
fusion are possible alternatives, but Gate 0 does not select one.
