# Governed Medical Knowledge Layer

## Criticism

The fair criticism is:

> Even if this system is not acting as a clinician, defining red flags,
> objective-data requirements, risk thresholds, and safe autonomy boundaries
> requires medical expert knowledge.

The correct response is not to deny that. The correct response is to make the
clinical knowledge path explicit, narrow, source-bound, reviewable, and
monitored.

## Position

This repository should treat medical knowledge as governed software
configuration, not model vibes.

The LLM may help find candidate guideline facts or clinical red-flag
definitions. It may not silently write production rules, authorize care, or
decide that a case is safe.

## Proposed Workflow

Use a strong medical-capable model, such as a configured Grok 4.2 endpoint or an
equivalent model, for atomic clinical/guideline questions only.

Good query shape:

```text
For adult ED/telehealth triage, what objective findings or symptom combinations
are commonly treated as red flags for [domain]?
Return only guideline-like criteria, source names, exact threshold values when
available, and uncertainty/controversy notes.
```

Bad query shape:

```text
Read this whole encounter and tell us what to do.
```

## Knowledge Object

Every returned clinical fact should become a structured candidate:

```json
{
  "knowledge_id": "dyspnea_spo2_escalation_threshold",
  "domain": "dyspnea_respiratory",
  "claim": "Low oxygen saturation should block autonomous reassurance.",
  "threshold": "SpO2 < 92% in current demo policy",
  "source_type": "guideline_or_expert_review",
  "source_citation": "required before promotion",
  "retrieved_by_model": "configured medical knowledge model",
  "retrieved_at": "ISO-8601 timestamp",
  "model_prompt_hash": "sha256",
  "model_answer_hash": "sha256",
  "human_review_status": "pending",
  "implemented_as": "candidate_only",
  "monitoring_plan": "track false positives, false negatives, overrides, and drift"
}
```

## Governance Rules

1. Atomic only.
   Each query asks one narrow clinical/guideline question.

2. Citation required.
   A model answer without a source is not promotable.

3. Human review required.
   A clinician or appropriately qualified reviewer must approve promotion into
   templates, red-flag patterns, thresholds, or guardrail rules.

4. Versioned rules.
   Store the source, prompt, answer hash, reviewer, effective date, and rollback
   path.

5. Monitored after promotion.
   Track case counts, overrides, false positives, false negatives, and drift.

6. More conservative by default.
   A candidate fact can add review pressure or ask for objective data. It cannot
   create autonomous clearance without outcome validation.

## How This Counters The Criticism

The system does not claim to replace clinical expertise. It operationalizes
clinical expertise as auditable software:

- expert-system slots encode known requirements;
- LLMs help gather candidate knowledge;
- sources and reviewer decisions are preserved;
- deterministic validators enforce the current approved rule set;
- retrospective DHSE and empirical modeling test whether those boundaries
  predict real trajectory revision;
- governance decides whether learned or retrieved facts become production
  rules.

This is stronger than an opaque chatbot because the medical knowledge is not
hidden in a prompt or model weight. It is a versioned boundary artifact.

## Failure Modes To Monitor

- model hallucinated a threshold
- source is outdated
- guideline differs by country, setting, age, pregnancy, or comorbidity
- rule is too broad and causes alert fatigue
- rule is too narrow and misses a sentinel
- real-world data shows subgroup drift
- reviewer-approved rule becomes obsolete

## Secret Handling

Use environment variables or deployment secrets:

```text
XAI_API_KEY
GROK_MEDICAL_KNOWLEDGE_MODEL
```

Do not commit keys, model transcripts containing PHI, or unreviewed clinical
claims as production rules.
