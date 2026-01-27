import unittest
from unittest.mock import MagicMock, patch
from backend.services.sql_service import SQLService

class TestMetricStore(unittest.TestCase):
    
    def setUp(self):
        # Patch settings
        self.settings_patcher = patch("backend.services.sql_service.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.database_url = "sqlite:///:memory:"
        self.mock_settings.openai_api_key = "dummy"
        
        # Patch SQLDatabase
        self.sql_db_patcher = patch("backend.services.sql_service.SQLDatabase")
        self.mock_sql_db = self.sql_db_patcher.start()
        self.mock_sql_db.from_uri.return_value.get_usable_table_names.return_value = []
        
        # Patch LLMs
        self.llm_patcher = patch("backend.services.sql_service.ChatOpenAI")
        self.mock_llm = self.llm_patcher.start()
        
        self.agent_patcher = patch("backend.services.sql_service.create_sql_agent")
        self.mock_agent = self.agent_patcher.start()

        # Patch get_db_service
        self.db_service_patcher = patch("backend.services.sql_service.get_db_service")
        self.mock_get_db_service = self.db_service_patcher.start()
        
        # Mock metrics return
        self.sample_metrics = [
            {
                "id": 1,
                "name": "htn_prevalence",
                "description": "HTN prevalence rate",
                "regex_pattern": "htn.*prevalence",
                "sql_template": "SELECT count(*) FROM htn_prevalence_pct",
                "priority": 1,
                "is_active": True
            },
            {
                "id": 2,
                "name": "smokers_high_risk",
                "description": "high-risk patients by smoking status",
                "regex_pattern": "smok.*risk|risk.*smok",
                "sql_template": "SELECT count(*) FROM is_smoker",
                "priority": 0,
                "is_active": True
            }
        ]
        self.mock_get_db_service.return_value.get_active_metrics.return_value = self.sample_metrics

    def tearDown(self):
        self.settings_patcher.stop()
        self.sql_db_patcher.stop()
        self.llm_patcher.stop()
        self.agent_patcher.stop()
        self.db_service_patcher.stop()

    def test_metric_loading(self):
        """Test that metrics are loaded from the service on initialization."""
        service = SQLService()
        
        # Verify we loaded metrics
        print(f"Loaded {len(service.metrics)} metrics")
        self.assertEqual(len(service.metrics), 2)
        
        # Check for a specific known metric
        htn_metric = next((m for m in service.metrics if "htn_prevalence" in m.name), None)
        self.assertIsNotNone(htn_metric)
        self.assertIn("prevalence", htn_metric.regex_pattern)

    def test_kpi_matching(self):
        """Test that questions match the correct metrics."""
        service = SQLService()
        
        # Test 1: HTN Prevalence
        question = "What is the HTN prevalence rate?"
        match = service._check_dashboard_kpi(question)
        self.assertIsNotNone(match)
        sql, description = match
        self.assertIn("htn_prevalence_pct", sql)
        self.assertIn("HTN prevalence rate", description)

        # Test 2: Smoking (High Risk) - Priority Check
        # This matches the "Priority 0" complex query
        question = "Show me high risk patients by smoking status"
        match = service._check_dashboard_kpi(question)
        self.assertIsNotNone(match)
        sql, description = match
        self.assertIn("is_smoker", sql)
        # Should match the first one: "high-risk patients by smoking status"
        self.assertEqual(description, "high-risk patients by smoking status")
        
        # Test 3: No match
        question = "What is the weather today?"
        match = service._check_dashboard_kpi(question)
        self.assertIsNone(match)

if __name__ == '__main__':
    unittest.main()
