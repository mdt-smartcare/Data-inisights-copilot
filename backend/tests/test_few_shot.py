import unittest
from unittest.mock import MagicMock, patch
from backend.services.agent_service import AgentService

class TestFewShot(unittest.TestCase):
    
    def setUp(self):
        # Patch dependencies
        self.settings_patcher = patch("backend.services.agent_service.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.openai_api_key = "dummy"
        self.mock_settings.openai_model = "gpt-4o"
        self.mock_settings.openai_temperature = 0
        
        self.db_service_patcher = patch("backend.services.agent_service.get_db_service")
        self.mock_get_db_service = self.db_service_patcher.start()
        
        self.sql_service_patcher = patch("backend.services.agent_service.get_sql_service")
        self.mock_sql_service = self.sql_service_patcher.start()
        
        self.embedding_patcher = patch("backend.services.agent_service.get_embedding_model")
        self.mock_get_embedding_model = self.embedding_patcher.start()
        self.mock_embedding_model = MagicMock()
        self.mock_get_embedding_model.return_value = self.mock_embedding_model
        # Mock embedding return (list of floats)
        self.mock_embedding_model.embed_query.return_value = [0.1, 0.2, 0.3]
        
        self.llm_patcher = patch("backend.services.agent_service.ChatOpenAI")
        self.mock_llm = self.llm_patcher.start()
        
        # Mock DB examples
        self.mock_examples = [
            {"question": "How many patients have HTN?", "sql_query": "SELECT count(*) FROM htn", "created_at": "2024-01-01"},
            {"question": "List all smokers", "sql_query": "SELECT * FROM smokers", "created_at": "2024-01-01"},
            {"question": "Show referrals", "sql_query": "SELECT * FROM withdrawals", "created_at": "2024-01-01"},
            {"question": "Count visits", "sql_query": "SELECT count(*) FROM visits", "created_at": "2024-01-01"},
        ]
        self.mock_get_db_service.return_value.get_sql_examples.return_value = self.mock_examples

    def tearDown(self):
        self.settings_patcher.stop()
        self.db_service_patcher.stop()
        self.sql_service_patcher.stop()
        self.embedding_patcher.stop()
        self.llm_patcher.stop()

    def test_example_retrieval(self):
        """Test that examples are retrieved and formatted."""
        service = AgentService()
        
        # Test retrieval
        query = "How many patients have hypertension?"
        examples = service._get_relevant_examples(query)
        
        print(f"Retrieved {len(examples)} examples")
        self.assertTrue(len(examples) > 0)
        self.assertTrue(len(examples) <= 3)
        
        first_example = examples[0]
        self.assertIn("Q: ", first_example)
        self.assertIn("SQL: ", first_example)
        
        # Check if HTN example is present (since keywords overlap)
        htn_present = any("HTN" in ex for ex in examples)
        self.assertTrue(htn_present)

    def test_empty_examples(self):
        """Test behavior when no examples exist."""
        self.mock_get_db_service.return_value.get_sql_examples.return_value = []
        service = AgentService()
        examples = service._get_relevant_examples("query")
        self.assertEqual(len(examples), 0)

if __name__ == '__main__':
    unittest.main()
