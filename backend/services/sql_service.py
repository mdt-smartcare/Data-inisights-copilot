"""
SQL service for structured database queries.
Wraps LangChain SQL agent for database interactions.
"""
from functools import lru_cache
from typing import Optional

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class SQLService:
    """Service for SQL database operations."""
    
    def __init__(self):
        """Initialize SQL database connection and agent."""
        logger.info(f"Connecting to database at {settings.database_url}")
        
        try:
            # Initialize database connection
            self.db = SQLDatabase.from_uri(settings.database_url)
            logger.info("Database connection established")
            
            # Initialize LLM
            self.llm = ChatOpenAI(
                temperature=settings.openai_temperature,
                model_name=settings.openai_model,
                api_key=settings.openai_api_key
            )
            
            # Create SQL agent
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=self.db,
                agent_type="openai-tools",
                verbose=settings.debug
            )
            logger.info("SQL agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQL service: {e}", exc_info=True)
            raise
    
    def query(self, question: str) -> str:
        """
        Execute a natural language query against the database.
        
        Args:
            question: Natural language question
        
        Returns:
            SQL agent response as string
        """
        logger.info(f"Executing SQL query for: '{question[:100]}...'")
        
        try:
            result = self.sql_agent.invoke({"input": question})
            
            # Extract output from agent result
            if isinstance(result, dict):
                output = result.get("output", str(result))
            else:
                output = str(result)
            
            logger.info(f"SQL query completed. Result length: {len(output)} chars")
            return output
            
        except Exception as e:
            logger.error(f"SQL query failed: {e}", exc_info=True)
            raise
    
    def health_check(self) -> bool:
        """
        Check if database is accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Execute a simple query
            result = self.db.run("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_table_info(self) -> str:
        """
        Get database schema information.
        
        Returns:
            Table information as string
        """
        try:
            return self.db.get_table_info()
        except Exception as e:
            logger.error(f"Failed to get table info: {e}", exc_info=True)
            return "Error retrieving table information"


@lru_cache()
def get_sql_service() -> SQLService:
    """
    Get cached SQL service instance.
    Singleton pattern to reuse database connections.
    
    Returns:
        Cached SQL service
    """
    return SQLService()
