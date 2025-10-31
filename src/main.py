#!/usr/bin/env python3
import argparse
import logging
import sys
import os

# Fix import paths
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from src.pipeline.utils import setup_logging
    from src.db.connector import db_connector
    from src.pipeline.extract import create_data_extractor
    from src.pipeline.transform import create_data_transformer
    from src.pipeline.embed import create_embedding_model
    from src.pipeline.build_index import create_index_builder
    from src.rag.query_interface import create_query_interface
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

def build_pipeline(config_path: str = "config/embedding_config.yaml", table_limit: int = None):
    """Build the complete RAG pipeline"""
    logger = logging.getLogger(__name__)
    
    try:
        # Step 1: Connect to database
        logger.info("Step 1: Connecting to database...")
        if not db_connector.connect():
            raise Exception("Failed to connect to database")
        
        # Step 2: Extract data
        logger.info("Step 2: Extracting data from database...")
        extractor = create_data_extractor(config_path)
        table_data = extractor.extract_all_tables(table_limit)
        
        if not table_data:
            raise Exception("No data extracted from database")
        
        # Step 3: Transform data
        logger.info("Step 3: Transforming data...")
        transformer = create_data_transformer()
        documents = transformer.transform_all_tables(table_data)
        
        if not documents:
            raise Exception("No documents created from data")
        
        # Step 4: Create embeddings
        logger.info("Step 4: Creating embeddings...")
        embedding_model = create_embedding_model(config_path)
        embeddings, metadata = embedding_model.encode_documents(documents)
        
        # Step 5: Build index
        logger.info("Step 5: Building vector index...")
        index_builder = create_index_builder(config_path)
        index_builder.build_complete_index(embeddings, metadata)
        
        logger.info("Pipeline completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_connector.disconnect()

def query_mode(config_path: str = "config/embedding_config.yaml"):
    """Run in query mode"""
    logger = logging.getLogger(__name__)
    
    try:
        query_interface = create_query_interface(config_path)
        
        print("RAG System Ready! Type 'quit' to exit.")
        print("=" * 50)
        
        while True:
            question = input("\nEnter your question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                break
            
            if not question:
                continue
            
            print(f"\nSearching for: {question}")
            results = query_interface.query(question, k=5)
            
            if results.get("error"):
                print(f"Error: {results['error']}")
            else:
                print(f"\nFound {results['total_results']} results:")
                print(results['summary'])
                
                for i, result in enumerate(results['results'], 1):
                    print(f"\n--- Result {i} (Score: {result['score']:.3f}) ---")
                    print(f"Table: {result['metadata']['table_name']}")
                    print(f"Content: {result['content'][:300]}...")
    
    except Exception as e:
        logger.error(f"Query mode failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Healthcare FHIR RAG System")
    parser.add_argument("--mode", choices=["build", "query", "both"], default="both",
                       help="Operation mode: build index, query, or both")
    parser.add_argument("--config", default="config/embedding_config.yaml",
                       help="Path to configuration file")
    parser.add_argument("--table-limit", type=int, 
                       help="Limit number of rows per table to process")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    if args.mode in ["build", "both"]:
        print("Starting pipeline build...")
        success = build_pipeline(args.config, args.table_limit)
        if not success:
            print("Pipeline build failed!")
            sys.exit(1)
        else:
            print("Pipeline build completed successfully!")
    
    if args.mode in ["query", "both"]:
        query_mode(args.config)

if __name__ == "__main__":
    main()