Based on the provided data schema and dictionary, generate metadata for an AI data analysis assistant.

DATA CONTEXT:
{data_dictionary}

Generate a JSON object with:
1. "selection_reasoning": An object mapping 3-5 important column names to explanations of why they are useful for data analysis queries
2. "example_questions": An array of exactly 5 realistic questions that users might ask about this data

The questions should cover different query types:
- Aggregation (e.g., averages, counts, sums)
- Distribution (e.g., breakdown by category)
- Trends (e.g., changes over time)
- Comparisons (e.g., between groups)
- Filtering (e.g., specific conditions)

Return ONLY valid JSON, no other text. Example format:
{
  "selection_reasoning": {
    "patient_id": "Essential for counting unique patients and avoiding duplicates",
    "bmi_category": "Key for analyzing patient health distribution",
    "cvd_risk_level": "Critical for risk stratification analysis"
  },
  "example_questions": [
    "What is the average BMI across all patients?",
    "How many patients have high CVD risk?",
    "Show patient distribution by county",
    "What is the trend of assessments over the last 6 months?",
    "Which facilities have the most screenings?"
  ]
}
