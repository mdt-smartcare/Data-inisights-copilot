# NCD Screening Rwanda - Test Questions Suite

This document contains test questions for the healthcare analytics chatbot, organized by query type (SQL, RAG, Hybrid) and expected chart visualization.

---

## 📊 SQL QUERIES (Intent A) - Structured Data Analytics

### Gauge Charts (Single KPI vs Target)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 1 | What is the diabetes control rate? | Gauge | Rate as % vs 80% target |
| 2 | What is the hypertension screening coverage? | Gauge | Coverage % |
| 3 | What percentage of patients have controlled blood pressure? | Gauge | Control rate |
| 4 | What is the overall NCD screening rate? | Gauge | Screening coverage |
| 5 | What is the treatment adherence rate? | Gauge | Adherence % |

---

### Funnel Charts (Care Cascades)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 6 | Show the NCD care cascade | Funnel | Screened → Diagnosed → Treated → Controlled |
| 7 | Show the diabetes care cascade | Funnel | Patient journey stages |
| 8 | What is the patient journey from screening to treatment? | Funnel | Sequential dropoff |
| 9 | Show the hypertension care funnel | Funnel | BP management stages |
| 10 | How many patients drop off at each stage of care? | Funnel | Attrition analysis |

---

### Bullet Charts (Performance vs Targets)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 11 | Compare facility screening rates vs targets | Bullet | Multiple facilities vs 80% target |
| 12 | How are different locations performing against screening targets? | Bullet | Location performance |
| 13 | Show district-wise performance against NCD targets | Bullet | District KPIs |
| 14 | Compare health center screening achievements vs goals | Bullet | Achievement tracking |
| 15 | Which facilities are meeting their screening targets? | Bullet | Target comparison |

---

### Horizontal Bar Charts (Rankings)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 16 | Which locations have the highest number of cases? | Horizontal Bar | Top 10 locations |
| 17 | Which districts have the most NCD patients? | Horizontal Bar | District ranking |
| 18 | Top 10 facilities by patient volume | Horizontal Bar | Volume ranking |
| 19 | Which areas have the lowest screening rates? | Horizontal Bar | Bottom performers |
| 20 | Rank locations by diabetes prevalence | Horizontal Bar | Prevalence ranking |

---

### Bar Charts (Categorical Comparisons)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 21 | Breakdown of patients by age group | Bar | Age distribution |
| 22 | Distribution of screenings by encounter type | Bar | Encounter categories |
| 23 | Number of patients by diagnosis category | Bar | Diagnosis breakdown |
| 24 | Screening counts by health facility type | Bar | Facility type comparison |
| 25 | Distribution of patients by risk level | Bar | Risk stratification |

---

### Pie Charts (Proportions/Distributions)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 26 | Male vs female patient distribution | Pie | Gender split |
| 27 | What percentage of patients are male vs female? | Pie | Gender % |
| 28 | Distribution of patients by gender | Pie | Gender proportions |
| 29 | Proportion of controlled vs uncontrolled diabetes | Pie | Control status |
| 30 | Percentage of new vs returning patients | Pie | Patient type split |

---

### Line Charts (Trends Over Time)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 31 | Show monthly screening trend | Line | Time series |
| 32 | How has screening volume changed over time? | Line | Volume trend |
| 33 | Trend of NCD cases by month | Line | Monthly trend |
| 34 | Show quarterly screening progress | Line | Quarterly data |
| 35 | Year-over-year comparison of screenings | Line | YoY comparison |

---

### Treemap Charts (Regional/Hierarchical)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 36 | Distribution of patients by region | Treemap | Regional hierarchy |
| 37 | Show patient distribution by district | Treemap | District breakdown |
| 38 | Geographic distribution of NCD screenings | Treemap | Location hierarchy |
| 39 | Distribution of encounters by location | Treemap | Location sizes |
| 40 | Regional breakdown of diabetes cases | Treemap | Regional diabetes |

---

### Scorecard Charts (Single Values/Counts)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 41 | Total number of patients screened | Scorecard | Simple count |
| 42 | How many screenings were done last month? | Scorecard | Monthly total |
| 43 | Total number of health facilities | Scorecard | Facility count |
| 44 | Count of unique patients in the system | Scorecard | Unique patients |
| 45 | Total encounters recorded | Scorecard | Encounter count |

---

### Aggregation Queries (Various Charts)

| # | Question | Expected Chart | Notes |
|---|----------|----------------|-------|
| 46 | Average age of diabetic patients | Scorecard | Mean calculation |
| 47 | What is the average screening rate by district? | Bar | District averages |
| 48 | Count of patients by age group and gender | Bar (Stacked) | Multi-dimensional |
| 49 | Sum of screenings by facility | Horizontal Bar | Volume sums |
| 50 | Min and max ages of patients | Scorecard | Range stats |

---

## 📄 RAG QUERIES (Intent B) - Unstructured Document Search

These questions search clinical notes, documents, and narrative text.

| # | Question | Expected Output | Notes |
|---|----------|-----------------|-------|
| 51 | Find patient notes about diabetes complications | Text snippets | Semantic search |
| 52 | Show clinical summaries for hypertension cases | Document excerpts | Note retrieval |
| 53 | What do the notes say about patient treatment plans? | Narrative text | Treatment docs |
| 54 | Find documentation about NCD screening protocols | Protocol docs | Procedure search |
| 55 | Search for clinical notes mentioning medication adherence | Text results | Keyword + semantic |
| 56 | Tell me about the patient with ID 356512 | Patient record | Specific lookup |
| 57 | Find notes about patients with uncontrolled blood sugar | Clinical notes | Condition search |
| 58 | What guidelines exist for NCD management? | Guideline docs | Policy search |
| 59 | Show recent clinical observations for diabetic patients | Observation notes | Recent notes |
| 60 | Find documentation about lifestyle interventions | Intervention docs | Treatment search |

---

## 🔀 HYBRID QUERIES (Intent C) - SQL Filter + RAG Search

These questions combine numerical filtering with semantic document search.

| # | Question | SQL Filter | RAG Search | Notes |
|---|----------|------------|------------|-------|
| 61 | Summarize notes for patients with glucose > 200 | Filter by glucose level | Search notes | High glucose patients |
| 62 | Find clinical notes for patients diagnosed last month | Filter by date | Search notes | Recent diagnoses |
| 63 | Show treatment notes for patients over 65 years old | Filter by age | Search treatment docs | Elderly patients |
| 64 | What do notes say about patients with uncontrolled BP? | Filter by BP status | Search notes | Uncontrolled cases |
| 65 | Find observations for high-risk diabetic patients | Filter by risk level | Search observations | Risk-based search |
| 66 | Summarize care plans for patients in Kigali region | Filter by location | Search care plans | Regional notes |
| 67 | Show notes for patients with multiple comorbidities | Filter by condition count | Search notes | Complex patients |
| 68 | Find documentation for patients missing follow-ups | Filter by follow-up status | Search docs | Lost to follow-up |
| 69 | Clinical notes for patients on insulin therapy | Filter by medication | Search notes | Insulin patients |
| 70 | Treatment summaries for newly diagnosed cases | Filter by diagnosis date | Search summaries | New patients |

---

## 🧪 EDGE CASES & STRESS TESTS

### Ambiguous Queries (Should Route Correctly)

| # | Question | Expected Intent | Reasoning |
|---|----------|-----------------|-----------|
| 71 | Tell me about diabetes | B (RAG) | Conceptual, not aggregation |
| 72 | Diabetes patient count | A (SQL) | Counting = SQL |
| 73 | Patient information | B (RAG) | Vague, needs documents |
| 74 | How many patients have diabetes? | A (SQL) | Explicit count |
| 75 | What is diabetes? | B (RAG) | Definition query |

### Complex Multi-Part Queries

| # | Question | Expected Behavior |
|---|----------|-------------------|
| 76 | Show me the total patients by gender and their age distribution | SQL with stacked/grouped bar |
| 77 | Compare screening rates across regions and show the trend | Multiple visualizations |
| 78 | Which district has the highest diabetes rate and what are the risk factors? | Hybrid: SQL + RAG |
| 79 | Give me a complete overview of NCD screening performance | Dashboard-style response |
| 80 | Analyze the care cascade and identify bottlenecks | Funnel + insights |

### Temporal Queries

| # | Question | Time Context |
|---|----------|--------------|
| 81 | Screenings done today | Current day |
| 82 | Patients screened this week | Last 7 days |
| 83 | Monthly trend for 2023 | Specific year |
| 84 | Compare Q1 vs Q2 performance | Quarterly comparison |
| 85 | Year-to-date screening progress | YTD aggregation |

### Negative/Null Handling

| # | Question | Expected Handling |
|---|----------|-------------------|
| 86 | How many patients have unknown gender? | Count NULL/Unknown |
| 87 | Patients with missing screening dates | NULL date handling |
| 88 | Facilities with zero screenings | Zero-value handling |
| 89 | Locations with no diabetes cases | Empty result handling |
| 90 | Patients without contact information | Missing data query |

---

## 📋 QUICK REFERENCE: Chart Type Selection

| Question Pattern | Chart Type |
|------------------|------------|
| "What is the ___ rate/percentage?" | **Gauge** |
| "Show the care cascade / funnel / journey" | **Funnel** |
| "Compare ___ vs targets" | **Bullet** |
| "Which has highest/lowest / Top N / Rank" | **Horizontal Bar** |
| "Breakdown by category / by type" | **Bar** |
| "Distribution / proportion / percentage of" | **Pie** |
| "Trend / over time / monthly / yearly" | **Line** |
| "Distribution by region / district / location" | **Treemap** |
| "Total / Count / How many" (single value) | **Scorecard** |

---

## 🚀 EXECUTION CHECKLIST

### Before Testing
- [ ] Backend server running
- [ ] Frontend connected
- [ ] Database connection active
- [ ] Vector store loaded (for RAG queries)
- [ ] System prompt configured for NCD domain

### Test Execution
- [ ] Run 5 queries from each SQL chart category
- [ ] Run 3 RAG queries
- [ ] Run 3 Hybrid queries
- [ ] Verify chart renders correctly
- [ ] Check data accuracy
- [ ] Note response times

### Post-Test Validation
- [ ] All chart types rendered
- [ ] No console errors
- [ ] Correct intent routing (check logs)
- [ ] Reasonable response times (<5s for SQL, <10s for RAG)

---

## 📊 SAMPLE EXPECTED RESPONSES

### Example 1: Gauge Chart Response
**Question:** "What is the diabetes control rate?"
```json
{
  "type": "gauge",
  "title": "Diabetes Control Rate",
  "value": 88.6,
  "min": 0,
  "max": 100,
  "target": 80,
  "thresholds": [
    {"value": 80, "color": "#10b981", "label": "Good"},
    {"value": 60, "color": "#f59e0b", "label": "Fair"},
    {"value": 0, "color": "#ef4444", "label": "Poor"}
  ]
}
```

### Example 2: Funnel Chart Response
**Question:** "Show the NCD care cascade"
```json
{
  "type": "funnel",
  "title": "NCD Care Cascade",
  "data": {
    "labels": ["Screened", "Diagnosed", "On Treatment", "Controlled"],
    "values": [676614, 450000, 320000, 250000]
  }
}
```

### Example 3: Bullet Chart Response
**Question:** "Compare facility screening rates vs targets"
```json
{
  "type": "bullet",
  "title": "Facility Screening Rates vs Targets",
  "data": {
    "labels": ["Facility A", "Facility B", "Facility C"],
    "values": [0.75, 0.62, 0.88],
    "target": 0.8
  }
}
```

---

*Last Updated: March 2026*
*Data Source: NCD Screening Rwanda Dataset*
