-- DHSE cohort extract template.
--
-- This is intentionally site-neutral SQL/pseudocode. Replace table and field
-- names with local EHR warehouse equivalents, then export the final SELECT to
-- the canonical CSV schema documented in docs/DHSE_CANONICAL_CSV_SCHEMA.md.

WITH eligible_ed_admissions AS (
    SELECT
        e.encounter_id AS case_id,
        e.patient_id,
        e.ed_arrival_time,
        e.ed_disposition_time,
        e.hospital_admission_time,
        e.hospital_discharge_time,
        e.age_at_encounter AS age,
        e.chief_concern,
        e.disposition_diagnosis,
        e.admission_service,
        e.intended_level_of_care AS level_of_care
    FROM ehr_ed_encounters e
    WHERE e.age_at_encounter >= 18
      AND e.admitted_flag = 1
      AND e.ed_disposition_time IS NOT NULL
      AND e.hospital_discharge_time IS NOT NULL
      AND COALESCE(e.direct_icu_admission_flag, 0) = 0
      AND COALESCE(e.hospice_or_comfort_care_flag, 0) = 0
      AND COALESCE(e.placement_only_flag, 0) = 0
),
ed_notes AS (
    SELECT
        n.encounter_id AS case_id,
        STRING_AGG(n.note_text, '\n\n' ORDER BY n.note_time) AS ed_note
    FROM ehr_notes n
    JOIN eligible_ed_admissions e ON e.case_id = n.encounter_id
    WHERE n.note_time <= e.ed_disposition_time
      AND n.note_type IN ('ED Provider Note', 'ED MDM', 'Triage Note')
    GROUP BY n.encounter_id
),
pmh AS (
    SELECT
        p.encounter_id AS case_id,
        STRING_AGG(DISTINCT p.condition_name, '|') AS key_pmh
    FROM ehr_problem_history p
    JOIN eligible_ed_admissions e ON e.case_id = p.encounter_id
    WHERE p.known_time <= e.ed_disposition_time
    GROUP BY p.encounter_id
),
ed_results AS (
    SELECT
        r.encounter_id AS case_id,
        JSON_OBJECT_AGG(r.result_name, r.result_value ORDER BY r.result_time) AS ed_results_json
    FROM ehr_results r
    JOIN eligible_ed_admissions e ON e.case_id = r.encounter_id
    WHERE r.result_time <= e.ed_disposition_time
      AND r.result_status = 'final'
    GROUP BY r.encounter_id
),
ed_vitals AS (
    SELECT
        v.encounter_id AS case_id,
        JSON_OBJECT_AGG(v.vital_name, v.vital_values) AS vital_trend_json
    FROM (
        SELECT
            raw.encounter_id,
            raw.vital_name,
            JSON_ARRAYAGG(raw.vital_value ORDER BY raw.vital_time) AS vital_values
        FROM ehr_vitals raw
        JOIN eligible_ed_admissions e ON e.case_id = raw.encounter_id
        WHERE raw.vital_time <= e.ed_disposition_time
        GROUP BY raw.encounter_id, raw.vital_name
    ) v
    GROUP BY v.encounter_id
),
ed_treatments AS (
    SELECT
        m.encounter_id AS case_id,
        STRING_AGG(DISTINCT m.treatment_name, '|') AS treatments
    FROM ehr_medications_and_treatments m
    JOIN eligible_ed_admissions e ON e.case_id = m.encounter_id
    WHERE m.order_time <= e.ed_disposition_time
    GROUP BY m.encounter_id
),
trajectory AS (
    SELECT
        h.encounter_id AS case_id,
        h.ed_diagnosis_category,
        h.discharge_diagnosis_category,
        h.discharge_principal_diagnosis,
        EXTRACT(EPOCH FROM (h.hospital_discharge_time - h.hospital_admission_time)) / 3600.0 AS los_hours,
        h.expected_los_hours,
        h.icu_transfer_within_24h,
        h.stepdown_transfer_within_24h,
        h.rapid_response_within_24h,
        h.mortality,
        h.major_procedure,
        h.service_change_due_to_diagnosis,
        h.major_therapeutic_pivots,
        h.delayed_definitive_therapy_hours,
        h.discharge_to_higher_level_of_care,
        h.readmission_30d
    FROM ehr_hospital_trajectory_labels h
)
SELECT
    e.case_id,
    'notes' AS input_mode,
    e.age,
    e.chief_concern,
    CASE
        WHEN LOWER(e.chief_concern) LIKE '%short%breath%' THEN 'dyspnea_respiratory'
        WHEN LOWER(e.chief_concern) LIKE '%chest%' THEN 'chest_discomfort'
        WHEN LOWER(e.chief_concern) LIKE '%urinary%' THEN 'uti_symptoms'
        WHEN LOWER(e.chief_concern) LIKE '%rash%' THEN 'rash'
        ELSE 'dyspnea_respiratory'
    END AS domain,
    e.disposition_diagnosis,
    e.admission_service,
    e.level_of_care,
    COALESCE(n.ed_note, '') AS ed_note,
    COALESCE(p.key_pmh, '') AS key_pmh,
    COALESCE(r.ed_results_json, '{}') AS ed_results_json,
    COALESCE(v.vital_trend_json, '{}') AS vital_trend_json,
    COALESCE(t.treatments, '') AS treatments,
    '[]' AS dialogue_json,
    '{}' AS metadata_json,
    EXTRACT(EPOCH FROM (e.ed_disposition_time - e.ed_arrival_time)) / 3600.0 AS ed_los_hours,
    tr.ed_diagnosis_category,
    tr.discharge_diagnosis_category,
    tr.discharge_principal_diagnosis,
    tr.los_hours,
    tr.expected_los_hours,
    tr.icu_transfer_within_24h,
    tr.stepdown_transfer_within_24h,
    tr.rapid_response_within_24h,
    tr.mortality,
    tr.major_procedure,
    tr.service_change_due_to_diagnosis,
    tr.major_therapeutic_pivots,
    tr.delayed_definitive_therapy_hours,
    tr.discharge_to_higher_level_of_care,
    tr.readmission_30d,
    '{}' AS trajectory_metadata_json,
    '' AS expected_ptr_b,
    '' AS expected_state,
    '' AS defect_family,
    '' AS notes
FROM eligible_ed_admissions e
LEFT JOIN ed_notes n ON n.case_id = e.case_id
LEFT JOIN pmh p ON p.case_id = e.case_id
LEFT JOIN ed_results r ON r.case_id = e.case_id
LEFT JOIN ed_vitals v ON v.case_id = e.case_id
LEFT JOIN ed_treatments t ON t.case_id = e.case_id
LEFT JOIN trajectory tr ON tr.case_id = e.case_id;
