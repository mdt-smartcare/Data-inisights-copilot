-- Create metric_definitions table
CREATE TABLE IF NOT EXISTS metric_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    regex_pattern TEXT NOT NULL,
    sql_template TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for performance (optional for small tables but good practice)
CREATE INDEX IF NOT EXISTS idx_metric_definitions_priority ON metric_definitions(priority);

-- Migrate existing KPIs from sql_service.py
-- PRIORITY 0: COMBINED/COMPOUND QUERIES
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('smokers_high_risk_breakdown', 'high-risk patients by smoking status', '(critical|high).?risk.*smok|smok.*(critical|high).?risk', 
'SELECT 
    risk_category,
    COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
    COUNT(DISTINCT CASE WHEN is_smoker = FALSE OR is_smoker IS NULL THEN patient_track_id END) as non_smokers,
    COUNT(DISTINCT patient_track_id) as total
FROM v_high_risk_patients 
WHERE workflow_status = ''NCD''
GROUP BY risk_category
ORDER BY CASE risk_category 
    WHEN ''Critical'' THEN 1 
    WHEN ''High'' THEN 2 
    WHEN ''Moderate'' THEN 3 
    ELSE 4 END', 0);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('critical_risk_smokers_count', 'critical risk patients who are smokers', 'smok.*(critical|high).?risk|(critical|high).?risk.*who.*smok', 
'SELECT 
    COUNT(DISTINCT patient_track_id) as critical_smokers
FROM v_high_risk_patients 
WHERE workflow_status = ''NCD'' 
AND risk_category = ''Critical''
AND is_smoker = TRUE', 0);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('smoking_rate_by_risk', 'smoking rate by risk category', 'risk.*categor.*smok|smok.*risk.*categor', 
'SELECT 
    risk_category,
    COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
    COUNT(DISTINCT patient_track_id) as total,
    ROUND(COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END)::numeric / 
          NULLIF(COUNT(DISTINCT patient_track_id), 0) * 100, 2) as smoking_rate_pct
FROM v_high_risk_patients 
WHERE workflow_status = ''NCD''
GROUP BY risk_category
ORDER BY CASE risk_category 
    WHEN ''Critical'' THEN 1 
    WHEN ''High'' THEN 2 
    WHEN ''Moderate'' THEN 3 
    ELSE 4 END', 0);

-- PRIORITY 1: High-Risk & Lifestyle Queries
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('high_risk_distribution', 'high-risk patient distribution by category', 'high.?risk.*patient|critical.*patient|risk.*(category|stratification)', 
'SELECT risk_category, COUNT(DISTINCT patient_track_id) as count
FROM v_high_risk_patients 
WHERE workflow_status = ''NCD''
GROUP BY risk_category
ORDER BY CASE risk_category 
    WHEN ''Critical'' THEN 1 
    WHEN ''High'' THEN 2 
    WHEN ''Moderate'' THEN 3 
    ELSE 4 END', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('smoking_status_ncd', 'smoking status among NCD patients', 'smoker|smoking.*patient', 
'SELECT 
    COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
    COUNT(DISTINCT CASE WHEN is_smoker = FALSE OR is_smoker IS NULL THEN patient_track_id END) as non_smokers,
    ROUND(COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END)::numeric / 
          NULLIF(COUNT(DISTINCT patient_track_id), 0) * 100, 2) as smoking_rate_pct
FROM v_analytics_screening_enhanced 
WHERE workflow_status = ''NCD''', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('lifestyle_risk_distribution', 'lifestyle risk score distribution', 'lifestyle.*risk|poor.*lifestyle', 
'SELECT 
    lifestyle_risk_score,
    COUNT(DISTINCT patient_track_id) as patient_count
FROM v_analytics_screening_enhanced 
WHERE workflow_status = ''NCD'' AND lifestyle_risk_score IS NOT NULL
GROUP BY lifestyle_risk_score
ORDER BY lifestyle_risk_score DESC', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('glycemic_control_distribution', 'glycemic control status distribution', 'glycemic.*control|hba1c.*control', 
'SELECT 
    glycemic_control_status,
    COUNT(DISTINCT patient_track_id) as patient_count
FROM v_analytics_enrollment_enhanced 
WHERE patient_status = ''ENROLLED'' AND workflow_status = ''NCD''
GROUP BY glycemic_control_status
ORDER BY CASE glycemic_control_status
    WHEN ''Very Poorly Controlled'' THEN 1
    WHEN ''Poorly Controlled'' THEN 2
    WHEN ''Controlled Diabetic'' THEN 3
    WHEN ''Pre-Diabetic'' THEN 4
    WHEN ''Normal'' THEN 5
    ELSE 6 END', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('abnormal_lab_count', 'patients by abnormal lab result count', 'abnormal.*lab|lab.*abnormal', 
'SELECT 
    CASE 
        WHEN abnormal_result_count >= 3 THEN ''3+ abnormal''
        WHEN abnormal_result_count = 2 THEN ''2 abnormal''
        WHEN abnormal_result_count = 1 THEN ''1 abnormal''
        ELSE ''No abnormal''
    END as abnormal_category,
    COUNT(DISTINCT patient_track_id) as patient_count
FROM v_analytics_enrollment_enhanced 
WHERE patient_status = ''ENROLLED'' AND workflow_status = ''NCD''
GROUP BY abnormal_category
ORDER BY abnormal_result_count DESC', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('screening_by_role', 'screening counts by screener role', 'screener.*role|role.*screener|who.*screen', 
'SELECT 
    screener_role_name,
    COUNT(DISTINCT patient_track_id) as patients_screened
FROM v_analytics_screening_enhanced 
WHERE workflow_status = ''NCD'' AND screener_role_name IS NOT NULL
GROUP BY screener_role_name
ORDER BY patients_screened DESC', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('health_worker_performance', 'screening and referral by health worker role', 'shasthya kormi|chcp|medical officer', 
'SELECT 
    screener_role_name,
    COUNT(DISTINCT patient_track_id) as patients_screened,
    COUNT(DISTINCT CASE WHEN is_referred = TRUE THEN patient_track_id END) as patients_referred
FROM v_analytics_screening_enhanced 
WHERE workflow_status = ''NCD'' AND screener_role_name IS NOT NULL
GROUP BY screener_role_name
ORDER BY patients_screened DESC', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('symptom_prevalence', 'symptom prevalence among NCD patients', 'symptom|headache|dizziness|fatigue', 
'SELECT 
    COUNT(DISTINCT CASE WHEN has_headache = TRUE THEN patient_track_id END) as with_headache,
    COUNT(DISTINCT CASE WHEN has_dizziness = TRUE THEN patient_track_id END) as with_dizziness,
    COUNT(DISTINCT CASE WHEN has_fatigue = TRUE THEN patient_track_id END) as with_fatigue,
    COUNT(DISTINCT CASE WHEN has_vision_issues = TRUE THEN patient_track_id END) as with_vision_issues,
    COUNT(DISTINCT CASE WHEN has_chest_pain = TRUE THEN patient_track_id END) as with_chest_pain
FROM v_analytics_screening_enhanced 
WHERE workflow_status = ''NCD''', 1);

-- PRIORITY 1: Prevalence & Yield KPIs (Merged into Priority 1 bucket for simplicity, preserving specific regex)
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('htn_prevalence_general', 'HTN prevalence rate', 'htn.*(prevalence|rate)|prevalence.*(htn|hypertension|bp)', 
'SELECT 
    ROUND(
        (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
            AND referred_reason IN (''Due to Elevated BP'', ''Due to Elevated BP & BG'') 
            THEN patient_track_id END)::numeric / 
         NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
            THEN patient_track_id END), 0)) * 100, 
        2
    ) as htn_prevalence_pct
FROM v_analytics_screening 
WHERE workflow_status = ''NCD''', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('htn_prevalence_specific', 'HTN prevalence rate (specific)', 'hypertension.*(prevalence|rate)', 
'SELECT 
    ROUND(
        (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
            AND referred_reason IN (''Due to Elevated BP'', ''Due to Elevated BP & BG'') 
            THEN patient_track_id END)::numeric / 
         NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
            THEN patient_track_id END), 0)) * 100, 
        2
    ) as htn_prevalence_pct
FROM v_analytics_screening 
WHERE workflow_status = ''NCD''', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('dbm_prevalence_general', 'DBM prevalence rate', 'dbm.*(prevalence|rate)|prevalence.*(dbm|diabetes|glucose|bg)', 
'SELECT 
    ROUND(
        (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
            AND referred_reason IN (''Due to Elevated BG'', ''Due to Elevated BP & BG'') 
            THEN patient_track_id END)::numeric / 
         NULLIF(COUNT(DISTINCT CASE WHEN has_bg_reading = TRUE 
            THEN patient_track_id END), 0)) * 100, 
        2
    ) as dbm_prevalence_pct
FROM v_analytics_screening 
WHERE workflow_status = ''NCD''', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('dbm_prevalence_specific', 'DBM prevalence rate (specific)', 'diabetes.*(prevalence|rate)', 
'SELECT 
    ROUND(
        (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
            AND referred_reason IN (''Due to Elevated BG'', ''Due to Elevated BP & BG'') 
            THEN patient_track_id END)::numeric / 
         NULLIF(COUNT(DISTINCT CASE WHEN has_bg_reading = TRUE 
            THEN patient_track_id END), 0)) * 100, 
        2
    ) as dbm_prevalence_pct
FROM v_analytics_screening 
WHERE workflow_status = ''NCD''', 1);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('screening_yield', 'screening yield percentage', 'screening.*(yield|rate)', 
'SELECT 
    ROUND(
        (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
            AND referred_reason IN (''Due to Elevated BP'', ''Due to Elevated BG'', ''Due to Elevated BP & BG'') 
            THEN patient_track_id END)::numeric / 
         NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
            THEN patient_track_id END), 0)) * 100, 
        2
    ) as screening_yield_pct
FROM v_analytics_screening 
WHERE workflow_status = ''NCD''', 1);

-- PRIORITY 2: Referral KPIs
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('crisis_referrals', 'crisis referrals', 'crisis.*(referral|refer)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE crisis_referral_status = ''Crisis Referral''', 2);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('referrals_elevated_bp', 'patients referred due to elevated blood pressure', 'referred.*(elevated|high).*(bp|blood pressure)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE workflow_status = ''NCD'' 
AND is_referred = TRUE 
AND referred_reason IN (''Due to Elevated BP'', ''Due to Elevated BP & BG'')', 2);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('referrals_elevated_bg', 'patients referred due to elevated blood glucose', 'referred.*(elevated|high).*(bg|glucose|sugar)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE workflow_status = ''NCD'' 
AND is_referred = TRUE 
AND referred_reason IN (''Due to Elevated BG'', ''Due to Elevated BP & BG'')', 2);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('total_referrals', 'total patients referred', '(total|how many|count).*referred|people referred', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE workflow_status = ''NCD'' 
AND is_referred = TRUE', 2);

-- PRIORITY 3: Enrollment KPIs
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('enrollment_breakdown', 'enrollment breakdown by condition', 'enrolled.*by.*condition|breakdown.*enrolled', 
'SELECT enrolled_condition, COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND workflow_status = ''NCD''
AND enrolled_condition IS NOT NULL
GROUP BY enrolled_condition
ORDER BY count DESC', 3);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('enrollment_htn', 'patients enrolled with Hypertension', 'enrolled.*(hypertension|htn)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND workflow_status = ''NCD''
AND enrolled_condition = ''Hypertension''', 3);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('enrollment_dbm', 'patients enrolled with Diabetes', 'enrolled.*(diabetes|dbm)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND workflow_status = ''NCD''
AND enrolled_condition = ''Diabetes''', 3);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('enrollment_comorbid', 'patients enrolled with co-morbid conditions', 'enrolled.*co-?morbid', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND workflow_status = ''NCD''
AND enrolled_condition = ''Co-morbid (DBM + HTN)''', 3);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('community_enrollment', 'community enrolled patients', 'community.*(enrolled|enrollment)', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND is_screening = TRUE 
AND workflow_status = ''NCD''', 3);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('total_enrollment', 'total enrolled NCD patients', '(total|how many|count).*enrolled|enrolled.*ncd', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_enrollment 
WHERE patient_status = ''ENROLLED'' 
AND workflow_status = ''NCD''', 3);

-- PRIORITY 4: Screening KPIs
INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('screened_bp_count', 'patients screened for blood pressure', 'screened.*(bp|blood pressure)|(bp|blood pressure).*screened', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE workflow_status = ''NCD'' 
AND has_bp_reading = TRUE', 4);

INSERT OR IGNORE INTO metric_definitions (name, description, regex_pattern, sql_template, priority) VALUES 
('screened_bg_count', 'patients screened for blood glucose', 'screened.*(bg|glucose|blood glucose)|(bg|glucose).*screened', 
'SELECT COUNT(DISTINCT patient_track_id) as count
FROM v_analytics_screening 
WHERE workflow_status = ''NCD'' 
AND has_bg_reading = TRUE', 4);
