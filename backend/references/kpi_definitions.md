# NCD Dashboard KPI Definitions Reference
# This document provides semantic context for the RAG system to understand dashboard metrics

## Screening & Referral KPIs

### 1. Screened for BP (Blood Pressure Screening)
- **Definition**: Unique patients with NCD workflow who have recorded systolic AND diastolic blood pressure readings
- **Filter**: workflow_status = 'NCD' AND has_bp_reading = TRUE
- **Source Table**: v_analytics_screening

### 2. Screened for BG (Blood Glucose Screening)  
- **Definition**: Unique patients with NCD workflow who have a recorded glucose value
- **Filter**: workflow_status = 'NCD' AND has_bg_reading = TRUE
- **Source Table**: v_analytics_screening

### 3. Patients Screened Above 40
- **Definition**: Patients screened for BP/BG who are 40 years or older
- **Filter**: is_above_40 = TRUE

### 4. People Referred
- **Definition**: Unique patients with NCD screening who were marked as referred
- **Filter**: workflow_status = 'NCD' AND is_referred = TRUE

### 5. Referred Due to Elevated BP
- **Definition**: Patients referred because of high blood pressure readings
- **Thresholds**: systolic >= 140 OR diastolic >= 90
- **Filter**: referred_reason IN ('Due to Elevated BP', 'Due to Elevated BP & BG')

### 6. Referred Due to Elevated BG
- **Definition**: Patients referred because of high blood glucose readings
- **Thresholds**: 
  - FBS >= 7.0 mmol/L
  - RBS >= 11.1 mmol/L
  - HbA1c >= 5.7%
- **Filter**: referred_reason IN ('Due to Elevated BG', 'Due to Elevated BP & BG')

### 7. Crisis Referrals
- **Definition**: Patients with critically high readings requiring urgent care
- **Thresholds**:
  - Crisis BP: systolic >= 180 OR diastolic >= 110
  - Crisis Glucose: >= 18 mmol/L
- **Filter**: crisis_referral_status = 'Crisis Referral'

### 8. Screening Yield (%)
- **Definition**: Proportion of screened patients who were referred
- **Formula**: (Screening Referrals / Total Screened) * 100

### 9. HTN Prevalence (%)
- **Definition**: Proportion of patients screened for BP who were referred due to elevated BP
- **Formula**: (Elevated BP Referrals / Screened for BP) * 100

### 10. DBM Prevalence (%)
- **Definition**: Proportion of patients screened for BG who were referred due to elevated BG
- **Formula**: (Elevated BG Referrals / Screened for BG) * 100

### 11. New vs Existing Diagnoses
- **New Diagnoses**: Patients with elevated readings who had no prior diagnosis (is_before_htn_diagnosis = FALSE or is_before_diabetes_diagnosis = FALSE)
- **Existing Diagnoses**: Patients with prior known diagnosis

---

## Enrollment KPIs

### 1. Total Enrolled
- **Definition**: Unique patients with NCD workflow marked as ENROLLED
- **Filter**: patient_status = 'ENROLLED' AND workflow_status = 'NCD'

### 2. Enrolled by Condition
- **Hypertension Only**: enrolled_condition = 'Hypertension'
- **Diabetes Only**: enrolled_condition = 'Diabetes'  
- **Co-morbid (Both HTN + DBM)**: enrolled_condition = 'Co-morbid (DBM + HTN)'
- **Provisional**: enrolled_condition = 'Provisional Diagnosis'

### 3. Community Enrolled
- **Definition**: Patients enrolled through community screening (not direct facility enrollment)
- **Filter**: is_screening = TRUE AND patient_status = 'ENROLLED'

### 4. % Community Enrolled
- **Formula**: (Community Enrolled / Total Enrolled) * 100

### 5. Crisis Referral Enrolled
- **Definition**: Patients enrolled who had crisis-level readings at screening
- **Filter**: patient_status = 'ENROLLED' AND crisis_referral_status = 'Crisis Referral'

### 6. % Crisis HTN Enrolled
- **Formula**: (Crisis HTN Enrolled / Crisis Referral Enrolled) * 100
- **Filter for numerator**: crisis_referral_htn = 'Referred to UHC'

### 7. % Crisis DBM Enrolled  
- **Formula**: (Crisis DBM Enrolled / Crisis Referral Enrolled) * 100
- **Filter for numerator**: crisis_referral_dbm = 'Referred to UHC'

---

## Site Level Classifications

- **Upazila Health Complex (UHC)**: site_level = 'Level 1' - Higher-level facility for crisis cases
- **Community Clinic (CC)**: site_level = 'Level 6' - Primary care facility for routine cases

---

## Clinical Thresholds Reference

| Condition | Metric | Normal | Elevated | Crisis |
|-----------|--------|--------|----------|--------|
| Blood Pressure | Systolic | < 140 | >= 140 | >= 180 |
| Blood Pressure | Diastolic | < 90 | >= 90 | >= 110 |
| Fasting Blood Sugar (FBS) | mmol/L | < 7.0 | >= 7.0 | >= 18 |
| Random Blood Sugar (RBS) | mmol/L | < 11.1 | >= 11.1 | >= 18 |
| HbA1c | % | < 5.7 | >= 5.7 | N/A |

---

## Workflow Status

- **NCD**: Non-Communicable Disease screening (Hypertension, Diabetes)
- **Para Counselling**: Mental health / counseling workflow (excluded from NCD KPIs)
