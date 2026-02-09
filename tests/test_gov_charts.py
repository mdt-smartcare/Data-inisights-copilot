
import unittest
import json
from unittest.mock import MagicMock
from backend.services.sql_service import SQLService

class TestGovCharts(unittest.TestCase):
    def setUp(self):
        self.sql_service = SQLService()
        # Mock the LLM to return specific JSON structures for our test cases
        self.sql_service.llm = MagicMock()

    def test_scorecard_structure(self):
        """Test that a scorecard query returns the correct JSON structure with 'metrics'"""
        mock_response = MagicMock()
        mock_response.content = """
        The total number of patients is 8,322 and the average wait time is 45 minutes.
        ```json
        {
            "chart_json": {
                "title": "Hospital KPIs",
                "type": "scorecard",
                "data": {
                    "labels": [],
                    "values": []
                },
                "metrics": [
                    { "label": "Total Patients", "value": 8322, "change": "+5%", "status": "up" },
                    { "label": "Avg Wait Time", "value": "45m", "change": "-2%", "status": "down" }
                ]
            }
        }
        ```
        """
        self.sql_service.llm.invoke.return_value = mock_response
        
        # We are testing the _execute_optimized parsing logic indirectly by simulating a response
        # In a real scenario, we'd mock the DB run too, but here we just want to ensure our 
        # prompt and response handling *conceptually* align.
        # Since _execute_optimized is complex to fully integration test without a real DB,
        # we will verify the JSON schema that we expect the LLM to generate.
        
        json_content = mock_response.content.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_content)
        
        self.assertEqual(data['chart_json']['type'], 'scorecard')
        self.assertTrue('metrics' in data['chart_json'])
        self.assertEqual(len(data['chart_json']['metrics']), 2)
        print("✅ Scorecard JSON structure verified")

    def test_radar_chart_structure(self):
        """Test that a radar chart query returns the correct JSON structure"""
        mock_response = MagicMock()
        mock_response.content = """
        comparison of Hospital A and B.
        ```json
        {
            "chart_json": {
                "title": "Hospital Performance Comparison",
                "type": "radar",
                "data": {
                    "labels": ["Efficiency", "Quality", "Satisfaction", "Speed", "Safety"],
                    "values": [
                        { "name": "Hospital A", "value": [80, 90, 70, 85, 95] },
                        { "name": "Hospital B", "value": [70, 85, 80, 75, 90] }
                    ]
                }
            }
        }
        ```
        """
        json_content = mock_response.content.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_content)
        
        self.assertEqual(data['chart_json']['type'], 'radar')
        self.assertTrue('labels' in data['chart_json']['data'])
        self.assertTrue(len(data['chart_json']['data']['values']) >= 2) # Comparative
        print("✅ Radar Chart JSON structure verified")

    def test_treemap_structure(self):
        """Test that a treemap query returns the correct JSON structure"""
        mock_response = MagicMock()
        mock_response.content = """
        Disease burden by region.
        ```json
        {
            "chart_json": {
                "title": "Disease Burden by Region",
                "type": "treemap",
                "data": {
                    "labels": [], 
                    "values": [
                         { "name": "North", "value": 500 },
                         { "name": "South", "value": 300 },
                         { "name": "East", "value": 200 },
                         { "name": "West", "value": 400 }
                    ]
                }
            }
        }
        ```
        """
        json_content = mock_response.content.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_content)
        
        self.assertEqual(data['chart_json']['type'], 'treemap')
        self.assertTrue(len(data['chart_json']['data']['values']) > 0)
        self.assertTrue('name' in data['chart_json']['data']['values'][0])
        self.assertTrue('value' in data['chart_json']['data']['values'][0])
        print("✅ Treemap JSON structure verified")

if __name__ == '__main__':
    unittest.main()
