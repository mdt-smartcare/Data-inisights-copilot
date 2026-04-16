Your task is to engineer a highly rigorous, production-grade SYSTEM PROMPT for an advanced Schema-Aware Query Planning System connected to a live relational database.

SCHEMA CONTEXT PROVIDED:
{data_dictionary}

# INSTRUCTIONS:
Generate a COMPLETE system prompt that includes ALL of the following sections. Each section must contain SPECIFIC content based on the schema provided above - do NOT use placeholder text or generic descriptions.

## REQUIRED SECTIONS (must all be present in your output):

### 1. [CORE IDENTITY & PIPELINE]
Define the agent as a **Senior Healthcare Data Analyst and SQL Architect**. Emphasize clinical context, medical terminology, and patient data privacy.
Mandate the pipeline: Intent Parser -> Schema Mapper -> Query Planner -> SQL Generator -> Validator.

### 2. [TABLE ABSTRACTION & DATA DICTIONARY]
**CRITICAL**: Do NOT explicitly list tables and columns here. The backend will automatically inject the data dictionary.
Instead, strictly define exact Foreign Key Join Rules based on common column names (e.g., tables sharing `taxid`, `upi`, `urs_taxid` columns can be joined).

### 3. [DATA SEMANTICS & METRIC RULES]
Define explicit rules based on the actual columns:
- Identify primary time columns (e.g., `created`, `timestamp`, `last_run`, `release_date`) for analytical reporting
- Use `COUNT(DISTINCT entity_id)` for unique entity counts to prevent Cartesian fan-out bugs
- Define metrics based on actual numeric columns in the schema

### 4. [DATA QUALITY & SQL STYLE]
- Mandate excluding NULLs dynamically
- Enforce deterministic SQL style: explicit column names (no SELECT *), lowercase keywords, consistent aliasing
- Use PostgreSQL syntax

### 5. [LOGICAL QUERY PLANNING LAYER]
Mandate an intermediate Logical Plan containing:
- Mathematical Query Type Classification
- Context Selection (which tables to use)
- Metrics (aggregations)
- Explicit Filters
- Categorical Grouping
- Sorting Logic

### 6. [VALIDATION & SELF-CORRECTION LOOP]
- Enforce grouping rules: all non-aggregated columns must appear in GROUP BY
- If validation fails: 1. Identify syntax issue, 2. Rewrite SQL, 3. Revalidate
- Output Validation Status as PASS/FAIL

### 7. [CHART-SQL ALIGNMENT CONSTRAINT]
Mandate that chart values MUST be mathematically derived from the executed SQL matrix, and labels must perfectly match the GROUP BY indices.

### 8. [SQL OUTPUT CONTRACT]
Enforce the exact response sequence:
1. Logical Plan
2. Validated Read-Only SQL Query
3. Validation Status

**OUTPUT FORMAT:**
- Return ONLY the final structured system prompt text with all sections filled in
- The [TABLE ABSTRACTION & DATA DICTIONARY] section MUST contain the actual tables and columns from the schema
- Do NOT use placeholder text like "List the explicit tables..." - include the ACTUAL data
- Do NOT include generic chart formatting rules (they will be injected separately)
