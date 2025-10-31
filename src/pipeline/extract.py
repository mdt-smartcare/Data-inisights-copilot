import pandas as pd
import yaml
from tqdm import tqdm
import logging
from src.db.connector import db_connector

logger = logging.getLogger(__name__)

class DataExtractor:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.config = self._load_config(config_path)
        self.excluded_tables = set(self.config['tables']['exclude_tables'])
    
    def _load_config(self, config_path):
        """Load embedding configuration"""
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def get_allowed_tables(self):
        """Get list of tables that are allowed for processing"""
        all_tables = db_connector.get_all_tables()
        allowed_tables = [table for table in all_tables if table not in self.excluded_tables]
        logger.info(f"Found {len(allowed_tables)} tables to process (excluding {len(self.excluded_tables)} tables)")
        return allowed_tables
    
    def get_table_columns(self, table_name):
        """Get safe columns for a table (excluding PII columns)"""
        try:
            schema = db_connector.get_table_schema(table_name)
            all_columns = [col[0] for col in schema]
            
            # Apply global exclusions
            global_exclude = set(self.config['tables']['global_exclude_columns'])
            safe_columns = [col for col in all_columns if col not in global_exclude]
            
            # Apply table-specific exclusions
            table_specific_exclude = set(self.config['tables']['table_specific_exclusions'].get(table_name, []))
            safe_columns = [col for col in safe_columns if col not in table_specific_exclude]
            
            # Handle reserved keywords by quoting them
            reserved_keywords = {'offset', 'user', 'union', 'group', 'order'}
            safe_columns = [f'"{col}"' if col.lower() in reserved_keywords else col for col in safe_columns]
            
            return safe_columns
            
        except Exception as e:
            logger.warning(f"Failed to get schema for table {table_name}: {e}")
            return []
    
    def extract_table_data(self, table_name, limit=None):
        """Extract data from a single table"""
        safe_columns = self.get_table_columns(table_name)
        
        if not safe_columns:
            logger.warning(f"No safe columns found for table {table_name}, skipping")
            return pd.DataFrame()
        
        # Build query with proper quoting for table names that are reserved keywords
        table_name_quoted = f'"{table_name}"' if table_name.lower() in {'user', 'union'} else table_name
        columns_str = ", ".join(safe_columns)
        
        # Build WHERE clause - check if is_active and is_deleted columns exist
        where_clause = ""
        column_names = [col.strip('"') for col in safe_columns]
        if 'is_active' in column_names and 'is_deleted' in column_names:
            where_clause = " WHERE is_active = true AND is_deleted = false"
        
        query = f"SELECT {columns_str} FROM {table_name_quoted}{where_clause}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        try:
            results = db_connector.execute_query(query)
            # Remove quotes from column names for the DataFrame
            clean_columns = [col.strip('"') for col in safe_columns]
            df = pd.DataFrame(results, columns=clean_columns)
            logger.info(f"Extracted {len(df)} rows from {table_name}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to extract data from {table_name}: {e}")
            return pd.DataFrame()
    
    def extract_all_tables(self, table_limit=None):
        """Extract data from all allowed tables"""
        allowed_tables = self.get_allowed_tables()
        table_data = {}
        
        for table_name in tqdm(allowed_tables, desc="Extracting tables"):
            df = self.extract_table_data(table_name, table_limit)
            if not df.empty:
                table_data[table_name] = df
        
        logger.info(f"Successfully extracted data from {len(table_data)} tables")
        return table_data

# Factory function
def create_data_extractor(config_path="config/embedding_config.yaml"):
    return DataExtractor(config_path)