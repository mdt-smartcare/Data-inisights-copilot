-- ============================================================================
-- Migration: 001_create_analytics_views.sql (LOCAL PostgreSQL Version)
-- Purpose: Create views that match Power BI dashboard logic
-- Note: This version uses snake_case table names for local PostgreSQL
-- ============================================================================

-- Drop existing views if they exist
DROP VIEW IF EXISTS v_analytics_enrollment CASCADE;
DROP VIEW IF EXISTS v_analytics_screening CASCADE;

-- ============================================================================
-- VIEW: v_analytics_screening
-- Purpose: Pre-compute all screening & referral KPIs matching dashboard logic
-- ============================================================================
CREATE OR REPLACE VIEW v_analytics_screening AS
WITH workflow_details AS (
    SELECT
        account_id,
        STRING_AGG(workflow_name, ',' ORDER BY workflow_name) AS workflow_name
    FROM (
        SELECT DISTINCT 
            acw.account_id,
            cw.name AS workflow_name
        FROM account_clinical_workflow acw
        JOIN clinical_workflow cw ON acw.clinical_workflow_id = cw.id
        WHERE acw.account_id != 9
    ) sub
    GROUP BY account_id
),
cte_site AS (
    SELECT DISTINCT ON (id)
        id AS site_id,
        name AS site_name,
        country_id,
        county_id,
        sub_county_id,
        city,
        site_level,
        account_id,
        tenant_id,
        updated_at
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
        referred_site_id,
        union_id,
        patient_id
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
    
    -- Site info
    s.site_name,
    s.site_level,
    
    -- ========================================================================
    -- DERIVED FIELDS: Match exact dashboard logic from references
    -- ========================================================================
    
    -- Workflow Status (NCD vs Para Counselling)
    CASE
        WHEN wd.workflow_name ILIKE '%Para counselling%' THEN 'Para Counselling'
        ELSE 'NCD'
    END AS workflow_status,
    
    -- Referred Reason (exact thresholds from 1. Screening & Referral.txt)
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
    
    -- Crisis Referral Status (exact thresholds from dashboard)
    CASE
        WHEN (sl.avg_diastolic >= 110 OR sl.avg_systolic >= 180)
             OR sl.glucose_value >= 18
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
LEFT JOIN cte_site s ON s.site_id = COALESCE(sl.site_id, pt.site_id)
LEFT JOIN workflow_details wd ON wd.account_id = s.account_id;

-- ============================================================================
-- VIEW: v_analytics_enrollment  
-- Purpose: Pre-compute enrollment KPIs matching dashboard logic
-- ============================================================================
CREATE OR REPLACE VIEW v_analytics_enrollment AS
SELECT
    vas.*,
    -- Enrolled condition based on patient_diagnosis
    CASE
        WHEN pd.is_htn_diagnosis = TRUE AND pd.is_diabetes_diagnosis = TRUE 
        THEN 'Co-morbid (DBM + HTN)'
        WHEN pd.is_htn_diagnosis = TRUE 
        THEN 'Hypertension'
        WHEN pd.is_diabetes_diagnosis = TRUE 
        THEN 'Diabetes'
        ELSE 'Provisional Diagnosis'
    END AS enrolled_condition
FROM v_analytics_screening vas
LEFT JOIN (
    SELECT DISTINCT ON (patient_track_id)
        patient_track_id,
        is_htn_diagnosis,
        is_diabetes_diagnosis
    FROM patient_diagnosis
    WHERE is_deleted = FALSE
    ORDER BY patient_track_id, updated_at DESC
) pd ON pd.patient_track_id = vas.patient_track_id;

-- ============================================================================
-- Add comments for documentation
-- ============================================================================
COMMENT ON VIEW v_analytics_screening IS 'Pre-computed screening analytics matching Power BI dashboard logic. Source: 1. Screening & Referral.txt';
COMMENT ON VIEW v_analytics_enrollment IS 'Pre-computed enrollment analytics matching Power BI dashboard logic. Source: 2. Enrollment.txt';

-- Verify the views were created
SELECT 'v_analytics_screening created with ' || COUNT(*) || ' rows' AS status FROM v_analytics_screening
UNION ALL
SELECT 'v_analytics_enrollment created with ' || COUNT(*) || ' rows' AS status FROM v_analytics_enrollment;
