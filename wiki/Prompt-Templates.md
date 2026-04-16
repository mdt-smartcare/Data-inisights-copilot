# Prompt Templates Documentation

This document explains the prompt template system used in the Data Insights Copilot backend. All LLM prompts are externalized to markdown files for easier maintenance, version control, and editing without code changes.

## Overview

All prompt templates are stored in `/agent_spec/prompt_templates/` and loaded at runtime by the centralized prompt loader (`app/core/prompts.py`). This approach provides:

- **Centralized management** - All prompts in one directory
- **Easy editing** - Non-developers can modify prompts without touching code
- **Version control friendly** - Prompt changes are clearly visible in git diffs
- **Cached loading** - LRU cache prevents repeated file reads
- **Graceful fallbacks** - System won't crash if a template is missing

---

## Prompt Template Files

| Template File | Description |
|---------------|-------------|
| `intent_router.md` | Classifies user queries into SQL-only, Vector-only, or Hybrid intents |
| `sql_generator.md` | Generates PostgreSQL queries from natural language |
| `query_planner.md` | Decomposes questions into structured query plans |
| `reflection_critique.md` | Validates and critiques generated SQL for security |
| `followup_generator.md` | Generates contextual follow-up questions |
| `chart_generator.md` | Rules for generating chart visualizations from data |
| `data_analyst.md` | Synthesizes natural language explanations of results |
| `rag_synthesis.md` | Synthesizes answers from RAG/vector search context |
| `query_rewriter.md` | Rewrites queries to resolve pronouns from conversation history |
| `base_system.md` | Base system prompt for healthcare AI assistant |

---

## Template to Code Mapping

### Intent Classification
| Template | Python File | Function |
|----------|-------------|----------|
| `intent_router.md` | `app/modules/chat/intent_classifier.py` | `IntentClassifier._llm_classify()` |

**Purpose:** Routes user queries to the appropriate handler:
- **Intent A (SQL-only):** Counting, aggregating, filtering structured data
- **Intent B (Vector-only):** Semantic search in clinical notes/documents
- **Intent C (Hybrid):** SQL filter + vector search combined

---

### SQL Generation Pipeline
| Template | Python File | Function |
|----------|-------------|----------|
| `query_planner.md` | `app/modules/chat/query/query_planner.py` | `QueryPlanner.plan()` |
| `sql_generator.md` | `app/modules/chat/sql_service.py` | `SQLService.query()` |
| `reflection_critique.md` | `app/modules/chat/query/reflection_service.py` | `ReflectionService.critique()` |

**Purpose:** Two-stage SQL generation with validation:
1. **Query Planner** - Decomposes question into entities, metrics, filters
2. **SQL Generator** - Generates actual SQL from the plan
3. **Reflection/Critique** - Validates SQL for correctness and security

---

### Response Synthesis
| Template | Python File | Function |
|----------|-------------|----------|
| `data_analyst.md` | `app/modules/chat/service.py` | `ChatService._synthesize_sql_response()` |
| `rag_synthesis.md` | `app/modules/chat/service.py` | `ChatService._synthesize_rag_response()` |
| `chart_generator.md` | `app/modules/chat/service.py` | `ChatService._synthesize_sql_response_with_chart()` |

**Purpose:** Transforms raw data into user-friendly responses:
- **Data Analyst** - Explains SQL query results in natural language
- **RAG Synthesis** - Synthesizes answers from retrieved documents
- **Chart Generator** - Creates visualization JSON for frontend rendering

---

### Conversation Features
| Template | Python File | Function |
|----------|-------------|----------|
| `followup_generator.md` | `app/modules/chat/followup.py` | `FollowupService.generate_followups()` |
| `query_rewriter.md` | `app/modules/chat/memory.py` | `rewrite_query_with_context()` |

**Purpose:** Enhances conversation experience:
- **Follow-up Generator** - Suggests relevant next questions
- **Query Rewriter** - Resolves pronouns using chat history (e.g., "What's their age?" → "What's the age of patient 12345?")

---

### Base Configuration
| Template | Python File | Function |
|----------|-------------|----------|
| `base_system.md` | `app/core/config/defaults.py` | Default system prompt |

**Purpose:** Provides the foundational AI assistant persona for healthcare data analysis.

---

## Query Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER QUERY                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  query_rewriter.md                                                           │
│  ─────────────────                                                           │
│  Resolves pronouns and references using conversation history                 │
│  "What's their age?" → "What's the age of patient 12345?"                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  intent_router.md                                                            │
│  ────────────────                                                            │
│  Classifies query into:                                                      │
│  • Intent A (SQL-only): "How many patients are over 60?"                    │
│  • Intent B (Vector-only): "Find patients with chest pain symptoms"         │
│  • Intent C (Hybrid): "Male patients over 50 with diabetes in their notes"  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │  Intent A   │          │  Intent B   │          │  Intent C   │
   │  SQL Only   │          │ Vector Only │          │   Hybrid    │
   └─────────────┘          └─────────────┘          └─────────────┘
          │                         │                         │
          ▼                         │                         │
┌───────────────────┐               │                         │
│ query_planner.md  │               │                         │
│ ────────────────  │               │                         │
│ Extracts:         │               │                         │
│ • Tables needed   │               │                         │
│ • Metrics (COUNT) │               │                         │
│ • Filters (WHERE) │               │                         │
│ • Grouping        │               │                         │
└───────────────────┘               │                         │
          │                         │                         │
          ▼                         │                         │
┌───────────────────┐               │                         │
│ sql_generator.md  │               │               ┌─────────┴─────────┐
│ ────────────────  │               │               │  SQL Filter for   │
│ Generates SQL     │               │               │  patient IDs      │
│ from query plan   │               │               └─────────┬─────────┘
└───────────────────┘               │                         │
          │                         │                         │
          ▼                         │                         ▼
┌─────────────────────┐             │               ┌───────────────────┐
│reflection_critique.md│            │               │   Vector Search   │
│ ────────────────────│             │               │   with ID Filter  │
│ Validates SQL for:  │             │               └─────────┬─────────┘
│ • Correctness       │             │                         │
│ • Security          │             ▼                         ▼
│ • Performance       │    ┌─────────────────┐      ┌─────────────────┐
└─────────────────────┘    │  Vector Search  │      │rag_synthesis.md │
          │                │  (Semantic)     │      └─────────────────┘
          ▼                └────────┬────────┘                │
┌───────────────────┐               │                         │
│ data_analyst.md   │               ▼                         │
│ ────────────────  │      ┌─────────────────┐                │
│ Explains results  │      │rag_synthesis.md │                │
│ in natural language│     │ ───────────────  │                │
└───────────────────┘      │ Synthesizes     │                │
          │                │ answer from docs │                │
          │                └────────┬────────┘                │
          ▼                         │                         │
┌───────────────────┐               │                         │
│chart_generator.md │               │                         │
│ ────────────────  │               │                         │
│ Creates chart JSON│               │                         │
│ (bar, pie, gauge) │               │                         │
└───────────────────┘               │                         │
          │                         │                         │
          └─────────────────────────┴─────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  followup_generator.md                                                       │
│  ─────────────────────                                                       │
│  Generates 2-3 relevant follow-up questions based on the response           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RESPONSE                                        │
│  • Answer text                                                               │
│  • Chart visualization (if applicable)                                      │
│  • Follow-up questions                                                       │
│  • Source references                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Using the Prompt Loader

### Loading Prompts in Code

```python
from app.core.prompts import load_prompt, get_sql_generator_prompt

# Method 1: Using convenience functions (recommended)
prompt = get_sql_generator_prompt()

# Method 2: Using generic loader
prompt = load_prompt("sql_generator")  # .md extension is optional

# Method 3: With fallback
prompt = load_prompt("custom_prompt", fallback="Default prompt text")
```

### Available Convenience Functions

```python
from app.core.prompts import (
    get_intent_router_prompt,      # → intent_router.md
    get_sql_generator_prompt,      # → sql_generator.md
    get_query_planner_prompt,      # → query_planner.md
    get_reflection_critique_prompt, # → reflection_critique.md
    get_followup_generator_prompt, # → followup_generator.md
    get_chart_generator_prompt,    # → chart_generator.md
    get_data_analyst_prompt,       # → data_analyst.md
    get_rag_synthesis_prompt,      # → rag_synthesis.md
    get_query_rewriter_prompt,     # → query_rewriter.md
    get_base_system_prompt,        # → base_system.md
)
```

### Clearing the Cache

```python
from app.core.prompts import clear_prompt_cache

# Clear all cached prompts (useful for hot-reloading during development)
clear_prompt_cache()
```

---

## Adding a New Prompt Template

### Step 1: Create the Markdown File

Create a new file in `/agent_spec/prompt_templates/`:

```markdown
# My New Prompt

You are a helpful assistant that does X.

## Guidelines

1. Rule one
2. Rule two

## Output Format

Describe expected output format here.
```

### Step 2: Add Convenience Function (Optional)

Add to `/backend-modmono/app/core/prompts.py`:

```python
def get_my_new_prompt() -> str:
    """Get the my new prompt."""
    return load_prompt("my_new_prompt", fallback="Default fallback text")
```

### Step 3: Use in Code

```python
from app.core.prompts import get_my_new_prompt

prompt = get_my_new_prompt()
```

---

## Best Practices

### Writing Prompts

1. **Be specific** - Clearly define the task and expected output
2. **Include examples** - Show input/output examples when helpful
3. **Set constraints** - Define what the LLM should NOT do
4. **Structure with headers** - Use markdown headers for readability

### Maintaining Prompts

1. **Version control** - All prompt changes should go through PR review
2. **Test changes** - Run evaluation suite after prompt modifications
3. **Document reasoning** - Add comments explaining non-obvious prompt decisions
4. **Keep fallbacks** - Always provide sensible fallback text

---

## File Locations

```
/agent_spec/prompt_templates/     # Prompt markdown files
    ├── intent_router.md
    ├── sql_generator.md
    ├── query_planner.md
    ├── reflection_critique.md
    ├── followup_generator.md
    ├── chart_generator.md
    ├── data_analyst.md
    ├── rag_synthesis.md
    ├── query_rewriter.md
    └── base_system.md

/backend-modmono/app/core/prompts.py   # Centralized prompt loader
```
