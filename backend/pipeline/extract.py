import pandas as pd
import yaml
from tqdm import tqdm
import logging
from backend.db.connector import db_connector

logger = logging.getLogger(__name__)

class DataExtractor:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.config = self._load_config(config_path)
        self.excluded_tables = set(self.config['tables'].get('exclude_tables', []))
    
    def _load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def get_allowed_tables(self):
        all_tables = db_connector.get_all_tables()
        allowed_tables = [table for table in all_tables if table not in self.excluded_tables]
        logger.info(f"Found {len(allowed_tables)} tables to process.")
        return allowed_tables
    
    def get_safe_columns(self, table_name):
        schema = db_connector.execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table",
            {"table": table_name}
        )
        all_columns = [col[0] for col in schema]
        global_exclude = set(self.config['tables'].get('global_exclude_columns', []))
        safe_columns = [col for col in all_columns if col not in global_exclude]
        return safe_columns
    
    def extract_all_tables(self, table_limit=None):
        allowed_tables = self.get_allowed_tables()
        table_data = {}
        
        for table_name in tqdm(allowed_tables, desc="Extracting tables"):
            safe_columns = self.get_safe_columns(table_name)
            if not safe_columns:
                logger.warning(f"No safe columns for table {table_name}, skipping.")
                continue
            
            cols_str = ", ".join([f'"{c}"' for c in safe_columns])
            query = f'SELECT {cols_str} FROM public."{table_name}"'
            if table_limit:
                query += f" LIMIT {table_limit}"
                
            try:
                results = db_connector.execute_query(query)
                df = pd.DataFrame(results, columns=safe_columns)
                if not df.empty:
                    table_data[table_name] = df
            except Exception as e:
                logger.error(f"Failed to extract {table_name}: {e}")
                
        logger.info(f"Successfully extracted data from {len(table_data)} tables")
        return table_data

def create_data_extractor(config_path="config/embedding_config.yaml"):
    return DataExtractor(config_path)