# Disposition Handoff Sufficiency: A Retrospective Benchmark for ED Admission Representation Quality

## Abstract

### Background

ED-to-inpatient handoff evaluation often focuses on completeness, subjective
quality, or pending-task transfer. These measures do not directly test whether
the ED disposition representation was sufficient for the inpatient trajectory
that subsequently unfolded.

### Objective

Introduce Disposition Handoff Sufficiency Benchmark (DHSB) and Disposition
Sufficiency Index (DSI), using only ED-disposition-time information to predict
post-disposition trajectory revision with measurable burden (PTR-B).

### Methods

Retrospective benchmark. Inputs are ED-disposition-time snapshots in notes,
dialogue, or hybrid mode. Outcomes are labeled after discharge using PTR-B:
objective trajectory revision plus measurable burden. DHSE is compared against
structured severity, nonspecific diagnosis, ED LOS, JRE-only, and Black
Swan-only baselines.

### Results

To be populated after retrospective cohort run.

Required tables:

- cohort flow
- PTR-B prevalence and event counts
- primary metrics and baseline comparison
- calibration
- DSI threshold operating points
- stratified performance
- false-positive/false-negative error analysis

### Conclusions

To be populated after validation. Avoid causal or diagnostic-error claims.

## 1. Introduction

Problem:

- Handoffs are safety-critical.
- ED admission often appropriately transfers unresolved workup.
- A metric that punishes pending results would be operationally wrong.
- The relevant question is whether the ED disposition representation was
  sufficient for the trajectory that actually unfolded.

Gap:

- Existing handoff measures are often subjective, checklist-based, or focused on
  information transfer rather than representation-trajectory mismatch.

Contribution:

- PTR-B label.
- DSI score.
- Notes/dialogue/hybrid input framework.
- Reproducible benchmark contract.
- Baseline comparison and paper-facing analysis outputs.

## 2. Methods

### 2.1 Study Design

Retrospective observational benchmark.

### 2.2 Cohort

Describe site, timeframe, adult ED admissions, and exclusions.

### 2.3 ED Snapshot Construction

Use only information available at ED disposition.

Input modes:

- notes
- dialogue
- hybrid

### 2.4 DHSE Model

Summarize:

- JRE evaluation
- Black Swan guardrail wrapper
- DSI scoring
- DHSE states

### 2.5 Outcome Label

PTR-B:

```text
trajectory revision event + burden event
```

### 2.6 Baselines

List implemented and future baselines.

### 2.7 Metrics

Primary:

- AUROC
- AUPRC
- top-decile enrichment
- capture at fixed review budget

Secondary:

- calibration
- threshold table
- stratification
- error analysis

### 2.8 Leakage Control

Explicitly state prohibited fields for scoring.

## 3. Results

### 3.1 Cohort Flow

Insert generated cohort flow table.

### 3.2 Label Prevalence

Insert PTR-B prevalence and event counts.

### 3.3 Primary Performance

Insert DHSE and baseline metrics.

### 3.4 Calibration And Thresholds

Insert calibration bins and DSI threshold table.

### 3.5 Stratified Analyses

Input mode, state, defect family.

### 3.6 Error Analysis

Summarize false positives and false negatives.

## 4. Discussion

Interpretation:

- DSI tests disposition representation sufficiency, not diagnostic correctness.
- PTR-B is a hard retrospective label, but not causal proof.
- The method is designed not to gridlock admissions for pending workup.

Operational relevance:

- Could identify admissions needing better ED-to-inpatient representation.
- Could support handoff QA, documentation improvement, and AI safety evaluation.

## 5. Limitations

- Retrospective.
- Confounding by severity and hospital operations.
- LOS is noisy despite risk adjustment.
- Diagnosis-category mapping may be coarse.
- DSI thresholds are not yet calibrated to real cohorts.
- DHSE is not a clinical decision tool.

## 6. Conclusion

DHSE provides a reproducible benchmark framework for ED disposition handoff
sufficiency using objective post-discharge trajectory revision with burden.
