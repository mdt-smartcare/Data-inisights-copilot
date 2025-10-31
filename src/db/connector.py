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
        """Load database configuration"""
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            # Fallback to direct credentials
            return {
                'database': {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'Spice_BD',
                    'username': 'admin',
                    'password': 'admin',
                    'schema': 'public'
                }
            }
    
    def connect(self):
        """Establish database connection with proper error handling"""
        if self.is_connected and self.connection:
            return True
            
        try:
            db_config = self.config['database']
            
            # Build connection string
            connection_string = (
                f"postgresql://{db_config['username']}:{db_config['password']}"
                f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
            )
            
            print(f" Connecting to database: {db_config['host']}:{db_config['port']}/{db_config['database']}")
            
            # Create engine
            self.engine = create_engine(connection_string)
            self.connection = self.engine.connect()
            
            # Test connection
            test_result = self.connection.execute(text("SELECT 1"))
            print("Database connection successful")
            self.is_connected = True
            return True
            
        except Exception as e:
            print(f"Database connection failed: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.engine:
            self.engine.dispose()
            self.engine = None
        self.is_connected = False
        print(" Database connection closed")
    
    def execute_query(self, query, params=None):
        """Execute a SQL query with connection check"""
        if not self.is_connected or not self.connection:
            if not self.connect():
                raise Exception("No database connection available")
        
        try:
            result = self.connection.execute(text(query), params or {})
            return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Query execution failed: {e}")
            return []
    
    def get_all_tables(self):
        """Get all tables in the database"""
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = :schema
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        results = self.execute_query(query, {
            "schema": self.config['database']['schema']
        })
        return [row[0] for row in results] if results else []
    
    def get_table_schema(self, table_name):
        """Get column information for a table"""
        query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name = :table_name 
        AND table_schema = :schema
        ORDER BY ordinal_position
        """
        return self.execute_query(query, {
            "table_name": table_name,
            "schema": self.config['database']['schema']
        })
    
    def get_table_row_count(self, table_name):
        """Get row count for a table"""
        query = f"SELECT COUNT(*) FROM {table_name}"
        result = self.execute_query(query)
        return result[0][0] if result else 0

# Singleton instance
db_connector = DatabaseConnector()