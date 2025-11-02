import logging
import yaml
import os
import sys
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.connector import db_connector
from src.pipeline.extract import create_data_extractor
from src.pipeline.transform import AdvancedDataTransformer
from src.pipeline.embed import LocalHuggingFaceEmbeddings
from src.pipeline.build_index import build_advanced_chroma_index
from src.pipeline.utils import setup_logging

def build_advanced_pipeline(limit: int = None):
    """Builds the complete advanced RAG pipeline."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Load Config
        with open("config/embedding_config.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # 2. Connect to DB and Extract
        logger.info("Connecting to database and extracting data...")
        db_connector.connect()
        extractor = create_data_extractor("config/embedding_config.yaml")
        table_data = extractor.extract_all_tables(table_limit=limit)

        # 3. Transform (Create Parent Docs and Child Chunks)
        logger.info("Transforming data with parent-child chunking...")
        transformer = AdvancedDataTransformer(config) # Use the correct class
        initial_documents = transformer.create_documents_from_tables(table_data)
        
        if not initial_documents:
            logger.error("No documents were created after transformation. Stopping.")
            return

        child_documents, parent_docstore = transformer.perform_parent_child_chunking(initial_documents)
        
        # 4. Initialize Embedding Model
        embedding_function = LocalHuggingFaceEmbeddings(model_id=config['embedding']['model_path'])

        # 5. Build and Save Index
        logger.info("Building and persisting advanced ChromaDB index and docstore...")
        build_advanced_chroma_index(
            child_docs=child_documents,
            docstore=parent_docstore,
            embedding_function=embedding_function,
            config=config
        )

        logger.info("✅ Advanced pipeline built successfully!")
    except Exception as e:
        logger.critical(f"Pipeline build failed: {e}", exc_info=True)
    finally:
        db_connector.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Advanced RAG Pipeline Builder")
    parser.add_argument(
        "--limit", 
        type=int, 
        default=None, 
        help="Limit the number of rows processed per table for a quick test run."
    )
    args = parser.parse_args()

    if args.limit:
        print(f"--- Running in test mode: Processing a maximum of {args.limit} rows per table. ---")
    
    build_advanced_pipeline(limit=args.limit)