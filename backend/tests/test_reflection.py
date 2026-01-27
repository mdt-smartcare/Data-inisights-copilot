import unittest
from unittest.mock import MagicMock, patch
from backend.services.sql_service import SQLService
from backend.models.schemas import CritiqueResponse

class TestReflectionLoop(unittest.TestCase):
    
    def setUp(self):
        # Patch dependencies
        self.settings_patcher = patch("backend.services.sql_service.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.database_url = "sqlite:///:memory:"
        self.mock_settings.openai_api_key = "dummy"
        
        self.sql_db_patcher = patch("backend.services.sql_service.SQLDatabase")
        self.mock_sql_db = self.sql_db_patcher.start()
        self.mock_sql_db.from_uri.return_value.get_usable_table_names.return_value = []
        
        self.llm_patcher = patch("backend.services.sql_service.ChatOpenAI")
        self.mock_llm = self.llm_patcher.start()
        
        self.agent_patcher = patch("backend.services.sql_service.create_sql_agent")
        self.mock_agent = self.agent_patcher.start()
        
        self.db_service_patcher = patch("backend.services.sql_service.get_db_service")
        self.mock_get_db_service = self.db_service_patcher.start()
        self.mock_get_db_service.return_value.get_active_metrics.return_value = []
        
        self.critique_patcher = patch("backend.services.sql_service.get_critique_service")
        self.mock_get_critique_service = self.critique_patcher.start()
        self.mock_critique_service = self.mock_get_critique_service.return_value

    def tearDown(self):
        self.settings_patcher.stop()
        self.sql_db_patcher.stop()
        self.llm_patcher.stop()
        self.agent_patcher.stop()
        self.db_service_patcher.stop()
        self.critique_patcher.stop()

    def test_reflection_retry(self):
        """Test that invalid SQL triggers retry loop."""
        service = SQLService()
        
        # Test query
        question = "Count smokers"
        
        # Mock LLM responses (First attempt bad, Second attempt good)
        bad_sql = "SELECT * FROM broken_table"
        good_sql = "SELECT count(*) FROM patient_tracker WHERE is_smoker=1"
        
        # Mock llm_fast.invoke().content
        # First call generates bad SQL, Second call generates good SQL
        mock_response_1 = MagicMock()
        mock_response_1.content = bad_sql
        mock_response_2 = MagicMock()
        mock_response_2.content = good_sql
        
        service.llm_fast = MagicMock()
        service.llm_fast.invoke.side_effect = [mock_response_1, mock_response_2]
        
        # Mock Critique Service
        # First critique: Fail
        critique_fail = CritiqueResponse(
            is_valid=False, 
            issues=["Table broken_table does not exist"], 
            reasoning="Bad table",
            corrected_sql=None
        )
        # Second critique: Pass
        critique_pass = CritiqueResponse(
            is_valid=True, 
            issues=[], 
            reasoning="LGTM",
            corrected_sql=None
        )
        
        self.mock_critique_service.critique_sql.side_effect = [critique_fail, critique_pass]
        
        # Call _execute_optimized (we need to bypass _is_simple_query check usually, 
        # but here we can just call the method directly)
        
        # Also mock _validate_sql_query (simple regex safety) to pass for both
        with patch.object(service, '_validate_sql_query', return_value=True):
             # Mock DB run to prevent actual execution error on bad SQL (though logic shouldn't run it if invalid?)
             # The code runs critique loop BEFORE execution. But waits, if valid it runs.
             # We want to assert that it eventually runs the GOOD sql.
             service.db.run.return_value = "Run result"
             
             # Mock schema
             service.cached_schema = "Schema info"
             service._get_relevant_schema = MagicMock(return_value="Schema info")
             
             # Call method
             service._execute_optimized(question)
             
             # Assertions
             # 1. Critique called twice
             self.assertEqual(self.mock_critique_service.critique_sql.call_count, 2)
             
             # 2. LLM invoked twice (Initial gen + Fix)
             self.assertEqual(service.llm_fast.invoke.call_count, 2)
             
             # 3. DB run called with GOOD sql
             service.db.run.assert_called_with(good_sql)

if __name__ == '__main__':
    unittest.main()
