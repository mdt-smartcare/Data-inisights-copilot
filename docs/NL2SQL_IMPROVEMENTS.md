# NL2SQL System Improvements

This document describes the fixes implemented to address the identified shortcomings in the NL2SQL system.

## Summary of Changes

| Issue | Solution | Files Modified/Created |
|-------|----------|----------------------|
| Agent's system_prompt not used for SQL generation | Added `set_agent_system_prompt()` method and extract SQL-relevant rules | `sql_service.py` |
| No runtime schema validation | Integrated `QueryValidator` for proactive validation | `query_validator.py`, `sql_service.py` |
| Vector retrieval may miss tables | Added query plan logging to show which tables were selected | `sql_service.py` |
| Cache not auto-invalidated | Created `CacheManager` with file watching | `cache_manager.py` |
| No query plan explanation | Added detailed logging of tables, joins, aggregations | `sql_service.py` |
| Few-shot examples may be stale | Validate examples against current schema before use | `sql_service.py`, `query_validator.py` |
| No feedback loop | Created `FeedbackLoop` service to track failures/corrections | `feedback_loop.py`, `sql_service.py` |
| Expensive retry-based correction | Proactive schema validation BEFORE execution | `query_validator.py`, `sql_service.py` |

---

## New Files Created

### 1. `backend/app/modules/chat/query/query_validator.py`

**Purpose**: Proactive SQL validation against database schema before execution.

**Key Features**:
- Validates table existence
- Validates column existence
- Enforces FHIR identifier patterns (e.g., `patient_gold.res_id` vs `patient_id`)
- Generates query plan explanation for debugging
- Validates few-shot examples against current schema

**Usage**:
```python
from app.modules.chat.query.query_validator import QueryValidator, get_query_validator

validator = get_query_validator(engine=db_engine, fhir_rules=fhir_rules)
result = validator.validate_sql("SELECT * FROM patient_gold WHERE patient_id = 1")

if not result.is_valid:
    print(f"Errors: {result.error_message}")
    print(f"Suggestions: {result.suggested_corrections}")
```

### 2. `backend/app/modules/chat/query/feedback_loop.py`

**Purpose**: Track failed queries and their corrections to improve future SQL generation.

**Key Features**:
- Records failed queries with error messages
- Records successful corrections
- Provides negative examples for prompt injection
- Exports training data from corrections
- Analyzes common error patterns

**Usage**:
```python
from app.modules.chat.query.feedback_loop import get_feedback_loop

feedback = get_feedback_loop(agent_id="uuid")

# Record failure
feedback.record_failure(
    question="How many active patients?",
    failed_sql="SELECT COUNT(*) FROM patient_gold WHERE patient_id IS NOT NULL",
    error_message="column patient_id does not exist"
)

# Get negative examples for prompt
negative_examples = feedback.format_negative_examples_for_prompt(max_examples=2)
```

### 3. `backend/app/core/cache_manager.py`

**Purpose**: Automatic cache invalidation when configuration files change.

**Key Features**:
- File modification time tracking
- Automatic cache refresh callbacks
- Thread-safe operations
- Decorator for cached functions with file watching

**Usage**:
```python
from app.core.cache_manager import get_cache_manager, setup_config_file_watching

# At application startup
setup_config_file_watching()

# In request handlers
from app.core.cache_manager import check_and_refresh_caches
changed = check_and_refresh_caches()
```

---

## Modifications to Existing Files

### `backend/app/modules/chat/sql_service.py`

1. **New Imports**:
   ```python
   from app.modules.chat.query.query_validator import QueryValidator, get_query_validator
   from app.modules.chat.query.feedback_loop import FeedbackLoop, get_feedback_loop
   from app.core.cache_manager import check_and_refresh_caches
   ```

2. **New Instance Variables**:
   - `_query_validator`: For proactive schema validation
   - `_feedback_loop`: For tracking failures and corrections
   - `_agent_system_prompt`: Agent's custom system prompt

3. **New Methods**:
   - `set_agent_system_prompt(prompt)`: Set agent's custom rules for SQL generation
   - `_initialize_query_validator()`: Lazy initialization of query validator
   - `_extract_tables_from_schema_context(schema)`: Extract table names for logging
   - `_extract_sql_relevant_rules(system_prompt)`: Extract SQL rules from agent prompt
   - `_classify_error_type(error_message)`: Categorize errors for feedback

4. **Modified `query_async()` Method**:
   - Added cache refresh check at the beginning
   - Added query plan logging (which tables were selected)
   - Added few-shot example validation against current schema
   - Added negative examples from feedback loop
   - Added agent system prompt inclusion in SQL generation prompt
   - Added proactive schema validation before execution
   - Added feedback loop recording for failures and corrections

---

## How to Use the Agent's System Prompt

To ensure the agent's FHIR rules and domain-specific instructions are used in SQL generation:

```python
# When creating the SQLService
sql_service = SQLService(
    db_url=db_url,
    agent_id=agent_id
)

# Set the agent's system prompt
sql_service.set_agent_system_prompt(agent_config.system_prompt)

# Now SQL generation will include relevant rules from the system prompt
result = await sql_service.query_async(question, llm_helper=llm_helper)
```

---

## Query Plan Logging

Query execution now logs detailed information about the query plan:

```
INFO: Query plan: tables selected for schema context
      tables=['patient_tracker_gold', 'bp_log_gold']
      question="How many patients have high blood pressure?"

INFO: Query plan explanation
      tables=['patient_tracker_gold', 'bp_log_gold']
      join_pattern='inner_join'
      aggregations=['count', 'group_by']
      filters=['bp_log_gold.systolic > 140']
```

---

## Feedback Loop Data Storage

Feedback data is stored in JSON files:

```
backend/data/feedback/
├── global_failures.json      # Global failure records
├── global_corrections.json   # Global correction records
├── {agent_id}_failures.json  # Per-agent failures
└── {agent_id}_corrections.json  # Per-agent corrections
```

---

## Testing the Changes

### 1. Test Proactive Schema Validation

```python
from app.modules.chat.query.query_validator import QueryValidator

validator = QueryValidator(engine=engine)
validator.load_schema()

# Test invalid table
result = validator.validate_sql("SELECT * FROM non_existent_table")
assert not result.is_valid
assert "non_existent_table" in result.invalid_tables

# Test FHIR violation
result = validator.validate_sql("SELECT COUNT(*) FROM patient_gold WHERE patient_id = 1")
assert result.fhir_violations  # Should warn about patient_id on patient_gold
```

### 2. Test Feedback Loop

```python
from app.modules.chat.query.feedback_loop import FeedbackLoop

feedback = FeedbackLoop(agent_id="test")

# Record failure
feedback.record_failure(
    question="Count patients",
    failed_sql="SELECT COUNT(*) FROM patient_gold WHERE patient_id IS NOT NULL",
    error_message="column patient_id does not exist"
)

# Get negative examples
examples = feedback.get_negative_examples()
assert len(examples) > 0
```

### 3. Test Cache Invalidation

```python
from app.core.cache_manager import get_cache_manager

cache_mgr = get_cache_manager()
cache_mgr.register_file("/path/to/config.yaml")

# Modify the file, then check
assert cache_mgr.should_refresh("/path/to/config.yaml")
```

---

## Configuration

### Enable/Disable Features

In `settings.py` or environment:

```python
# Enable query relevance checking (default: True)
ENABLE_QUERY_RELEVANCE_CHECK = True

# Enable few-shot learning (default: True)
ENABLE_FEW_SHOT = True
```

### FHIR Identifier Rules

Configure in the agent's data dictionary:

```yaml
fhir_identifier_rules:
  patient_count_tables:
    patient_gold:
      identifier: res_id
      description: "FHIR Patient resource - use res_id for patient counts"
    patient_tracker_gold:
      identifier: patient_id
      description: "Operational tracking - use patient_id for counts"
  clinical_tables_with_patient_id:
    - bp_log_gold
    - glucose_log_gold
    - appointment_gold
```

---

## Migration Notes

1. **No database migrations required** - All new functionality uses file-based storage or in-memory caches.

2. **Backward compatible** - Existing code continues to work without changes.

3. **Gradual adoption** - Features can be enabled/disabled independently.

---

## Future Improvements

1. **Active Learning**: Use feedback loop data to fine-tune SQL generation model.

2. **Schema Change Detection**: Automatically detect when database schema changes and invalidate caches.

3. **Query Performance Tracking**: Track query execution times and optimize slow queries.

4. **A/B Testing**: Compare SQL generation quality with and without improvements.
