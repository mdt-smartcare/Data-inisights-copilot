import logging
import pickle
import os
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from langchain_chroma import Chroma
import chromadb
from tqdm import tqdm

logger = logging.getLogger(__name__)

class ProgressTracker:
    """Track and display progress for index building with checkpoints."""
    
    def __init__(self, total_docs: int, checkpoint_file: str = "build_progress.json"):
        self.total_docs = total_docs
        self.checkpoint_file = checkpoint_file
        self.start_time = time.time()
        self.processed_docs = 0
        self.last_checkpoint = 0
        
        # Try to resume from checkpoint
        self.resume_from_checkpoint()
    
    def resume_from_checkpoint(self):
        """Load previous progress if available."""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_docs = data.get('processed_docs', 0)
                    self.last_checkpoint = self.processed_docs
                    logger.info(f"📂 Resuming from checkpoint: {self.processed_docs}/{self.total_docs} docs ({self.get_percentage():.1f}%)")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")
    
    def save_checkpoint(self):
        """Save current progress to disk."""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed_docs': self.processed_docs,
                    'total_docs': self.total_docs,
                    'timestamp': datetime.now().isoformat(),
                    'percentage': self.get_percentage()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save checkpoint: {e}")
    
    def update(self, n: int = 1):
        """Update progress by n documents."""
        self.processed_docs += n
        
        # Save checkpoint every 10,000 documents
        if self.processed_docs - self.last_checkpoint >= 10000:
            self.save_checkpoint()
            self.last_checkpoint = self.processed_docs
    
    def get_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_docs == 0:
            return 0.0
        return (self.processed_docs / self.total_docs) * 100
    
    def get_eta(self) -> str:
        """Get estimated time remaining."""
        if self.processed_docs == 0:
            return "Calculating..."
        
        elapsed = time.time() - self.start_time
        docs_per_second = self.processed_docs / elapsed
        remaining_docs = self.total_docs - self.processed_docs
        
        if docs_per_second > 0:
            remaining_seconds = remaining_docs / docs_per_second
            eta = timedelta(seconds=int(remaining_seconds))
            return str(eta)
        return "Unknown"
    
    def get_speed(self) -> float:
        """Get processing speed in docs/second."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.processed_docs / elapsed
        return 0.0
    
    def print_summary(self):
        """Print final summary."""
        elapsed = time.time() - self.start_time
        elapsed_time = timedelta(seconds=int(elapsed))
        
        print("\n" + "="*80)
        print("📊 INDEX BUILD COMPLETE!")
        print("="*80)
        print(f"✅ Total Documents Processed: {self.processed_docs:,}")
        print(f"⏱️  Total Time Taken: {elapsed_time}")
        print(f"⚡ Average Speed: {self.get_speed():.2f} docs/second")
        print("="*80 + "\n")
        
        # Clean up checkpoint file
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)

def build_advanced_chroma_index(
    child_docs: List[Document],
    docstore: BaseStore,
    embedding_function,
    config: dict
):
    chroma_path = config['vector_store']['chroma_path']
    collection_name = config['vector_store']['collection_name']
    batch_size = config['embedding'].get('batch_size', 128)
    
    total_docs = len(child_docs)
    logger.info(f"Building Chroma index at '{chroma_path}' with {total_docs:,} documents.")
    
    # Create directory
    os.makedirs(chroma_path, exist_ok=True)
    
    # Initialize progress tracker
    progress = ProgressTracker(total_docs, checkpoint_file=f"{chroma_path}/.build_progress.json")
    
    # Check if resuming
    start_idx = progress.processed_docs
    if start_idx > 0:
        logger.info(f"🔄 Resuming from document {start_idx:,}")
        remaining_docs = child_docs[start_idx:]
    else:
        remaining_docs = child_docs
    
    # Disable telemetry
    client_settings = chromadb.Settings(anonymized_telemetry=False)
    
    # Initialize or load existing collection
    client = chromadb.PersistentClient(path=chroma_path, settings=client_settings)
    
    try:
        collection = client.get_collection(name=collection_name)
        logger.info(f"📂 Found existing collection with {collection.count()} documents")
    except:
        collection = None
        logger.info("🆕 Creating new collection")
    
    # Print initial status
    print("\n" + "="*80)
    print(" STARTING INDEX BUILD")
    print("="*80)
    print(f" Output Path: {chroma_path}")
    print(f" Total Documents: {total_docs:,}")
    print(f" Batch Size: {batch_size}")
    print(f" Starting Progress: {progress.get_percentage():.1f}%")
    print("="*80 + "\n")
    
    # Process in batches with progress bar
    num_batches = (len(remaining_docs) + batch_size - 1) // batch_size
    
    with tqdm(total=len(remaining_docs), 
              desc="Building Index",
              initial=0,
              unit="docs",
              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
        
        for i in range(0, len(remaining_docs), batch_size):
            batch = remaining_docs[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            # Add batch to collection
            if collection is None:
                # First batch - create collection
                Chroma.from_documents(
                    documents=batch,
                    embedding=embedding_function,
                    collection_name=collection_name,
                    persist_directory=chroma_path,
                    client_settings=client_settings
                )
                collection = client.get_collection(name=collection_name)
            else:
                # Subsequent batches - add to existing collection
                vector_store = Chroma(
                    client=client,
                    collection_name=collection_name,
                    embedding_function=embedding_function
                )
                vector_store.add_documents(batch)
            
            # Update progress
            progress.update(len(batch))
            pbar.update(len(batch))
            
            # Update progress bar description with stats
            pbar.set_postfix({
                'Progress': f'{progress.get_percentage():.1f}%',
                'ETA': progress.get_eta(),
                'Speed': f'{progress.get_speed():.1f} docs/s'
            })
            
            # Log every 10 batches
            if batch_num % 10 == 0:
                logger.info(
                    f"Batch {batch_num}/{num_batches} | "
                    f"{progress.processed_docs:,}/{total_docs:,} docs | "
                    f"{progress.get_percentage():.1f}% | "
                    f"ETA: {progress.get_eta()}"
                )
    
    # Save docstore
    docstore_path = f"{chroma_path}/parent_docstore.pkl"
    with open(docstore_path, "wb") as f:
        pickle.dump(docstore, f)
    
    logger.info(f"Chroma index built and parent docstore saved to '{docstore_path}'.")
    
    # Print final summary
    progress.print_summary()

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from backend.services.embeddings import get_embedding_model
    from backend.pipeline.utils import load_config
    from backend.pipeline.extract import create_data_extractor
    from backend.pipeline.transform import AdvancedDataTransformer

    # Set up logging
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/pipeline.log'),
            logging.StreamHandler()
        ]
    )

    print("\n" + "="*80)
    print("🔧 FHIR RAG INDEX BUILDER")
    print("="*80)
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    config = load_config("config/embedding_config.yaml")
    
    print(" Step 1/4: Extracting data from database...")
    extractor = create_data_extractor("config/embedding_config.yaml")
    table_data = extractor.extract_all_tables()
    
    print(f"\n Step 2/4: Transforming {len(table_data)} tables into documents...")
    transformer = AdvancedDataTransformer(config)
    documents = transformer.create_documents_from_tables(table_data)
    
    print(f"\n Step 3/4: Applying parent-child chunking...")
    child_docs, docstore = transformer.perform_parent_child_chunking(documents)

    print(f"\n Step 4/4: Building Chroma index with {len(child_docs):,} documents...")
    embedding_function = get_embedding_model()
    
    build_advanced_chroma_index(
        child_docs=child_docs,
        docstore=docstore,
        embedding_function=embedding_function,
        config=config
    )
    
    print("\n" + "="*80)
    print(" INDEX BUILD PROCESS COMPLETED SUCCESSFULLY!")
    print("="*80)
    print(f"Index Location: {config['vector_store']['chroma_path']}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")