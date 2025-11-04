
import os
import sys
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.pipeline.extract import create_data_extractor
from src.db.connector import db_connector
from src.pipeline.utils import setup_logging

load_dotenv()

# Load from .env
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise ValueError("NEO4J_PASSWORD not found in .env file. Please set it.")

logger = logging.getLogger(__name__)

def build_knowledge_graph():
    """
    Extracts data from Postgres and builds a Neo4j knowledge graph.
    """
    setup_logging()
    logger.info("Starting knowledge graph build...")
    
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logger.info(f"Successfully connected to Neo4j at {NEO4J_URI}")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j. Is it running? Error: {e}")
        return

    # 1. Connect to Postgres and extract data
    logger.info("Connecting to Postgres to extract data...")
    db_connector.connect()
    extractor = create_data_extractor("config/embedding_config.yaml")
    # We only need a few key tables for the graph
    tables_to_extract = ['account', 'patient_tracker', 'patient_diagnosis']
    table_data = {}
    
    for table in tables_to_extract:
        try:
            safe_cols = extractor.get_safe_columns(table)
            cols_str = ", ".join([f'"{c}"' for c in safe_cols])
            query = f'SELECT {cols_str} FROM public."{table}"'
            results = db_connector.execute_query(query)
            df = pd.DataFrame(results, columns=safe_cols)
            if not df.empty:
                table_data[table] = df
                logger.info(f"Successfully extracted {len(df)} rows from {table}")
        except Exception as e:
            logger.error(f"Failed to extract {table}: {e}")

    db_connector.disconnect()
    logger.info("Disconnected from Postgres.")

    # 2. Load data into Neo4j
    with driver.session(database="neo4j") as session:
        # Create constraints for unique IDs
        logger.info("Creating Neo4j constraints...")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Patient) REQUIRE p.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Diagnosis) REQUIRE d.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE")

        # Example: Load Accounts
        if 'account' in table_data:
            logger.info("Loading Accounts into Neo4j...")
            account_rows = table_data['account'].to_dict('records')
            session.run("""
            UNWIND $rows AS row
            MERGE (a:Account {id: row.id})
            SET a.name = row.name, a.tenant_id = row.tenant_id
            """, rows=account_rows)
            logger.info(f"Loaded {len(account_rows)} Account nodes.")

        # Example: Load Patients and link to Accounts
        if 'patient_tracker' in table_data:
            logger.info("Loading Patients and linking to Accounts...")
            patient_rows = table_data['patient_tracker'].to_dict('records')
            session.run("""
            UNWIND $rows AS row
            MERGE (p:Patient {id: row.id})
            SET p.gender = row.gender, p.age = row.age, p.patient_status = row.patient_status
            
            // Link patient to their account
            MERGE (a:Account {id: row.account_id})
            MERGE (p)-[:BELONGS_TO_ACCOUNT]->(a)
            """, rows=patient_rows)
            logger.info(f"Loaded {len(patient_rows)} Patient nodes and relationships.")

        # Example: Load Diagnoses and link to Patients
        if 'patient_diagnosis' in table_data:
             logger.info("Loading Diagnoses and linking to Patients...")
             diag_rows = table_data['patient_diagnosis'].to_dict('records')
             session.run("""
             UNWIND $rows AS row
             // Find the patient
             MERGE (p:Patient {id: row.patient_track_id})
             
             // Create/Merge diagnosis nodes and link
             FOREACH (diag IN CASE WHEN row.is_diabetes_diagnosis = true THEN ['Diabetes'] ELSE [] END |
                MERGE (d:Diagnosis {name: diag})
                MERGE (p)-[:HAS_DIAGNOSIS]->(d)
             )
             FOREACH (diag IN CASE WHEN row.is_htn_diagnosis = true THEN ['Hypertension'] ELSE [] END |
                MERGE (d:Diagnosis {name: diag})
                MERGE (p)-[:HAS_DIAGNOSIS]->(d)
             )
             """, rows=diag_rows)
             logger.info(f"Processed {len(diag_rows)} diagnosis records.")

    driver.close()
    logger.info("Knowledge graph build complete. Neo4j connection closed.")

if __name__ == "__main__":
    import pandas as pd
    build_knowledge_graph()