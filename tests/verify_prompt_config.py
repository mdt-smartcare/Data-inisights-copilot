import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import asyncio

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock settings before importing agent_service to avoid validation errors
with patch('backend.config.get_settings') as mock_settings:
    mock_settings.return_value.openai_api_key = "sk-test"
    mock_settings.return_value.openai_model = "gpt-4"
    mock_settings.return_value.openai_temperature = 0
    mock_settings.return_value.embedding_model_name = "text-embedding-3-small"
    
    from backend.services.agent_service import AgentService

class TestAgentConfig(unittest.IsolatedAsyncioTestCase):
    
    @patch('backend.services.agent_service.get_sql_service')
    @patch('backend.services.agent_service.get_db_service')
    @patch('backend.services.agent_service.get_vector_store')
    @patch('backend.services.agent_service.get_embedding_model')
    @patch('backend.services.agent_service.ChatOpenAI')
    @patch('backend.services.agent_service.create_tool_calling_agent')
    @patch('backend.services.agent_service.AgentExecutor')
    async def test_missing_config_raises_error(self, mock_exec, mock_agent, mock_llm, mock_embed, mock_vec, mock_db, mock_sql):
        """Verify processing query fails when no prompt is configured."""
        
        # Setup mocks
        mock_db_instance = MagicMock()
        mock_db_instance.get_latest_active_prompt.return_value = None  # SIMULATE MISSING CONFIG
        mock_db.return_value = mock_db_instance
        
        # Mocks to pass init
        mock_sql.return_value._check_dashboard_kpi.return_value = None # Bypass fast path

        # Initialize service
        service = AgentService()
        
        # execution
        try:
            await service.process_query("test query")
            self.fail("Should have raised ValueError")
        except ValueError as e:
            print(f"\nCaught expected error: {e}")
            self.assertIn("System Not Configured", str(e))
        except Exception as e:
            self.fail(f"Raised wrong exception type: {type(e)}")

    @patch('backend.services.agent_service.get_sql_service')
    @patch('backend.services.agent_service.get_db_service')
    @patch('backend.services.agent_service.get_vector_store')
    @patch('backend.services.agent_service.get_embedding_model')
    @patch('backend.services.agent_service.ChatOpenAI')
    @patch('backend.services.agent_service.create_tool_calling_agent')
    @patch('backend.services.agent_service.AgentExecutor')
    async def test_valid_config_succeeds(self, mock_exec, mock_agent, mock_llm, mock_embed, mock_vec, mock_db, mock_sql):
        """Verify processing query succeeds when prompt IS configured."""
         # Setup mocks
        mock_db_instance = MagicMock()
        mock_db_instance.get_latest_active_prompt.return_value = "You are a test agent."
        mock_db.return_value = mock_db_instance
        
        mock_sql.return_value._check_dashboard_kpi.return_value = None # Bypass fast path

        # Mock executor instance
        mock_executor_instance = MagicMock()
        mock_executor_instance.invoke.return_value = {
            "output": "Test answer", 
            "intermediate_steps": []
        }
        mock_exec.return_value = mock_executor_instance

        # Initialize service
        service = AgentService()
        
        # execution
        try:
            result = await service.process_query("test query")
            self.assertIn("answer", result)
            print("\nSuccess with valid config")
        except Exception as e:
            self.fail(f"Should not have raised exception: {e}")

if __name__ == "__main__":
    unittest.main()
