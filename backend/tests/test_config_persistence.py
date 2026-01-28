import os
import tempfile
import pytest
import json
from backend.sqliteDb.db import DatabaseService

@pytest.fixture
def test_db_service():
    """Create a temporary database service for testing."""
    # Create temp DB file
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    try:
        service = DatabaseService(path)
        yield service
    finally:
        os.unlink(path)

def test_config_persistence(test_db_service: DatabaseService):
    """Test that embedding and retriever configs are persisted correctly."""
    
    # 1. Publish a prompt with config
    user_id = "test_user_config"
    config = {
        "embedding": {"model": "test-model", "chunkSize": 512, "chunkOverlap": 50},
        "retriever": {"topKInitial": 100, "topKFinal": 5, "hybridWeights": [0.8, 0.2]}
    }
    
    result = test_db_service.publish_system_prompt(
        prompt_text="Test prompt",
        user_id=user_id,
        embedding_config=json.dumps(config['embedding']),
        retriever_config=json.dumps(config['retriever'])
    )
    
    assert result['id'] is not None
    config_id = result['id']
    
    # 2. Retrieve active config
    active_config = test_db_service.get_active_config()
    
    assert active_config is not None
    assert active_config['prompt_id'] == config_id
    assert active_config['embedding_config'] is not None
    assert active_config['retriever_config'] is not None
    
    # 3. Verify content
    saved_emb = json.loads(active_config['embedding_config'])
    assert saved_emb['model'] == "test-model"
    assert saved_emb['chunkSize'] == 512
    
    saved_ret = json.loads(active_config['retriever_config'])
    assert saved_ret['topKInitial'] == 100
    assert saved_ret['hybridWeights'] == [0.8, 0.2]

def test_connection_pool_persistence(test_db_service: DatabaseService):
    """Test that connection pool config is persisted."""
    pool_config = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 60,
        "pool_recycle": 1800
    }
    
    pool_config_str = json.dumps(pool_config)
    
    conn_id = test_db_service.add_db_connection(
        name="Test Pool DB",
        uri="postgresql://user:pass@localhost/db",
        pool_config=pool_config_str
    )
    
    # Retrieve
    conn = test_db_service.get_db_connection_by_id(conn_id)
    assert conn['pool_config'] is not None
    
    saved_pool = json.loads(conn['pool_config'])
    assert saved_pool['pool_size'] == 20
    assert saved_pool['pool_timeout'] == 60
