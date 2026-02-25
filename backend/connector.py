import os
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class DatabaseConnector:
    def __init__(self, config_path="config/db_config.yaml"):
        load_dotenv()
        self.config = self._load_config(config_path)
        self.engine = None
        self.connection = None
        self.is_connected = False

    def _load_config(self, config_path):
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            return None

    def connect(self):
        if self.is_connected and self.connection:
            return True
        try:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not set.")
            
            logger.info("Connecting to database...")
            self.engine = create_engine(database_url, pool_size=20, max_overflow=50, pool_timeout=60)
            self.connection = self.engine.connect()
            self.connection.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
            self.is_connected = True
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        if self.connection:
            self.connection.close()
        if self.engine:
            self.engine.dispose()
        self.is_connected = False
        logger.info("Database connection closed.")

    def execute_query(self, query, params=None):
        if not self.is_connected:
            if not self.connect():
                raise Exception("No database connection available")
        try:
            result = self.connection.execute(text(query), params or {})
            return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Query execution failed: {e}")
            return []

    def get_all_tables(self):
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        results = self.execute_query(query)
        return [row[0] for row in results] if results else []

# Singleton instance
db_connector = DatabaseConnector()