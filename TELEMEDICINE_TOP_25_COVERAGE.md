# Top Telemedicine Reasons Coverage

## Purpose

This document maps common telemedicine reasons/chief complaints to the current `ver2` expert-system templates.

The goal is not to claim these are production clinical protocols. The goal is to ensure the app has a governed starting template for high-volume telemedicine work, so the dynamic expert-system planner has something to extend rather than inventing from scratch.

## Current Coverage Summary

The app now supports 21 expert-system domains:

- `adhd_behavioral_med`
- `asthma_allergy`
- `chest_discomfort`
- `diabetes_hyperglycemia`
- `dyspnea_respiratory`
- `eye_ear`
- `followup_lab_review`
- `general_med_management`
- `gerd_dyspepsia`
- `gi_symptoms`
- `headache_migraine`
- `med_refill_hypertension`
- `mental_health`
- `musculoskeletal_pain`
- `obesity_metabolic`
- `rash`
- `routine_dermatology`
- `skin_infection`
- `uri_sinus_throat`
- `uti_symptoms`
- `vaginal_sti`

## Top Reasons Mapping

| Telemedicine reason | Current domain | Coverage type |
|---|---|---|
| Medication refills / medication management | `general_med_management` | New general pathway |
| Hypertension medication refill | `med_refill_hypertension` | Existing strong pathway |
| Follow-up visit | `followup_lab_review` | New follow-up/lab review pathway |
| Lab/test result review | `followup_lab_review` | New objective-result pathway |
| Anxiety/depression | `mental_health` | New safety-focused pathway |
| ADHD / behavioral medication follow-up | `adhd_behavioral_med` | New controlled-medication pathway |
| URI / cold / viral symptoms | `uri_sinus_throat` | New URI stewardship pathway |
| Cough / bronchitis | `uri_sinus_throat` | New respiratory-infection pathway |
| COVID / flu-like illness | `uri_sinus_throat` | New viral/respiratory pathway |
| Sinusitis | `uri_sinus_throat` | New antibiotic-stewardship pathway |
| Sore throat / strep concern | `uri_sinus_throat` | New airway/strep boundary pathway |
| Allergies | `asthma_allergy` | New allergy/asthma pathway |
| Asthma/wheezing | `asthma_allergy` | New asthma-severity pathway |
| UTI | `uti_symptoms` | Existing strong pathway |
| Vaginal discharge / yeast / BV | `vaginal_sti` | New GU/sexual-health pathway |
| STI exposure | `vaginal_sti` | New STI/PEP/coercion pathway |
| Rash / hives | `rash` | Existing dangerous-rash pathway |
| Skin infection / cellulitis / abscess | `skin_infection` | New infection-severity pathway |
| Acne / routine dermatology | `routine_dermatology` | New routine-derm pathway |
| Pink eye / conjunctivitis | `eye_ear` | New eye/ear pathway |
| Ear pain | `eye_ear` | New eye/ear pathway |
| Nausea / vomiting / diarrhea | `gi_symptoms` | New GI pathway |
| Heartburn / indigestion | `gerd_dyspepsia` | New GERD-with-cardiac-boundary pathway |
| Headache / migraine | `headache_migraine` | Existing strong pathway |
| Back pain / musculoskeletal pain | `musculoskeletal_pain` | New MSK red-flag pathway |
| Obesity / GLP-1 / metabolic care | `obesity_metabolic` | New metabolic-medication pathway |
| Diabetes chronic check-in | `diabetes_hyperglycemia` | Existing diabetes-danger pathway |

## What Was Added

The update added first-pass `SlotSpec` templates for:

- mental health,
- ADHD/behavioral medication,
- general medication management,
- follow-up and lab review,
- URI/sinus/sore throat,
- asthma/allergy,
- vaginal/STI,
- eye/ear,
- GI symptoms,
- GERD/dyspepsia,
- musculoskeletal pain,
- routine dermatology,
- skin infection,
- obesity/metabolic care.

Each added domain has:

- at least five expert-system slots,
- critical safety slots,
- clarification questions,
- red-flag patterns,
- Black Swan Guardrail supported-envelope registration,
- multi-turn resolution answers for dashboard simulation,
- seeded trap priors where traps are used.

## Proof

Run:

```bash
pytest tests/test_top_telemedicine_coverage.py
pytest tests
```

Current verification:

```text
tests/test_top_telemedicine_coverage.py: 5 passed
full suite: 318 passed
```

## Important Limit

These new domains are coverage scaffolds. They are not production clinical protocols.

The production-ready version still needs:

- clinician review by specialty,
- jurisdiction-specific prescribing constraints,
- antibiotic stewardship policy review,
- controlled-substance policy review,
- mental-health crisis workflow validation,
- real outcome calibration,
- and governance approval before deployment.

The value for the demo is that the system no longer looks like it only works for seven hand-picked cases. It now has a broad telemedicine template surface that the dynamic ESS planner, VAMS memory, and stigmergic learning layer can extend.
