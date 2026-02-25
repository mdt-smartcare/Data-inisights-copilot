# Guide: Deploying MIMIC-III Demo on Docker PostgreSQL

This guide outlines the process for loading the MIMIC-III clinical database demo into a PostgreSQL Docker container.

### Prerequisites

*   **Docker Container:** Running instance (e.g., `fhir_rag_postgres`).
*   **Credentials:** Database superuser (e.g., `admin`).
*   **Assets:**
    *   `mimic-iii-clinical-database-demo-1.4.zip` (PhysioNet).
    *   SQL Scripts: `postgres_create_tables.sql`, `postgres_load_data.sql`, `postgres_add_indexes.sql` (MIT-LCP GitHub).

---

### Step 1: Extract Source Data

Extract the CSV files from the demo zip archive on your host machine.

```bash
unzip mimic-iii-clinical-database-demo-1.4.zip
# This creates the directory: mimic-iii-clinical-database-demo-1.4/
```

### Step 2: Transfer Assets to Container

Create a staging directory within the container and copy the SQL scripts and CSV data.

```bash
# Create staging directory
docker exec -it fhir_rag_postgres mkdir -p /tmp/mimic_data

# Copy SQL scripts
docker cp postgres_create_tables.sql fhir_rag_postgres:/tmp/mimic_data/
docker cp postgres_load_data.sql fhir_rag_postgres:/tmp/mimic_data/
docker cp postgres_add_indexes.sql fhir_rag_postgres:/tmp/mimic_data/

# Copy CSV contents
docker cp mimic-iii-clinical-database-demo-1.4/. fhir_rag_postgres:/tmp/mimic_data/
```

### Step 3: Initialize Database and Schema

Create the target database and the `mimiciii` schema.

```bash
docker exec -it fhir_rag_postgres psql -U admin -d postgres -c "CREATE DATABASE mimic;"
docker exec -it fhir_rag_postgres psql -U admin -d mimic -c "CREATE SCHEMA mimiciii;"
```

### Step 4: Execute DDL and Data Load

Run the scripts in sequence. Ensure the `search_path` is set to the `mimiciii` schema for all operations.

```bash
# 1. Create Tables
docker exec -it fhir_rag_postgres psql -U admin -d mimic \
  -c "SET search_path TO mimiciii;" \
  -f /tmp/mimic_data/postgres_create_tables.sql

# 2. Load Data (ETL)
docker exec -it fhir_rag_postgres psql -U admin -d mimic \
  -c "SET search_path TO mimiciii;" \
  -v mimic_data_dir='/tmp/mimic_data' \
  -f /tmp/mimic_data/postgres_load_data.sql

# 3. Create Indexes
docker exec -it fhir_rag_postgres psql -U admin -d mimic \
  -c "SET search_path TO mimiciii;" \
  -f /tmp/mimic_data/postgres_add_indexes.sql
```

### Step 5: Verification

Validate the installation by checking table counts and sample data.

```sql
-- Connect to the mimic database
\c mimic

-- Set schema scope
SET search_path TO mimiciii;

-- Verify table count (Expected: 26)
\dt

-- Verify patient count (Expected: 100)
SELECT count(*) FROM patients;

-- Sample Join Query
SELECT p.subject_id, a.diagnosis 
FROM patients p 
JOIN admissions a ON p.subject_id = a.subject_id 
LIMIT 5;
```

### Troubleshooting: Missing Relations

If `\dt` returns no results, the tables may have been created in the `public` schema. Verify by running:

```sql
SET search_path TO public;
\dt
```
