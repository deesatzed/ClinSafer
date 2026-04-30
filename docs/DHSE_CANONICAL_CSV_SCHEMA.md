# DHSE Canonical Flat CSV Schema

This schema is the site-neutral bridge from an EHR export into the DHSE
benchmark. It is deliberately flat so MIMIC, Temple, or another institutional
extract can map into the same contract without changing the scoring engine.

Run with:

```bash
python scripts/run_dhse_benchmark.py --input path/to/export.csv --input-format csv
```

For a reproducible pilot packet with validation, manifest, summary metrics, and
case-level outputs:

```bash
python scripts/create_dhse_study_packet.py \
  --input path/to/export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_real_pilot_YYYYMMDD
```

Use `data/dhse_column_mapping_template.csv` to document how each site-native
field maps into this schema.

## Required Snapshot Columns

| Column | Meaning |
|---|---|
| `case_id` | Stable encounter identifier. |
| `age` | Age at ED encounter. |
| `chief_concern` | ED chief concern or triage reason. |
| `domain` | JRE domain, such as `dyspnea_respiratory`, `chest_discomfort`, `uti_symptoms`, or `rash`. |
| `disposition_diagnosis` | ED disposition problem representation or diagnosis. |

## Optional Snapshot Columns

| Column | Format | Meaning |
|---|---|---|
| `input_mode` | `notes`, `dialogue`, or `hybrid` | Defaults to `notes`. |
| `admission_service` | string | Admitting service. |
| `level_of_care` | string | `floor`, `observation`, `stepdown`, `ICU`, etc. |
| `ed_note` | string | ED note text available at disposition. |
| `key_pmh` | pipe-separated | Example: `COPD|heart failure|diabetes`. |
| `ed_results_json` | JSON object | Resulted ED data before disposition, for example `{"lactate": 3.2}`. |
| `vital_trend_json` | JSON object | Vital arrays before disposition, for example `{"spo2": [94, 89]}`. |
| `treatments` | pipe-separated | ED treatments before disposition. |
| `dialogue_json` | JSON list | Dialogue statements for `dialogue` or `hybrid` mode. |
| `metadata_json` | JSON object | Extra fields not used directly by scoring. |
| `ed_los_hours` | number | Used only by the ED LOS baseline. |

`dialogue_json` items use:

```json
{"question": "...", "answer": "...", "concept": "oxygen_saturation", "source": "patient"}
```

## Outcome Label Columns

These fields are post-disposition labels. They must not be used to construct the
ED snapshot.

| Column | Meaning |
|---|---|
| `ed_diagnosis_category` | Category at ED disposition. |
| `discharge_diagnosis_category` | Discharge category. |
| `discharge_principal_diagnosis` | Discharge principal diagnosis. |
| `los_hours` | Hospital LOS. |
| `expected_los_hours` | DRG, diagnosis-group, or risk-adjusted expected LOS. |
| `icu_transfer_within_24h` | Boolean. |
| `stepdown_transfer_within_24h` | Boolean. |
| `rapid_response_within_24h` | Boolean. |
| `mortality` | Boolean. |
| `major_procedure` | Boolean. |
| `service_change_due_to_diagnosis` | Boolean. |
| `major_therapeutic_pivots` | Pipe-separated therapeutic pivots. |
| `delayed_definitive_therapy_hours` | Number. |
| `discharge_to_higher_level_of_care` | Boolean. |
| `readmission_30d` | Boolean. |
| `trajectory_metadata_json` | JSON object. |

## Fixture/Testing Columns

| Column | Meaning |
|---|---|
| `expected_ptr_b` | Optional expected PTR-B label for fixture tests. |
| `expected_state` | Optional expected DHSE state. |
| `defect_family` | Optional family label for stratified analysis. |
| `notes` | Free-text fixture note. |

## Boolean Values

Accepted true values: `1`, `true`, `yes`, `y`, `t`.

Everything else is false unless the field is blank and documented as optional.
