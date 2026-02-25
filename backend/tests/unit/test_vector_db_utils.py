from backend.core.vector_db_utils import validate_vector_db_name, derive_vector_db_name

def test_validate_vector_db_name():
    # Valid names
    assert validate_vector_db_name("my_db")[0] is True
    assert validate_vector_db_name("db123")[0] is True
    assert validate_vector_db_name("a_b_c")[0] is True
    
    # Invalid names
    assert validate_vector_db_name("")[0] is False
    assert validate_vector_db_name("ab")[0] is False # too short
    assert validate_vector_db_name("my-db")[0] is False # hyphen not allowed
    assert validate_vector_db_name("my db")[0] is False # space not allowed
    assert validate_vector_db_name("a" * 65)[0] is False # too long

def test_derive_vector_db_name():
    # Source name precedence
    assert derive_vector_db_name(source_name="My Dataset") == "my_dataset_data"
    assert derive_vector_db_name(source_name="Hello-World!!!") == "hello_world_data"
    
    # Agent ID precedence
    assert derive_vector_db_name(agent_id=5) == "agent_5_data"
    
    # Connection ID precedence
    assert derive_vector_db_name(connection_id=10) == "db_connection_10_data"
    
    # Default
    assert derive_vector_db_name() == "default_vector_db"
    
    # Complex source name
    assert derive_vector_db_name(source_name="  ___Multiple   Spaces--And--Hyphens___") == "multiple_spaces_and_hyphens_data"
