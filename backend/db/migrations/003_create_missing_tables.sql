-- ============================================================================
-- Migration: 003_create_missing_tables.sql
-- Purpose: Create missing tables for lifestyle, symptoms, lab results, and user roles
-- Author: RAG System Alignment
-- Date: 2026-01-09
-- Note: These tables are referenced in Data Dictionary but were not in RAG views
-- ============================================================================

-- ============================================================================
-- TABLE: userrole
-- Purpose: Map user IDs to their roles for screener identification
-- Source: 1. Screening & Referral.txt (CTE cte_userrole)
-- ============================================================================
CREATE TABLE IF NOT EXISTS userrole (
    user_role_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    role_id INTEGER,
    role_name VARCHAR(100) NOT NULL,
    tenant_id INTEGER,
    created_by INTEGER,
    updated_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_userrole_user_id ON userrole(user_id);
CREATE INDEX IF NOT EXISTS idx_userrole_role_name ON userrole(role_name);

COMMENT ON TABLE userrole IS 'User role mappings for health workers (SHASTHYA KORMI, CHCP, MEDICAL OFFICER, etc.)';

-- ============================================================================
-- TABLE: patientlifestyle
-- Purpose: Store patient lifestyle factors for NCD risk assessment
-- Source: Data Dictionary - patientlifestyle
-- ============================================================================
CREATE TABLE IF NOT EXISTS patientlifestyle (
    patient_lifestyle_id SERIAL PRIMARY KEY,
    patient_track_id INTEGER NOT NULL,
    lifestyle_type VARCHAR(50) NOT NULL,  -- 'smoking', 'alcohol', 'physical_activity', 'diet'
    lifestyle_value VARCHAR(100),          -- 'current', 'former', 'never', 'regular', 'sedentary', etc.
    lifestyle_details TEXT,                -- Additional notes
    tenant_id INTEGER,
    created_by INTEGER,
    updated_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_patientlifestyle_patient_track_id ON patientlifestyle(patient_track_id);
CREATE INDEX IF NOT EXISTS idx_patientlifestyle_type ON patientlifestyle(lifestyle_type);

COMMENT ON TABLE patientlifestyle IS 'Patient lifestyle factors: smoking, alcohol, diet, physical activity';

-- ============================================================================
-- TABLE: patientsymptom
-- Purpose: Store patient-reported symptoms for clinical context
-- Source: Data Dictionary - patientsymptom
-- ============================================================================
CREATE TABLE IF NOT EXISTS patientsymptom (
    patient_symptom_id SERIAL PRIMARY KEY,
    patient_track_id INTEGER NOT NULL,
    symptom_name VARCHAR(100) NOT NULL,    -- 'headache', 'dizziness', 'blurred vision', etc.
    symptom_severity VARCHAR(20),          -- 'mild', 'moderate', 'severe'
    symptom_duration VARCHAR(50),          -- 'acute', 'chronic', 'intermittent'
    symptom_notes TEXT,
    reported_date DATE,
    tenant_id INTEGER,
    created_by INTEGER,
    updated_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_patientsymptom_patient_track_id ON patientsymptom(patient_track_id);
CREATE INDEX IF NOT EXISTS idx_patientsymptom_name ON patientsymptom(symptom_name);

COMMENT ON TABLE patientsymptom IS 'Patient-reported symptoms for NCD monitoring (headache, dizziness, vision issues, etc.)';

-- ============================================================================
-- TABLE: patientlabtestresult
-- Purpose: Store lab test results for biomarker tracking
-- Source: Data Dictionary - patientlabtestresult
-- ============================================================================
CREATE TABLE IF NOT EXISTS patientlabtestresult (
    lab_result_id SERIAL PRIMARY KEY,
    patient_track_id INTEGER NOT NULL,
    test_name VARCHAR(100) NOT NULL,       -- 'HbA1c', 'FBS', 'Creatinine', 'Cholesterol', etc.
    test_value NUMERIC(10, 2),
    test_unit VARCHAR(20),                 -- 'mmol/L', '%', 'mg/dL', etc.
    reference_range_min NUMERIC(10, 2),
    reference_range_max NUMERIC(10, 2),
    is_abnormal BOOLEAN,
    test_date DATE,
    lab_name VARCHAR(200),
    ordering_provider_id INTEGER,
    tenant_id INTEGER,
    created_by INTEGER,
    updated_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_patientlabtestresult_patient_track_id ON patientlabtestresult(patient_track_id);
CREATE INDEX IF NOT EXISTS idx_patientlabtestresult_test_name ON patientlabtestresult(test_name);
CREATE INDEX IF NOT EXISTS idx_patientlabtestresult_test_date ON patientlabtestresult(test_date);
CREATE INDEX IF NOT EXISTS idx_patientlabtestresult_abnormal ON patientlabtestresult(is_abnormal) WHERE is_abnormal = TRUE;

COMMENT ON TABLE patientlabtestresult IS 'Lab test results for biomarker tracking (HbA1c, FBS, creatinine, cholesterol, etc.)';

-- ============================================================================
-- Add foreign key constraints (optional - uncomment if patienttracker exists)
-- ============================================================================
-- ALTER TABLE patientlifestyle 
--     ADD CONSTRAINT fk_lifestyle_patient_track 
--     FOREIGN KEY (patient_track_id) REFERENCES patienttracker(patient_track_id);
-- 
-- ALTER TABLE patientsymptom 
--     ADD CONSTRAINT fk_symptom_patient_track 
--     FOREIGN KEY (patient_track_id) REFERENCES patienttracker(patient_track_id);
-- 
-- ALTER TABLE patientlabtestresult 
--     ADD CONSTRAINT fk_labresult_patient_track 
--     FOREIGN KEY (patient_track_id) REFERENCES patienttracker(patient_track_id);

-- ============================================================================
-- Grant permissions (adjust role names as needed)
-- ============================================================================
-- GRANT SELECT ON userrole TO readonly_role;
-- GRANT SELECT ON patientlifestyle TO readonly_role;
-- GRANT SELECT ON patientsymptom TO readonly_role;
-- GRANT SELECT ON patientlabtestresult TO readonly_role;
