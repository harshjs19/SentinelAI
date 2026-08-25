# Knowledge source provenance

## Curation policy

Knowledge cards are original SentinelAI summaries, not mirrors of third-party material.
External sources were selected in the order preferred for Retriever V1: OEM/engineering
documentation, government or standards sources, then peer-reviewed research. Source URLs
were inspected during curation on 2026-08-25; normal ingestion and retrieval never fetch
them. No vendor manual, paid standard, paper, table, figure, or PDF is committed.

Each Markdown file's exact bytes receive a source SHA-256 at ingestion. That digest tracks
the project-authored summary, not the authenticity or current availability of its cited
source. `knowledge/sources/manifest.json` is the machine-readable authority for titles,
publishers, versions, URLs, usage notes, fault codes, and asset types.

## External cards

| Source ID | Authority and source | Facts summarized | Scope and usage boundary |
| --- | --- | --- | --- |
| `skf_bearing_damage_reference` | SKF, [Bearing Damage and Failure Analysis](https://cdn.skfmediahub.skf.com/api/public/0901d196806f2d3a/pdf_preview_medium/0901d196806f2d3a_pdf_preview_medium.pdf) | Bearing damage interpretation needs operating, load, lubrication, assembly, and inspection context. | General `bearing_fault` reference only. Original paraphrase; no SKF text, figures, or failure tables reproduced. |
| `doe_motor_alignment_coupling_reference` | U.S. Department of Energy, [Motor and Drive System Sourcebook](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/motor.pdf) | Angular/parallel alignment, coupling tolerance, vibration, foundation, and inspection context. | Supports separate `misalignment` and `coupling_fault` labels; it does not prove damage or urgency. U.S. Government sourcebook is cited, not bundled. |
| `fluke_rotating_balance_shaft_reference` | Fluke, [Dynamic Unbalance](https://www.fluke.com/en-us/learn/blog/alignment/dynamic-unbalance-what-it-is-how-to-fix-i) and triaxial technical guidance | Mass-axis unbalance and overlapping bent-shaft/imbalance/alignment indications. | Supports separate `imbalance` and `bent_shaft` labels. Copyrighted article and images are not reproduced. |
| `iec_motor_eccentricity_scope` | IEC, [IEC TS 60034-24:2009 public catalogue](https://webstore.iec.ch/en/publication/127) | Public scope lists static/dynamic eccentricity in rotating-machine online diagnosis. | Only the public catalogue scope is paraphrased. The paid standard is not copied; no detailed IEC requirement is claimed. |
| `ieee_induction_motor_rotor_bar_reference` | IEEE, [DOI 10.1109/28.952499](https://doi.org/10.1109/28.952499), cross-checked with partial-bar DOI 10.1109/TIM.2016.2540941 | Electrical-signature methods, operating-state sensitivity, and the harder partial-bar measurement problem. | Supports separate half/full rotor-bar labels without bar count, physical proof, or severity. Abstract/bibliographic facts are paraphrased; paper text is not redistributed. |
| `nasa_gear_condition_reference` | NASA Glenn, [NASA/TM-2001-210936](https://ntrs.nasa.gov/citations/20020009087), with NASA TM-106467 context | Complementary vibration, oil-debris, visual inspection, and operating speed/load effects in gear experiments. | Supports all three CORA gear-wear class labels without interpreting their numbers as measured wear or severity. Public-use U.S. Government reports are linked, not bundled. |

## Internal SentinelAI cards

| Source ID | Repository basis | Curated boundary |
| --- | --- | --- |
| `sentinelai_acoustic_anomaly_semantics_v1` | `docs/audio_baseline.md`, `docs/model_capabilities.md`, `docs/decision_engine.md`, `docs/evidence_package.md` | Acoustic novelty is not a named physical fault; Audio V1 remains experimental. |
| `sentinelai_visual_anomaly_semantics_v1` | `docs/vision_baseline.md`, model-capability, Decision Engine, and Evidence Package docs | Visual anomaly is not a physical diagnosis; validated scope remains VisA PCB1. |
| `sentinelai_normal_interpretation_v1` | Decision Engine, capability, and Evidence Package docs | Normal is limited to declared model scope and does not prove absence of every defect. |
| `sentinelai_confidence_semantics_v1` | Capability, Decision Engine, and Evidence Package docs | Raw classifier/anomaly evidence is not failure probability, severity, health, risk, or urgency. |
| `sentinelai_model_scope_lifecycle_v1` | `docs/model_capabilities.md`, `docs/evidence_package.md` | Validated-baseline versus experimental meaning; retrieval cannot expand validated scope. |
| `sentinelai_evidence_limitations_v1` | Decision Engine, Evidence Package, runtime architecture, and CORA alignment docs | Unsupported claims remain absent; blocked CORA fusion is not reconstructed. |
| `sentinelai_insufficient_evidence_v1` | Decision Engine and Evidence Package docs | Indeterminate zero-prediction evidence produces no fault-specific maintenance result. |

Third-party publishers retain their rights. SentinelAI claims authorship only over its
original summaries and code, not over cited publications or standards.
