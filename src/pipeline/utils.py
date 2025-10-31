import logging
import os
from tqdm import tqdm
import json
from typing import List, Dict, Any
import hashlib

def setup_logging(log_file="logs/pipeline.log"):
    """Setup logging configuration"""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def batch_generator(data: List, batch_size: int):
    """Generate batches from data"""
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]

def calculate_md5(text: str) -> str:
    """Calculate MD5 hash of text"""
    return hashlib.md5(text.encode()).hexdigest()

def save_checkpoint(data: Any, checkpoint_path: str):
    """Save pipeline checkpoint"""
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    
    if isinstance(data, (list, dict)):
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            f.write(str(data))
    
    logging.info(f"Checkpoint saved: {checkpoint_path}")

def load_checkpoint(checkpoint_path: str) -> Any:
    """Load pipeline checkpoint"""
    if not os.path.exists(checkpoint_path):
        return None
    
    with open(checkpoint_path, 'r', encoding='utf-8') as f:
        if checkpoint_path.endswith('.json'):
            return json.load(f)
        else:
            return f.read()

def validate_documents(documents: List[Dict]) -> List[Dict]:
    """Validate and clean documents"""
    valid_documents = []
    
    for doc in documents:
        if not doc.get("content") or len(doc["content"].strip()) < 10:
            continue
        
        if not doc.get("metadata"):
            continue
            
        valid_documents.append(doc)
    
    logging.info(f"Validated documents: {len(valid_documents)}/{len(documents)}")
    return valid_documents

def get_memory_usage():
    """Get current memory usage"""
    import psutil
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024  # MB