# DHSE Real-Data Pilot Runbook

This runbook converts DHSE from a synthetic harness into a retrospective pilot
without changing the metric definition.

## Pilot Goal

Measure whether ED-disposition-time material, scored by DHSE, enriches for
Post-Disposition Trajectory Revision with Burden (PTR-B) after hospital
discharge.

This is not a prospective care-delay workflow. DHSE is run retrospectively after
discharge. Pending inpatient workup is expected flow and is not a failure.

## Minimum Cohort

Start with 50-100 adult ED admissions before scaling.

Include:

- ED disposition timestamp
- ED provider note available at or before disposition
- ED chief concern
- disposition diagnosis or problem representation
- admitting service and intended level of care
- key PMH
- ED resulted labs/imaging before disposition
- ED vital trend before disposition
- ED treatments before disposition
- discharge diagnosis category
- hospital LOS and expected/risk-adjusted LOS when available
- objective upgrade, rapid response, procedure, mortality, discharge, and
  readmission fields

Exclude:

- direct ICU admissions
- planned procedure-only admissions
- hospice/comfort-care admissions
- placement-only/social admissions
- missing disposition timestamp
- missing fields required to label PTR-B
- pathways where inpatient serial testing is the intended reason for admission
  and no trajectory revision occurred

## Build The Export

1. Use [docs/DHSE_CANONICAL_CSV_SCHEMA.md](DHSE_CANONICAL_CSV_SCHEMA.md) as the
   target schema.
2. Use [data/dhse_column_mapping_template.csv](../data/dhse_column_mapping_template.csv)
   to document every native-to-DHSE mapping.
3. Use [sql/dhse_cohort_extract_template.sql](../sql/dhse_cohort_extract_template.sql)
   as a site-neutral extraction outline.
4. Put only ED-disposition-time material into snapshot columns.
5. Put post-disposition outcomes only into label columns.

## Validate

```bash
python scripts/validate_dhse_export.py path/to/canonical_export.csv --json
```

Validation must pass before scoring. Leakage-risk warnings are not always fatal,
but each warning should be documented in the mapping file.

## Run Study Packet

```bash
python scripts/create_dhse_study_packet.py \
  --input path/to/canonical_export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_real_pilot_YYYYMMDD
```

The packet contains:

- `validation.json`
- `reports.json`
- `summary.json`
- `case_level.csv`
- `run_manifest.json`
- `METHODS_SNAPSHOT.md`

## Primary Analysis

Primary risk score:

```text
risk = 100 - DSI
```

Primary outcome:

```text
PTR-B = any objective trajectory revision event AND any burden event
```

Primary metrics:

- AUROC
- AUPRC
- top-decile enrichment
- capture at fixed review fractions: 5%, 10%, 20%

Required comparisons:

- structured severity heuristic
- nonspecific diagnosis heuristic
- ED LOS heuristic
- JRE-only risk
- Black Swan-only risk

## Acceptance Gate For Scaling

Scale beyond the pilot only if:

- canonical export can be generated without manual chart abstraction
- at least 80% of candidate records are labelable
- PTR-B prevalence is nonzero and clinically plausible
- leakage review finds no post-disposition fields in snapshot columns
- DHSE output has interpretable false positives and false negatives

The pilot does not need to show superiority to justify a larger study. It must
show that the data contract and label are operational.

## Outputs To Preserve

For every pilot run, archive:

- canonical CSV hash from `run_manifest.json`
- mapping file
- validation output
- study packet
- code commit or repository snapshot
- date range and inclusion/exclusion counts
- any manual adjudication notes
