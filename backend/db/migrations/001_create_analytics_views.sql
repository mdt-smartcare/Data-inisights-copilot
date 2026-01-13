-- ============================================================================
-- Migration: 001_create_analytics_views.sql
-- Purpose: Create materialized views that match Power BI dashboard logic
-- Author: RAG System Alignment
-- Date: 2026-01-08
-- Updated: 2026-01-09 - Fixed to match actual DB schema structure
-- ============================================================================

-- Drop existing views if they exist
DROP VIEW IF EXISTS v_analytics_enrollment CASCADE;
DROP VIEW IF EXISTS v_analytics_screening CASCADE;

-- ============================================================================
-- VIEW: v_analytics_screening
-- ============================================================================
CREATE OR REPLACE VIEW v_analytics_screening AS
WITH workflow_details AS (
    SELECT
        acw.account_id,
        STRING_AGG(cw.name, ',' ORDER BY cw.name) AS workflow_name
    FROM account_clinical_workflow acw
    JOIN clinical_workflow cw ON cw.id = acw.clinical_workflow_id
    WHERE acw.account_id NOT IN (9)
    GROUP BY acw.account_id
),
cte_site AS (
    SELECT DISTINCT ON (id)
        id AS site_id,
        name AS site_name,
        country_id,
        county_id,
        sub_county_id,
        city,
        account_id,
        site_level
    FROM site
    ORDER BY id, updated_at DESC
),
latest_patient_tracker AS (
    SELECT DISTINCT ON (id)
        id AS patient_track_id,
        gender,
        age,
        enrollment_at,
        screening_referral,
        is_red_risk_patient,
        is_pregnant,
        screening_id,
        is_screening,
        patient_status,
        site_id,
        referred_site_id
    FROM patient_tracker
    WHERE is_deleted = FALSE
    ORDER BY id, updated_at DESC
),
latest_screening_log AS (
    SELECT DISTINCT ON (id)
        id AS screening_id,
        avg_systolic,
        avg_diastolic,
        glucose_value,
        glucose_type,
        is_before_htn_diagnosis,
        is_before_diabetes_diagnosis,
        category,
        bmi,
        site_id,
        created_at,
        created_by
    FROM screening_log
    ORDER BY id, updated_at DESC
)
SELECT
    pt.patient_track_id,
    pt.gender,
    pt.age,
    pt.enrollment_at::date AS enrollment_at,
    pt.screening_referral,
    pt.is_red_risk_patient,
    pt.is_pregnant,
    pt.screening_id,
    pt.is_screening,
    pt.patient_status,
    
    -- Screening data
    sl.created_at::date AS screening_date,
    sl.avg_systolic,
    sl.avg_diastolic,
    sl.glucose_value,
    sl.glucose_type,
    sl.is_before_htn_diagnosis,
    sl.is_before_diabetes_diagnosis,
    sl.category,
    sl.bmi,
    sl.created_by,
    
    -- Site info
    s.site_name,
    s.site_level,
    
    -- Workflow Status (NCD vs Para Counselling)
    CASE
        WHEN wd.workflow_name ILIKE '%Para counselling%' THEN 'Para Counselling'
        ELSE 'NCD'
    END AS workflow_status,
    
    -- Referred Reason
    CASE
        WHEN (
            (sl.avg_diastolic >= 90 OR sl.avg_systolic >= 140)
            AND (
                (sl.glucose_type = 'fbs' AND sl.glucose_value >= 7.0)
                OR (sl.glucose_type = 'rbs' AND sl.glucose_value >= 11.1)
                OR (sl.glucose_type = 'hba1c' AND sl.glucose_value >= 5.7)
            )
        ) THEN 'Due to Elevated BP & BG'
        WHEN (
            (sl.glucose_type = 'fbs' AND sl.glucose_value >= 7.0)
            OR (sl.glucose_type = 'rbs' AND sl.glucose_value >= 11.1)
            OR (sl.glucose_type = 'hba1c' AND sl.glucose_value >= 5.7)
        ) THEN 'Due to Elevated BG'
        WHEN (sl.avg_diastolic >= 90 OR sl.avg_systolic >= 140)
        THEN 'Due to Elevated BP'
        ELSE 'Others'
    END AS referred_reason,
    
    -- Crisis Referral Status
    CASE
        WHEN (sl.avg_diastolic >= 110 OR sl.avg_systolic >= 180) OR sl.glucose_value >= 18
        THEN 'Crisis Referral'
        ELSE 'Others'
    END AS crisis_referral_status,
    
    -- Crisis Referral HTN
    CASE
        WHEN (sl.avg_diastolic >= 110 OR sl.avg_systolic >= 180)
        THEN 'Referred to UHC'
        ELSE 'Referred to CC'
    END AS crisis_referral_htn,
    
    -- Crisis Referral DBM
    CASE
        WHEN sl.glucose_value >= 18
        THEN 'Referred to UHC'
        ELSE 'Referred to CC'
    END AS crisis_referral_dbm,
    
    -- HTN New vs Existing Diagnoses
    CASE
        WHEN sl.is_before_htn_diagnosis = TRUE THEN 'Existing Diagnoses'
        WHEN sl.is_before_htn_diagnosis = FALSE
             AND (sl.avg_diastolic >= 90 OR sl.avg_systolic >= 140)
        THEN 'New Diagnoses'
        ELSE NULL
    END AS htn_new_vs_existing,
    
    -- DBM New vs Existing Diagnoses
    CASE
        WHEN sl.is_before_diabetes_diagnosis = TRUE THEN 'Existing Diagnoses'
        WHEN sl.is_before_diabetes_diagnosis = FALSE
             AND (
                 (sl.glucose_type = 'fbs' AND sl.glucose_value NOT BETWEEN 4 AND 7)
                 OR (sl.glucose_type = 'rbs' AND sl.glucose_value NOT BETWEEN 4 AND 10)
             )
        THEN 'New Diagnoses'
        ELSE NULL
    END AS dbm_new_vs_existing,
    
    -- Site Level Filter
    CASE
        WHEN s.site_level = 'Level 1' THEN 'Upazila Health Complex'
        WHEN s.site_level = 'Level 6' THEN 'Community Clinic'
        ELSE 'Others'
    END AS site_level_filter,
    
    -- Pregnant Status
    CASE
        WHEN pt.is_pregnant IS TRUE THEN 'Yes'
        ELSE 'No'
    END AS pregnant_status,
    
    -- Flags for easy filtering
    CASE WHEN sl.avg_systolic IS NOT NULL AND sl.avg_diastolic IS NOT NULL THEN TRUE ELSE FALSE END AS has_bp_reading,
    CASE WHEN sl.glucose_value IS NOT NULL THEN TRUE ELSE FALSE END AS has_bg_reading,
    CASE WHEN pt.screening_referral = TRUE THEN TRUE ELSE FALSE END AS is_referred,
    CASE WHEN pt.age >= 40 THEN TRUE ELSE FALSE END AS is_above_40

FROM latest_patient_tracker pt
LEFT JOIN latest_screening_log sl ON sl.screening_id = pt.screening_id
LEFT JOIN cte_site s ON s.site_id = pt.site_id
LEFT JOIN workflow_details wd ON wd.account_id = s.account_id;

-- ============================================================================
-- VIEW: v_analytics_enrollment  
-- Using is_htn_diagnosis/is_diabetes_diagnosis boolean flags
-- ============================================================================
CREATE OR REPLACE VIEW v_analytics_enrollment AS
WITH confirm_diagnosis AS (
    SELECT 
        patient_track_id,
        CASE
            WHEN BOOL_OR(is_htn_diagnosis = TRUE) AND BOOL_OR(is_diabetes_diagnosis = TRUE)
            THEN 'Co-morbid (DBM + HTN)'
            WHEN BOOL_OR(is_htn_diagnosis = TRUE)
            THEN 'Hypertension'
            WHEN BOOL_OR(is_diabetes_diagnosis = TRUE)
            THEN 'Diabetes'
            ELSE 'Provisional Diagnosis'
        END AS enrolled_condition
    FROM patient_diagnosis
    WHERE is_deleted = FALSE
    GROUP BY patient_track_id
)
SELECT
    vas.*,
    COALESCE(cd.enrolled_condition, 'Provisional Diagnosis') AS enrolled_condition
FROM v_analytics_screening vas
LEFT JOIN confirm_diagnosis cd ON cd.patient_track_id = vas.patient_track_id;

COMMENT ON VIEW v_analytics_screening IS 'Pre-computed screening analytics matching Power BI dashboard logic';
COMMENT ON VIEW v_analytics_enrollment IS 'Pre-computed enrollment analytics matching Power BI dashboard logic';
