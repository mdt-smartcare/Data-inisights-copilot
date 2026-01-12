-- ============================================================================
-- Migration: 002_enhanced_analytics_views.sql
-- Purpose: Enhanced views with role mappings, lifestyle, symptoms, and lab data
-- Author: RAG System Alignment
-- Date: 2026-01-09
-- Updated: Fixed to match actual DB schema with lookup table joins
-- ============================================================================

-- ============================================================================
-- VIEW: v_user_roles
-- Purpose: Map technical role names to human-friendly Bangla names
-- ============================================================================
DROP VIEW IF EXISTS v_user_roles CASCADE;

CREATE OR REPLACE VIEW v_user_roles AS
SELECT
    ur.user_id,
    ur.role_id,
    CASE
        WHEN r.name = 'HEALTH_SCREENER' THEN 'SHASTHYA KORMI'
        WHEN r.name = 'PHYSICIAN_PRESCRIBER' THEN 'MEDICAL OFFICER'
        WHEN r.name = 'COMMUNITY_HEALTH_CARE_PROVIDER' THEN 'CHCP'
        WHEN r.name = 'PROVIDER' THEN 'MEDICAL OFFICER'
        WHEN r.name = 'FIELD_ORGANIZER' THEN 'FIELD ORGANIZER'
        WHEN r.name = 'PROGRAM_ORGANIZER' THEN 'PROGRAM ORGANIZER'
        ELSE r.name
    END AS role_name,
    r.name AS role_name_technical
FROM user_role ur
JOIN role r ON r.id = ur.role_id
WHERE r.name NOT IN (
    'EMR_REGION_ADMIN', 'SUPER_USER', 'ACCOUNT_ADMIN', 'EMR_ACCOUNT_ADMIN',
    'EMR_OPERATING_UNIT_ADMIN', 'SUPER_ADMIN', 'EMR_REPORT_ADMIN', 'REGION_ADMIN',
    'OPERATING_UNIT_ADMIN', 'RED_RISK_USER', 'EMR_SITE_ADMIN'
);

COMMENT ON VIEW v_user_roles IS 'User roles with Bangla-friendly name mappings matching Power BI dashboard';

-- ============================================================================
-- VIEW: v_patient_lifestyle
-- Purpose: Aggregate lifestyle factors per patient for risk assessment
-- ============================================================================
DROP VIEW IF EXISTS v_patient_lifestyle CASCADE;

CREATE OR REPLACE VIEW v_patient_lifestyle AS
SELECT
    pl.patient_track_id,
    -- Smoking status (using lifestyle.type and patient_lifestyle.answer)
    MAX(CASE WHEN l.type ILIKE '%smoking%' OR l.name ILIKE '%smoking%' THEN pl.answer END) AS smoking_status,
    BOOL_OR(CASE WHEN (l.type ILIKE '%smoking%' OR l.name ILIKE '%smoking%') 
                  AND pl.answer IN ('current', 'regular', 'yes', 'Yes', 'TRUE', 'true') THEN TRUE ELSE FALSE END) AS is_smoker,
    -- Alcohol consumption
    MAX(CASE WHEN l.type ILIKE '%alcohol%' OR l.name ILIKE '%alcohol%' THEN pl.answer END) AS alcohol_status,
    BOOL_OR(CASE WHEN (l.type ILIKE '%alcohol%' OR l.name ILIKE '%alcohol%') 
                  AND pl.answer IN ('regular', 'heavy', 'yes', 'Yes', 'TRUE', 'true') THEN TRUE ELSE FALSE END) AS is_heavy_drinker,
    -- Physical activity
    MAX(CASE WHEN l.type ILIKE '%physical%' OR l.name ILIKE '%exercise%' THEN pl.answer END) AS physical_activity_level,
    BOOL_OR(CASE WHEN (l.type ILIKE '%physical%' OR l.name ILIKE '%exercise%') 
                  AND pl.answer IN ('sedentary', 'none', 'low', 'No', 'no') THEN TRUE ELSE FALSE END) AS is_sedentary,
    -- Diet
    MAX(CASE WHEN l.type ILIKE '%diet%' OR l.name ILIKE '%diet%' THEN pl.answer END) AS diet_status,
    BOOL_OR(CASE WHEN (l.type ILIKE '%diet%' OR l.name ILIKE '%diet%') 
                  AND pl.answer IN ('poor', 'unhealthy', 'high_salt', 'high_sugar') THEN TRUE ELSE FALSE END) AS has_poor_diet,
    -- Lifestyle risk score
    (
        CASE WHEN BOOL_OR(CASE WHEN (l.type ILIKE '%smoking%' OR l.name ILIKE '%smoking%') 
                               AND pl.answer IN ('current', 'regular', 'yes', 'Yes', 'TRUE', 'true') THEN TRUE ELSE FALSE END) THEN 1 ELSE 0 END +
        CASE WHEN BOOL_OR(CASE WHEN (l.type ILIKE '%alcohol%' OR l.name ILIKE '%alcohol%') 
                               AND pl.answer IN ('regular', 'heavy', 'yes', 'Yes', 'TRUE', 'true') THEN TRUE ELSE FALSE END) THEN 1 ELSE 0 END +
        CASE WHEN BOOL_OR(CASE WHEN (l.type ILIKE '%physical%' OR l.name ILIKE '%exercise%') 
                               AND pl.answer IN ('sedentary', 'none', 'low', 'No', 'no') THEN TRUE ELSE FALSE END) THEN 1 ELSE 0 END +
        CASE WHEN BOOL_OR(CASE WHEN (l.type ILIKE '%diet%' OR l.name ILIKE '%diet%') 
                               AND pl.answer IN ('poor', 'unhealthy', 'high_salt', 'high_sugar') THEN TRUE ELSE FALSE END) THEN 1 ELSE 0 END
    ) AS lifestyle_risk_score,
    MAX(pl.created_at) AS last_updated
FROM patient_lifestyle pl
JOIN lifestyle l ON l.id = pl.lifestyle_id
WHERE pl.is_deleted = FALSE
GROUP BY pl.patient_track_id;

COMMENT ON VIEW v_patient_lifestyle IS 'Aggregated patient lifestyle factors for NCD risk assessment';

-- ============================================================================
-- VIEW: v_patient_symptoms
-- Purpose: Aggregate symptoms per patient for clinical context
-- ============================================================================
DROP VIEW IF EXISTS v_patient_symptoms CASCADE;

CREATE OR REPLACE VIEW v_patient_symptoms AS
SELECT
    ps.patient_track_id,
    STRING_AGG(DISTINCT COALESCE(ps.name, s.name), ', ' ORDER BY COALESCE(ps.name, s.name)) AS symptoms_list,
    COUNT(DISTINCT COALESCE(ps.name, s.name)) AS symptom_count,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%headache%') AS has_headache,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%dizz%') AS has_dizziness,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%blur%' OR COALESCE(ps.name, s.name) ILIKE '%vision%') AS has_vision_issues,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%chest%' OR COALESCE(ps.name, s.name) ILIKE '%pain%') AS has_chest_pain,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%fatigue%' OR COALESCE(ps.name, s.name) ILIKE '%tired%') AS has_fatigue,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%numb%' OR COALESCE(ps.name, s.name) ILIKE '%tingling%') AS has_numbness,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%thirst%') AS has_excessive_thirst,
    BOOL_OR(COALESCE(ps.name, s.name) ILIKE '%urin%' OR COALESCE(ps.name, s.name) ILIKE '%frequent%') AS has_frequent_urination,
    MAX(ps.created_at) AS last_reported
FROM patient_symptom ps
LEFT JOIN symptom s ON s.id = ps.symptom_id
WHERE ps.is_deleted = FALSE
GROUP BY ps.patient_track_id;

COMMENT ON VIEW v_patient_symptoms IS 'Aggregated patient symptoms for clinical context and NCD monitoring';

-- ============================================================================
-- VIEW: v_patient_lab_history
-- Purpose: Track lab test history for biomarker trends
-- ============================================================================
DROP VIEW IF EXISTS v_patient_lab_history CASCADE;

CREATE OR REPLACE VIEW v_patient_lab_history AS
WITH latest_labs AS (
    SELECT
        patient_track_id,
        result_name,
        result_value,
        unit,
        is_abnormal,
        created_at,
        ROW_NUMBER() OVER (PARTITION BY patient_track_id, result_name ORDER BY created_at DESC) AS rn
    FROM patient_lab_test_result
    WHERE is_deleted = FALSE
)
SELECT
    patient_track_id,
    MAX(CASE WHEN result_name ILIKE '%hba1c%' AND rn = 1 THEN result_value END) AS latest_hba1c,
    MAX(CASE WHEN result_name ILIKE '%hba1c%' AND rn = 1 THEN created_at::date END) AS latest_hba1c_date,
    MAX(CASE WHEN (result_name ILIKE '%fbs%' OR result_name ILIKE '%fasting%') AND rn = 1 THEN result_value END) AS latest_fbs,
    MAX(CASE WHEN (result_name ILIKE '%fbs%' OR result_name ILIKE '%fasting%') AND rn = 1 THEN created_at::date END) AS latest_fbs_date,
    MAX(CASE WHEN result_name ILIKE '%creatinine%' AND rn = 1 THEN result_value END) AS latest_creatinine,
    MAX(CASE WHEN (result_name ILIKE '%cholesterol%' OR result_name ILIKE '%lipid%') AND rn = 1 THEN result_value END) AS latest_cholesterol,
    COUNT(CASE WHEN is_abnormal = TRUE THEN 1 END) AS abnormal_result_count,
    COUNT(DISTINCT result_name) AS total_test_types,
    COUNT(*) AS total_lab_records
FROM latest_labs
GROUP BY patient_track_id;

COMMENT ON VIEW v_patient_lab_history IS 'Patient lab test history with latest values for key biomarkers';

-- ============================================================================
-- VIEW: v_analytics_screening_enhanced
-- ============================================================================
DROP VIEW IF EXISTS v_high_risk_patients CASCADE;
DROP VIEW IF EXISTS v_analytics_enrollment_enhanced CASCADE;
DROP VIEW IF EXISTS v_analytics_screening_enhanced CASCADE;

CREATE OR REPLACE VIEW v_analytics_screening_enhanced AS
SELECT
    vas.*,
    COALESCE(ur.role_name, 'Unknown') AS screener_role_name,
    ur.role_name_technical AS screener_role_technical,
    pl.is_smoker,
    pl.is_heavy_drinker,
    pl.is_sedentary,
    pl.has_poor_diet,
    pl.lifestyle_risk_score,
    pl.smoking_status,
    pl.alcohol_status,
    pl.physical_activity_level,
    ps.symptoms_list,
    ps.symptom_count,
    ps.has_headache,
    ps.has_dizziness,
    ps.has_vision_issues,
    ps.has_chest_pain,
    ps.has_fatigue,
    CASE WHEN COALESCE(pl.lifestyle_risk_score, 0) >= 2 THEN TRUE ELSE FALSE END AS high_lifestyle_risk,
    CASE WHEN COALESCE(ps.symptom_count, 0) >= 3 THEN TRUE ELSE FALSE END AS multiple_symptoms_flag
FROM v_analytics_screening vas
LEFT JOIN v_user_roles ur ON ur.user_id = vas.created_by
LEFT JOIN v_patient_lifestyle pl ON pl.patient_track_id = vas.patient_track_id
LEFT JOIN v_patient_symptoms ps ON ps.patient_track_id = vas.patient_track_id;

COMMENT ON VIEW v_analytics_screening_enhanced IS 'Enhanced screening analytics with role mappings, lifestyle factors, and symptoms';

-- ============================================================================
-- VIEW: v_analytics_enrollment_enhanced
-- ============================================================================
CREATE OR REPLACE VIEW v_analytics_enrollment_enhanced AS
SELECT
    vae.*,
    plh.latest_hba1c,
    plh.latest_hba1c_date,
    plh.latest_fbs,
    plh.latest_fbs_date,
    plh.latest_creatinine,
    plh.latest_cholesterol,
    plh.abnormal_result_count,
    plh.total_lab_records,
    CASE
        WHEN plh.latest_hba1c IS NULL THEN 'No HbA1c Data'
        WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric < 5.7 THEN 'Normal'
        WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric BETWEEN 5.7 AND 6.4 THEN 'Pre-Diabetic'
        WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric BETWEEN 6.5 AND 7.9 THEN 'Controlled Diabetic'
        WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric BETWEEN 8.0 AND 9.9 THEN 'Poorly Controlled'
        WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' THEN 'Very Poorly Controlled'
        ELSE 'Invalid Data'
    END AS glycemic_control_status,
    CASE
        WHEN plh.latest_hba1c_date IS NOT NULL 
        THEN (CURRENT_DATE - plh.latest_hba1c_date)::integer
        ELSE NULL
    END AS days_since_hba1c
FROM v_analytics_enrollment vae
LEFT JOIN v_patient_lab_history plh ON plh.patient_track_id = vae.patient_track_id;

COMMENT ON VIEW v_analytics_enrollment_enhanced IS 'Enhanced enrollment analytics with lab history and glycemic control status';

-- ============================================================================
-- VIEW: v_high_risk_patients
-- ============================================================================
CREATE OR REPLACE VIEW v_high_risk_patients AS
SELECT
    vase.*,
    plh.latest_hba1c,
    plh.abnormal_result_count AS lab_abnormal_count,
    (
        CASE WHEN vase.is_red_risk_patient = TRUE THEN 2 ELSE 0 END +
        CASE WHEN vase.crisis_referral_status = 'Crisis Referral' THEN 2 ELSE 0 END +
        CASE WHEN COALESCE(vase.lifestyle_risk_score, 0) >= 2 THEN 1 ELSE 0 END +
        CASE WHEN COALESCE(vase.symptom_count, 0) >= 3 THEN 1 ELSE 0 END +
        CASE WHEN vase.avg_systolic >= 160 OR vase.avg_diastolic >= 100 THEN 1 ELSE 0 END +
        CASE WHEN vase.glucose_value >= 15 THEN 1 ELSE 0 END +
        CASE WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric >= 9 THEN 1 ELSE 0 END +
        CASE WHEN COALESCE(plh.abnormal_result_count, 0) >= 2 THEN 1 ELSE 0 END
    ) AS composite_risk_score,
    CASE
        WHEN (
            CASE WHEN vase.is_red_risk_patient = TRUE THEN 2 ELSE 0 END +
            CASE WHEN vase.crisis_referral_status = 'Crisis Referral' THEN 2 ELSE 0 END +
            CASE WHEN COALESCE(vase.lifestyle_risk_score, 0) >= 2 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(vase.symptom_count, 0) >= 3 THEN 1 ELSE 0 END +
            CASE WHEN vase.avg_systolic >= 160 OR vase.avg_diastolic >= 100 THEN 1 ELSE 0 END +
            CASE WHEN vase.glucose_value >= 15 THEN 1 ELSE 0 END +
            CASE WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric >= 9 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(plh.abnormal_result_count, 0) >= 2 THEN 1 ELSE 0 END
        ) >= 5 THEN 'Critical'
        WHEN (
            CASE WHEN vase.is_red_risk_patient = TRUE THEN 2 ELSE 0 END +
            CASE WHEN vase.crisis_referral_status = 'Crisis Referral' THEN 2 ELSE 0 END +
            CASE WHEN COALESCE(vase.lifestyle_risk_score, 0) >= 2 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(vase.symptom_count, 0) >= 3 THEN 1 ELSE 0 END +
            CASE WHEN vase.avg_systolic >= 160 OR vase.avg_diastolic >= 100 THEN 1 ELSE 0 END +
            CASE WHEN vase.glucose_value >= 15 THEN 1 ELSE 0 END +
            CASE WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric >= 9 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(plh.abnormal_result_count, 0) >= 2 THEN 1 ELSE 0 END
        ) >= 3 THEN 'High'
        WHEN (
            CASE WHEN vase.is_red_risk_patient = TRUE THEN 2 ELSE 0 END +
            CASE WHEN vase.crisis_referral_status = 'Crisis Referral' THEN 2 ELSE 0 END +
            CASE WHEN COALESCE(vase.lifestyle_risk_score, 0) >= 2 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(vase.symptom_count, 0) >= 3 THEN 1 ELSE 0 END +
            CASE WHEN vase.avg_systolic >= 160 OR vase.avg_diastolic >= 100 THEN 1 ELSE 0 END +
            CASE WHEN vase.glucose_value >= 15 THEN 1 ELSE 0 END +
            CASE WHEN plh.latest_hba1c ~ '^[0-9]+\.?[0-9]*$' AND plh.latest_hba1c::numeric >= 9 THEN 1 ELSE 0 END +
            CASE WHEN COALESCE(plh.abnormal_result_count, 0) >= 2 THEN 1 ELSE 0 END
        ) >= 1 THEN 'Moderate'
        ELSE 'Low'
    END AS risk_category
FROM v_analytics_screening_enhanced vase
LEFT JOIN v_patient_lab_history plh ON plh.patient_track_id = vase.patient_track_id;

COMMENT ON VIEW v_high_risk_patients IS 'High-risk patient identification combining clinical, lifestyle, and lab factors';
