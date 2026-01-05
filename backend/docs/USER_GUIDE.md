# FHIR RAG Chatbot - End-to-End User Guide

> **Complete Step-by-Step Guide for Setting Up and Using the FHIR RAG Chatbot System**
> 
> Last Updated: December 30, 2025

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Prerequisites](#prerequisites)
3. [Initial Setup](#initial-setup)
4. [Backend API Setup](#backend-api-setup)
5. [Gradio UI Setup](#gradio-ui-setup)
6. [Using the System](#using-the-system)
7. [API Reference](#api-reference)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Features](#advanced-features)

---

## 🎯 System Overview

The FHIR RAG Chatbot is a sophisticated healthcare data analysis system that combines:

- **FastAPI Backend**: RESTful API with JWT authentication, RAG pipeline, and SQL querying
- **Gradio Web UI**: Interactive chat interface with visualizations and feedback
- **Hybrid RAG System**: Combines vector search (ChromaDB) and SQL querying for comprehensive answers
- **Advanced Features**: Chart generation, suggested questions, agent reasoning display

### Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Gradio UI     │◄────────│   FastAPI        │◄────────│   PostgreSQL    │
│   (Port 7860)   │         │   Backend        │         │   Database      │
│                 │         │   (Port 8000)    │         │   (Port 5432)   │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                    ▲
                                    │
                            ┌───────┴────────┐
                            │                │
                    ┌───────▼──────┐  ┌─────▼────────┐
                    │   ChromaDB   │  │   OpenAI     │
                    │ Vector Store │  │   GPT-4o     │
                    └──────────────┘  └──────────────┘
```

---

## 🔧 Prerequisites

### Software Requirements

- **Python 3.10+** (recommended: 3.10.19)
- **PostgreSQL 14+** with your FHIR database
- **Conda** (optional but recommended)
- **Git** for cloning repositories
- **OpenAI API Key** (GPT-4o access)

### Hardware Requirements

- **RAM**: Minimum 8GB, recommended 16GB+
- **Storage**: 5GB free space for models and indexes
- **GPU**: Optional (Apple Silicon MPS or CUDA supported)

### Account Requirements

- OpenAI API account with credits
- (Optional) Langfuse account for tracing

---

## 🚀 Initial Setup

### Step 1: Clone the Repository

```bash
cd ~
git clone <your-repository-url> fhir_rag
cd fhir_rag
```

### Step 2: Create Conda Environment

```bash
# Create a new conda environment
conda create -n fhir_rag_env python=3.10 -y

# Activate the environment
conda activate fhir_rag_env
```

### Step 3: Install Core Dependencies

```bash
# Install main requirements
pip install -r requirements.txt

# Install backend-specific dependencies
pip install 'python-jose[cryptography]==3.3.0' 'passlib[bcrypt]==1.7.4' \
    'pytest>=7.0.0,<8.0.0' pytest-asyncio==0.23.4 pytest-cov==4.1.0
```

### Step 4: Download Embedding Models

```bash
# Create models directory
mkdir -p models

# Download BGE-M3 embedding model
git clone https://huggingface.co/BAAI/bge-m3 models/bge-m3

# Download BGE reranker model
git clone https://huggingface.co/BAAI/bge-reranker-base models/bge-reranker-base
```

**Verify models are downloaded:**
```bash
ls -lh models/bge-m3/pytorch_model.bin
# Should show ~2.3GB file
```

### Step 5: Configure Environment Variables

Create a `.env` file in the project root:

```bash
cat > .env << 'EOF'
# OpenAI Configuration
OPENAI_API_KEY="sk-proj-YOUR-API-KEY-HERE"
OPENAI_MODEL="gpt-4o"

# PostgreSQL Database
DB_USER="admin"
DB_PASSWORD="admin"
DB_NAME="Spice_BD"
DB_HOST="localhost"
DB_PORT="5432"
DATABASE_URL="postgresql://admin:admin@localhost:5432/Spice_BD"

# Langfuse Tracing (Optional)
LANGFUSE_PUBLIC_KEY="pk-lf-YOUR-KEY"
LANGFUSE_SECRET_KEY="sk-lf-YOUR-KEY"
LANGFUSE_HOST="https://cloud.langfuse.com"
EOF
```

**⚠️ Important:** Replace the placeholder values with your actual credentials!

### Step 6: Configure Backend Environment

```bash
# Copy and customize backend .env
cat > backend/.env << 'EOF'
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-YOUR-API-KEY-HERE
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0

# Database Configuration
DB_USER=admin
DB_PASSWORD=admin
DB_NAME=Spice_BD
DB_HOST=localhost
DB_PORT=5432
DATABASE_URL=postgresql://admin:admin@localhost:5432/Spice_BD

# Embedding Model Configuration
EMBEDDING_MODEL_PATH=models/bge-m3
EMBEDDING_MODEL_NAME=BAAI/bge-m3
VECTOR_DB_PATH=./data/indexes/chroma_db_advanced

# Security Configuration (Generate a new secret key!)
SECRET_KEY=$(openssl rand -hex 32)
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# API Configuration
API_V1_PREFIX=/api/v1
PROJECT_NAME=FHIR RAG Chatbot API
VERSION=1.0.0
DEBUG=False

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:7860
CORS_ALLOW_CREDENTIALS=True

# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-YOUR-KEY
LANGFUSE_SECRET_KEY=sk-lf-YOUR-KEY
LANGFUSE_HOST=https://cloud.langfuse.com
ENABLE_LANGFUSE=False

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=./logs/backend.log

# RAG Configuration
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7
RAG_RERANK=True
RAG_CONFIG_PATH=./config/embedding_config.yaml
EOF

# Generate a secure SECRET_KEY
SECRET_KEY=$(openssl rand -hex 32)
echo "SECRET_KEY=$SECRET_KEY" >> backend/.env
```

### Step 7: Start PostgreSQL Database

```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5432

# If not running, start it (method depends on installation)
# Homebrew:
brew services start postgresql

# Or direct:
pg_ctl -D /usr/local/var/postgres start

# Verify database exists
psql -U admin -d Spice_BD -c "SELECT version();"
```

### Step 8: Build the RAG Index

**First time setup - Build the vector index:**

```bash
# Full index build (may take 30-60 minutes)
python src/main.py

# OR for testing with limited data (faster, ~5 minutes)
python src/main.py --limit 1000
```

**What this does:**
1. Extracts data from PostgreSQL database
2. Chunks documents using parent-child strategy
3. Generates embeddings using BGE-M3 model
4. Builds ChromaDB vector index
5. Creates BM25 keyword index
6. Saves everything to `./data/indexes/chroma_db_advanced/`

**Verify index was created:**
```bash
ls -lh data/indexes/chroma_db_advanced/
# Should show chroma.sqlite3 (500MB+) and parent_docstore.pkl
```

---

## 🔌 Backend API Setup

### Step 1: Start the FastAPI Backend

Open a new terminal window:

```bash
# Navigate to project directory
cd ~/fhir_rag

# Activate conda environment
conda activate fhir_rag_env

# Start the backend server
/opt/anaconda3/envs/fhir_rag_env/bin/python -m uvicorn backend.app:app \
    --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Application startup complete.
```

### Step 2: Verify Backend Health

In another terminal:

```bash
# Check health endpoint
curl http://localhost:8000/api/v1/health | python -m json.tool
```

**Expected response:**
```json
{
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2025-12-30T14:00:00.000000",
    "services": {
        "database": "connected",
        "vector_store": "loaded",
        "llm": "ready"
    }
}
```

✅ If you see `"status": "healthy"`, the backend is ready!

### Step 3: Test Authentication

```bash
# Login to get JWT token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python -m json.tool
```

**Expected response:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "username": "admin",
    "expires_in": 1800
}
```

### Step 4: Test Chat Endpoint

```bash
# Get token and test chat
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Query the chat endpoint
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"How many patients are in the database?"}' | \
  python -m json.tool | head -40
```

### Step 5: Explore API Documentation

Open in your browser:

- **Swagger UI**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc

You can test all API endpoints interactively in Swagger UI!

---

## 🎨 Gradio UI Setup

### Step 1: Start the Gradio Interface

Open another terminal window:

```bash
# Navigate to project directory
cd ~/fhir_rag

# Activate conda environment
conda activate fhir_rag_env

# Start Gradio UI
python main.py
```

**Expected output:**
```
Initializing agent components...
--- FHIR RAG Chatbot is Ready ---
Running on local URL:  http://127.0.0.1:7860
```

### Step 2: Access the Web Interface

Open your browser and navigate to: **http://127.0.0.1:7860**

You should see the login screen.

### Step 3: Login to the System

**Default credentials:**
- **Username**: `admin`
- **Password**: `admin`

**Other available users:**
- `analyst` / `analyst2024`
- `viewer` / `view123`

Click **Login** to access the main interface.

---

## 💬 Using the System

### Using the Gradio UI

#### 1. Basic Chat

1. **Ask a question** in the text box at the bottom
2. Click **Send** or press **Enter**
3. Watch the agent think (optional: expand "Show Agent's Reasoning")
4. View the response in the chat history

**Example queries:**
```
- "How many patients are in the database?"
- "Show me the distribution of patients by gender"
- "What are the top 5 most common diagnoses?"
- "How many patients have diabetes?"
- "Tell me about patient with ID 12345"
```

#### 2. View Visualizations

When the agent generates charts, they appear in the **Chart Visualization** panel on the right side.

Charts are automatically generated for:
- Counts and comparisons (pie charts)
- Time series data (line charts)
- Rankings (bar charts)

#### 3. Explore Agent Reasoning

Click **"Show Agent's Reasoning"** to see:
- Which tools the agent used
- SQL queries generated
- Vector search results
- Reranking process

#### 4. Use Suggested Questions

After each response, the agent provides 3 suggested follow-up questions.

**To use them:**
1. Click on a suggestion in the table
2. The question appears in the text box
3. Click Send to ask it

**To provide feedback:**
1. Select a suggestion row
2. Click **👍 Mark as Good** or **👎 Mark as Bad**
3. Feedback is logged to `feedback_log.csv`

#### 5. Embedding Explorer (Advanced)

Click the **"Embedding Explorer"** tab to:
- Test semantic search
- Compare different queries
- Visualize embeddings in 3D
- Understand how the RAG system works

### Using the API Directly

#### 1. Get Authentication Token

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

Save the `access_token` from the response.

#### 2. Query the Chat Endpoint

```bash
# Set your token
TOKEN="your-token-here"

# Ask a question
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the average age of patients with hypertension?",
    "include_sources": true,
    "trace_id": "my-custom-trace-id"
  }'
```

#### 3. Submit Feedback

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How many patients have diabetes?",
    "response": "There are 1,234 patients with diabetes...",
    "rating": 1,
    "trace_id": "abc-123"
  }'
```

---

## 📖 API Reference

### Authentication Endpoints

#### `POST /api/v1/auth/login`

Login and receive JWT token.

**Request:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "username": "admin",
  "expires_in": 1800
}
```

### Chat Endpoints

#### `POST /api/v1/chat`

Query the RAG system.

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "query": "How many patients have diabetes?",
  "include_sources": true,
  "trace_id": "optional-trace-id"
}
```

**Response:**
```json
{
  "answer": "There are 1,234 patients diagnosed with diabetes...",
  "sources": [
    {
      "content": "Patient data shows...",
      "metadata": {"table": "patient_diagnosis", "score": 0.95}
    }
  ],
  "sql_query": "SELECT COUNT(*) FROM patient_diagnosis WHERE...",
  "suggested_questions": [
    "What is the age distribution of diabetic patients?",
    "How many have Type 1 vs Type 2 diabetes?",
    "What medications are commonly prescribed?"
  ],
  "chart_data": {
    "type": "pie",
    "title": "Diabetes Distribution",
    "data": {...}
  },
  "trace_id": "abc-123",
  "processing_time": 5.23
}
```

### Health Endpoints

#### `GET /api/v1/health`

Check system health.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-12-30T14:00:00.000000",
  "services": {
    "database": "connected",
    "vector_store": "loaded",
    "llm": "ready"
  }
}
```

### Feedback Endpoints

#### `POST /api/v1/feedback`

Submit user feedback.

**Request:**
```json
{
  "query": "original question",
  "response": "system response",
  "rating": 1,
  "comment": "optional comment",
  "trace_id": "abc-123"
}
```

---

## 🔍 Troubleshooting

### Backend Issues

#### Problem: "Port 8000 already in use"

```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9

# Then restart the server
```

#### Problem: "Database connection refused"

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# If not running, start it
brew services start postgresql  # macOS Homebrew
# or
pg_ctl -D /usr/local/var/postgres start
```

#### Problem: "Vector store error"

```bash
# Verify the index exists
ls -lh data/indexes/chroma_db_advanced/

# If missing, rebuild the index
python src/main.py --limit 1000
```

#### Problem: "Secret key validation error"

```bash
# Generate a new secret key
openssl rand -hex 32

# Add to backend/.env
echo "SECRET_KEY=<your-generated-key>" >> backend/.env
```

### Gradio UI Issues

#### Problem: "Gradio won't start"

```bash
# Check if port 7860 is in use
lsof -ti:7860 | xargs kill -9

# Verify conda environment
conda activate fhir_rag_env
which python
# Should show: /opt/anaconda3/envs/fhir_rag_env/bin/python
```

#### Problem: "Login fails"

Check `main.py` for valid credentials:
```python
class Config:
    USERS = {
        "admin": "admin",
        "analyst": "analyst2024",
        "viewer": "view123"
    }
```

#### Problem: "No charts generated"

- Ensure your query asks for comparative data
- Check agent reasoning to see if chart_json was created
- Try explicit requests: "Show me a chart of..."

### Model Issues

#### Problem: "Embedding model not found"

```bash
# Verify model exists
ls models/bge-m3/pytorch_model.bin

# If missing, re-download
git clone https://huggingface.co/BAAI/bge-m3 models/bge-m3
```

#### Problem: "CUDA/MPS errors"

```bash
# For Apple Silicon (MPS)
export PYTORCH_ENABLE_MPS_FALLBACK=1

# For CPU-only (slower but stable)
export CUDA_VISIBLE_DEVICES=""
```

### Performance Issues

#### Problem: "Queries are very slow"

1. **First query is always slower** (10-20s) due to model loading
2. **Subsequent queries should be faster** (3-5s)
3. **Check embedding model device:**
   ```python
   # In logs, look for:
   # "Use pytorch device: mps"  # Apple Silicon - Good!
   # "Use pytorch device: cpu"  # Slower but works
   ```

4. **Reduce RAG_TOP_K in backend/.env:**
   ```bash
   RAG_TOP_K=3  # Instead of 5
   ```

---

## 🚀 Advanced Features

### 1. Langfuse Tracing

Enable observability to debug and monitor your RAG system:

```bash
# In backend/.env
ENABLE_LANGFUSE=True
LANGFUSE_PUBLIC_KEY=pk-lf-your-key
LANGFUSE_SECRET_KEY=sk-lf-your-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

View traces at: https://cloud.langfuse.com

### 2. Custom User Management

Edit `backend/config.py` to add users:

```python
# Default hardcoded users
DEFAULT_USERS = {
    "admin": "admin",
    "analyst": "analyst2024",
    "viewer": "view123",
    "newuser": "password123"  # Add your user
}
```

### 3. Adjust RAG Parameters

Edit `backend/.env`:

```bash
# Number of documents to retrieve
RAG_TOP_K=5

# Minimum similarity score (0.0 to 1.0)
RAG_SIMILARITY_THRESHOLD=0.7

# Enable/disable reranking
RAG_RERANK=True
```

### 4. Database Table Filtering

Edit `config/embedding_config.yaml` to exclude tables:

```yaml
database:
  excluded_tables:
    - system_logs
    - audit_trail
    - temp_table
```

### 5. Custom Chunking Strategy

Edit `config/embedding_config.yaml`:

```yaml
chunking:
  parent:
    chunk_size: 1500  # Larger for more context
    chunk_overlap: 200
  
  child:
    chunk_size: 400  # Smaller for precise retrieval
    chunk_overlap: 50
```

### 6. API Rate Limiting

In `backend/config.py`:

```python
rate_limit_enabled: bool = Field(default=True)
rate_limit_per_minute: int = Field(default=60)
```

---

## 📊 Monitoring and Logs

### View Backend Logs

```bash
# Real-time logs
tail -f logs/backend.log

# Search for errors
grep ERROR logs/backend.log

# View last 50 lines
tail -50 logs/backend.log
```

### View Feedback Data

```bash
# View all feedback
cat feedback_log.csv

# Count positive feedback
grep ",1$" feedback_log.csv | wc -l

# Recent feedback
tail -20 feedback_log.csv
```

### Monitor Database

```bash
# Connect to database
psql -U admin -d Spice_BD

# Check table sizes
SELECT 
  tablename, 
  pg_size_pretty(pg_total_relation_size(tablename::text)) as size
FROM pg_tables 
WHERE schemaname = 'public';

# Check patient count
SELECT COUNT(*) FROM patient_tracker;
```

---

## 🎓 Usage Examples

### Example 1: Patient Statistics

**Query:** "How many patients do we have in total?"

**System Response:**
```
We have 45,678 patients in the database.

Here's the breakdown by gender:
- Female: 23,456 (51.4%)
- Male: 22,222 (48.6%)

[Automatic pie chart generated]

Suggested questions:
1. What is the age distribution of patients?
2. How many active patients do we have?
3. What are the most common patient conditions?
```

### Example 2: Diagnosis Analysis

**Query:** "What are the top 5 most common diagnoses?"

**System Response:**
```
Here are the top 5 most common diagnoses:

1. Hypertension - 12,345 patients (27.0%)
2. Diabetes Type 2 - 8,901 patients (19.5%)
3. Asthma - 6,543 patients (14.3%)
4. Depression - 5,432 patients (11.9%)
5. Arthritis - 4,321 patients (9.5%)

[Bar chart automatically generated]

SQL Query Used:
SELECT condition, COUNT(*) as count
FROM patient_diagnosis
GROUP BY condition
ORDER BY count DESC
LIMIT 5;
```

### Example 3: Patient-Specific Query

**Query:** "Tell me about patient 12345"

**System Response:**
```
Patient ID: 12345
Name: John Doe
Age: 45 years
Gender: Male

Recent Diagnoses:
- Hypertension (2024-01-15)
- Type 2 Diabetes (2023-11-20)

Recent Notes:
"Patient reports improved blood pressure control with current medication regimen. Blood sugar levels remain elevated despite dietary modifications..."

[Retrieved from vector store using semantic search]
```

---

## 🔒 Security Best Practices

1. **Change default passwords** in production
2. **Use strong SECRET_KEY** (32+ characters)
3. **Enable HTTPS** in production (use nginx/Apache)
4. **Rotate JWT tokens** regularly
5. **Monitor API usage** for abuse
6. **Keep dependencies updated**: `pip list --outdated`
7. **Backup your database** regularly
8. **Don't commit `.env` files** to git

---

## 📝 Quick Reference

### Start Everything (One-line commands)

```bash
# Terminal 1: Backend
cd ~/fhir_rag && conda activate fhir_rag_env && \
/opt/anaconda3/envs/fhir_rag_env/bin/python -m uvicorn backend.app:app \
  --reload --host 0.0.0.0 --port 8000

# Terminal 2: Gradio UI
cd ~/fhir_rag && conda activate fhir_rag_env && python main.py
```

### Stop Everything

```bash
# Kill backend
lsof -ti:8000 | xargs kill -9

# Kill Gradio
lsof -ti:7860 | xargs kill -9
```

### Rebuild Index

```bash
cd ~/fhir_rag
conda activate fhir_rag_env
python src/main.py --limit 1000  # Fast test
python src/main.py                # Full rebuild
```

---

## 📞 Support and Resources

- **API Documentation**: http://localhost:8000/api/v1/docs
- **Gradio UI**: http://localhost:7860
- **Project README**: `/Users/adityanbhatt/fhir_rag/README.md`
- **Backend README**: `/Users/adityanbhatt/fhir_rag/backend/README.md`

### Useful Commands Cheatsheet

```bash
# Check system status
curl http://localhost:8000/api/v1/health | python -m json.tool

# Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Test chat
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"How many patients?"}' | python -m json.tool

# View logs
tail -f logs/backend.log

# Check database
psql -U admin -d Spice_BD -c "SELECT COUNT(*) FROM patient_tracker;"
```

---

## ✅ Final Checklist

Before considering your setup complete, verify:

- [ ] PostgreSQL database is running and accessible
- [ ] Embedding models are downloaded in `models/`
- [ ] RAG index is built in `data/indexes/chroma_db_advanced/`
- [ ] Backend health check returns `"status": "healthy"`
- [ ] You can login via API and receive a JWT token
- [ ] Chat endpoint responds to queries
- [ ] Gradio UI loads and you can login
- [ ] Charts and suggestions appear in responses
- [ ] Feedback logging works

---

**🎉 Congratulations! Your FHIR RAG Chatbot is fully operational!**

You now have a production-ready healthcare AI assistant that can:
- Answer natural language questions about patient data
- Generate visualizations automatically
- Provide intelligent follow-up suggestions
- Trace and debug queries with Langfuse
- Scale to handle multiple users

Happy querying! 🚀
