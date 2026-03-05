-- Migration: Add operational configuration settings (data_privacy, medical_context, chunking, vector_store)
-- Created: 2026-03-02
-- Purpose: Migrate static YAML configuration to database-backed system_settings
--
-- This migration seeds the operational configuration categories with defaults
-- previously stored in backend/config/embedding_config.yaml
-- 
-- Categories:
--   - data_privacy: PII protection rules (global_exclude_columns, exclude_tables, table_specific_exclusions)
--   - medical_context: Clinical terminology mappings and flag prefixes
--   - chunking: Text chunking parameters for embedding pipeline
--   - vector_store: Vector database configuration

-- ============================================================================
-- Data Privacy Settings (PII Protection Rules)
-- ============================================================================
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('data_privacy', 'global_exclude_columns', '["first_name", "last_name", "phone_number", "date_of_birth", "qr_code", "mother_name", "father_name", "mother_occupation", "father_occupation", "mother_educational_qualification", "father_educational_qualification", "password", "national_id", "email", "address", "social_security_number"]', 'json', 'Columns to exclude globally from embedding (PII protection)');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('data_privacy', 'exclude_tables', '["audit", "awsdms_ddl_audit", "deleted_site_program", "duplicate_profile", "email_template", "flyway_schema_history", "form_meta_ui", "offline_log", "outbound_email", "outbound_sms", "shedlock", "site_report_log", "sms_template", "sms_template_values", "updated_duplicate_patient_profile", "user_token"]', 'json', 'Tables to exclude entirely from embedding');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('data_privacy', 'table_specific_exclusions', '{"patient": ["first_name", "last_name", "phone_number", "date_of_birth", "qr_code", "mother_name", "father_name", "mother_occupation", "father_occupation", "mother_educational_qualification", "father_educational_qualification"], "patient_tracker": ["first_name", "last_name", "phone_number", "date_of_birth", "qr_code"], "call_register": ["first_name", "last_name", "phone_number"], "user": ["first_name", "last_name", "phone_number", "password", "username"]}', 'json', 'Table-specific column exclusions');

-- ============================================================================
-- Medical Context Settings (Clinical Terminology)
-- ============================================================================
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('medical_context', 'terminology_mappings', '{
  "bp": "Blood Pressure",
  "bp_systolic": "Systolic Blood Pressure",
  "bp_diastolic": "Diastolic Blood Pressure",
  "hr": "Heart Rate",
  "pulse": "Pulse Rate",
  "rr": "Respiratory Rate",
  "spo2": "Oxygen Saturation (SpO2)",
  "temp": "Body Temperature",
  "temperature": "Body Temperature",
  "bmi": "Body Mass Index",
  "height": "Height",
  "weight": "Weight",
  "waist_circumference": "Waist Circumference",
  "hip_circumference": "Hip Circumference",
  "hba1c": "Glycated Hemoglobin (HbA1c)",
  "fbs": "Fasting Blood Sugar",
  "rbs": "Random Blood Sugar",
  "ppbs": "Post-Prandial Blood Sugar",
  "glucose": "Blood Glucose",
  "fasting_glucose": "Fasting Glucose Level",
  "cholesterol": "Total Cholesterol",
  "hdl": "HDL Cholesterol (Good)",
  "ldl": "LDL Cholesterol (Bad)",
  "triglycerides": "Triglycerides",
  "vldl": "VLDL Cholesterol",
  "creatinine": "Serum Creatinine",
  "bun": "Blood Urea Nitrogen",
  "egfr": "Estimated Glomerular Filtration Rate (eGFR)",
  "uric_acid": "Uric Acid",
  "sgot": "SGOT (AST) Liver Enzyme",
  "sgpt": "SGPT (ALT) Liver Enzyme",
  "alp": "Alkaline Phosphatase",
  "bilirubin": "Bilirubin",
  "albumin": "Serum Albumin",
  "hb": "Hemoglobin",
  "hemoglobin": "Hemoglobin Level",
  "wbc": "White Blood Cell Count",
  "rbc": "Red Blood Cell Count",
  "platelet": "Platelet Count",
  "platelets": "Platelet Count",
  "pcv": "Packed Cell Volume (Hematocrit)",
  "tsh": "Thyroid Stimulating Hormone",
  "t3": "Triiodothyronine (T3)",
  "t4": "Thyroxine (T4)",
  "ft3": "Free T3",
  "ft4": "Free T4",
  "cvd_risk": "Cardiovascular Disease Risk Score",
  "cvd_risk_score": "CVD Risk Assessment Score",
  "risk_level": "Risk Classification Level",
  "patient_track_id": "Patient Tracking ID",
  "encounter_id": "Clinical Encounter ID",
  "visit_id": "Visit Identifier",
  "screening_id": "Screening Session ID",
  "medication_name": "Medication Name",
  "dosage": "Medication Dosage",
  "frequency": "Dosing Frequency",
  "prescription_id": "Prescription ID",
  "diagnosis_code": "Diagnosis Code",
  "icd_code": "ICD Diagnosis Code",
  "condition": "Medical Condition",
  "comorbidity": "Comorbid Condition",
  "phq9_score": "PHQ-9 Depression Score",
  "phq4_score": "PHQ-4 Mental Health Score",
  "gad7_score": "GAD-7 Anxiety Score",
  "audit_score": "AUDIT Alcohol Use Score"
}', 'json', 'Medical terminology mappings (column_name -> human readable name)');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('medical_context', 'clinical_flag_prefixes', '["is_", "has_", "was_", "history_of_", "flag_", "confirmed_", "requires_", "on_"]', 'json', 'Column prefixes that indicate clinical boolean flags');

-- ============================================================================
-- Chunking Settings (Text Processing for Embedding Pipeline)
-- ============================================================================
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('chunking', 'parent_chunk_size', '800', 'number', 'Parent chunk size for hierarchical chunking');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('chunking', 'parent_chunk_overlap', '150', 'number', 'Overlap between parent chunks');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('chunking', 'child_chunk_size', '200', 'number', 'Child chunk size for hierarchical chunking');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('chunking', 'child_chunk_overlap', '50', 'number', 'Overlap between child chunks');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('chunking', 'min_chunk_length', '50', 'number', 'Minimum chunk length to index');

-- ============================================================================
-- Vector Store Settings
-- ============================================================================
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('vector_store', 'type', '"chroma"', 'string', 'Vector store type (chroma, pinecone, qdrant, weaviate)');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('vector_store', 'default_collection', '"default_collection"', 'string', 'Default vector store collection name');

INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('vector_store', 'chroma_base_path', '"./data/indexes"', 'string', 'Base path for ChromaDB indexes');
