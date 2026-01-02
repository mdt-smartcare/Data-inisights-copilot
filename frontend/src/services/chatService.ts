import { apiClient } from './api';
import { API_ENDPOINTS } from '../config';
import type { ChatRequest, ChatResponse } from '../types';

// Mock mode flag - set to false when backend is ready
const USE_MOCK_DATA = true;

// Mock responses for development
const mockResponses: Record<string, ChatResponse> = {
  default: {
    answer: `# FHIR Patient Resource Overview

The **Patient** resource is one of the core FHIR resources. Here are the key components:

## Essential Elements

1. **Identifier** - Unique patient identifiers
2. **Name** - Human names (given, family, prefix, suffix)
3. **Telecom** - Contact details (phone, email)
4. **Gender** - Administrative gender
5. **Birth Date** - Date of birth
6. **Address** - Physical addresses

## Example Structure

\`\`\`json
{
  "resourceType": "Patient",
  "id": "example",
  "identifier": [{
    "system": "http://hospital.org/mrn",
    "value": "12345"
  }],
  "name": [{
    "family": "Doe",
    "given": ["John"]
  }]
}
\`\`\`

The Patient resource supports rich demographic information and is foundational for healthcare interoperability.`,
    sources: [
      {
        content: "FHIR Patient Resource - The Patient resource covers data about patients involved in a wide range of health-related activities, including curative activities, psychiatric care, social services, pregnancy care, nursing and assisted living, dietary services, tracking of personal health and exercise data, and more.",
        metadata: { table: "fhir_documentation", score: 0.95 }
      },
      {
        content: "Patient demographics include identifiers, names, addresses, contact information, gender, birth date, and other administrative attributes that are needed to support administrative, financial and logistic procedures.",
        metadata: { table: "fhir_spec", score: 0.89 }
      }
    ],
    sql_query: "SELECT * FROM patient_resources WHERE resource_type = 'Patient' LIMIT 10;",
    suggested_questions: [
      "What are the required fields for a FHIR Patient resource?",
      "How do I link a Patient to an Observation?",
      "What is the difference between Patient and Person resources?"
    ],
    chart_data: {
      type: "bar",
      title: "Patient Resource Usage in Database",
      data: [
        { name: "Active", value: 1234 },
        { name: "Inactive", value: 456 },
        { name: "Deceased", value: 89 },
        { name: "Unknown", value: 123 }
      ],
      xKey: "name",
      yKey: "value"
    },
    conversation_id: "mock-conv-" + Date.now(),
    timestamp: new Date().toISOString(),
    trace_id: "mock-trace-" + Math.random().toString(36).substring(7),
    processing_time: 2.34
  },
  diabetes: {
    answer: `# Diabetes Patient Analysis

Based on the database query, here are the findings:

## Summary
There are **1,234 patients** diagnosed with diabetes in the system.

### Key Statistics
- **Type 1 Diabetes**: 345 patients (28%)
- **Type 2 Diabetes**: 889 patients (72%)
- **Average Age**: 54.3 years
- **Gender Distribution**: 52% Female, 48% Male

### Common Medications
1. Metformin - 67% of patients
2. Insulin - 45% of patients
3. Glipizide - 23% of patients

The data shows a higher prevalence of Type 2 diabetes, which is consistent with national trends.`,
    sources: [
      {
        content: "Patient diagnosis data for diabetes mellitus shows 1,234 active cases with various treatment protocols.",
        metadata: { table: "patient_diagnosis", score: 0.98 }
      }
    ],
    sql_query: `SELECT 
  diagnosis_type, 
  COUNT(*) as patient_count,
  AVG(age) as avg_age
FROM patient_diagnosis 
WHERE diagnosis_code LIKE 'E11%' OR diagnosis_code LIKE 'E10%'
GROUP BY diagnosis_type;`,
    suggested_questions: [
      "What is the age distribution of diabetic patients?",
      "Which medications are most commonly prescribed?",
      "Show me the trend of new diabetes diagnoses over the past year"
    ],
    chart_data: {
      type: "pie",
      title: "Diabetes Type Distribution",
      data: [
        { name: "Type 1", value: 345 },
        { name: "Type 2", value: 889 }
      ]
    },
    conversation_id: "mock-conv-" + Date.now(),
    timestamp: new Date().toISOString(),
    trace_id: "mock-trace-" + Math.random().toString(36).substring(7),
    processing_time: 3.45
  }
};

function getMockResponse(query: string): ChatResponse {
  const lowerQuery = query.toLowerCase();
  
  if (lowerQuery.includes('diabetes') || lowerQuery.includes('diabetic')) {
    return { ...mockResponses.diabetes, timestamp: new Date().toISOString() };
  }
  
  return { ...mockResponses.default, timestamp: new Date().toISOString() };
}

export const chatService = {
  sendMessage: async (request: ChatRequest): Promise<ChatResponse> => {
    if (USE_MOCK_DATA) {
      // Simulate network delay
      await new Promise(resolve => setTimeout(resolve, 1500));
      return getMockResponse(request.query);
    }
    
    const response = await apiClient.post<ChatResponse>(
      API_ENDPOINTS.CHAT,
      request
    );
    return response.data;
  },

  getConversationHistory: async (conversationId: string) => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 500));
      return { messages: [], conversation_id: conversationId };
    }
    
    const response = await apiClient.get(
      `${API_ENDPOINTS.CHAT}/${conversationId}`
    );
    return response.data;
  },
};
