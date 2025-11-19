# FHIR RAG Chatbot: Data Insights AI-Copilot

This project is an advanced Retrieval-Augmented Generation (RAG) system designed to provide insights from a healthcare database (PostgreSQL). It combines a powerful language model with multiple data retrieval tools to answer natural language questions about patient data, diagnoses, and more.

The system is exposed through an interactive Gradio web interface that includes features for querying, visualization, feedback, and embedding analysis.

##  Key Features

*   **Hybrid Agent Approach**: Utilizes a primary agent that delegates tasks to specialized tools:
    *   **SQL Agent**: Translates natural language to SQL queries for structured data retrieval (e.g., counting patients, aggregating stats).
    *   **Advanced RAG Retriever**: Performs semantic search over unstructured data using a sophisticated "Small-to-Big" chunking strategy, hybrid search (BM25 + Dense), and a final reranking step.
*   **Interactive Web UI**: A Gradio application that provides:
    *   User authentication (Login/Logout).
    *   A chatbot interface for asking questions.
    *   Automatic chart generation (e.g., pie charts, bar charts) based on the query context.
    *   Proactive "suggested next questions" to guide user exploration.
    *   An "Embedding Explorer" to visualize and understand how the semantic search works.
*   **Advanced RAG Pipeline**:
    *   **Data Extraction**: Pulls data from a PostgreSQL database, respecting specified table/column exclusions.
    *   **Parent-Child Chunking**: Implements a "Small-to-Big" strategy where documents are split into large parent chunks (for context) and smaller child chunks (for embedding).
    *   **Hybrid Indexing**: Creates a BM25 sparse index (for keyword search) and a ChromaDB vector index (for semantic search).
*   **Observability & Feedback**:
    *   Integrates with **Langfuse** for tracing and debugging agent interactions.
    *   Logs user feedback on suggested questions to a CSV file, capturing which suggestions are useful.

## 📂 Project Structure

```
fhir_rag/
├── app.py                  # Deprecated Gradio app, main logic is now in main.py
├── config/
│   ├── db_config.yaml      # Database connection settings
│   └── embedding_config.yaml # RAG pipeline, models, and chunking config
├── data/
│   └── indexes/            # Stores the generated ChromaDB vector index
├── main.py                 # Entry point for the main Gradio application
├── models/                 # Directory to store local embedding and reranker models
├── notebooks/              # Jupyter notebooks for exploration and testing
├── requirements.txt        # Python dependencies
├── src/
│   ├── db/                 # Database connector
│   ├── main.py             # Entry point for the data indexing pipeline
│   ├── pipeline/           # Modules for Extract, Transform, Load (ETL) and Indexing
│   │   ├── build_index.py
│   │   ├── embed.py
│   │   ├── extract.py
│   │   ├── transform.py
│   │   └── utils.py
│   └── rag/
│       └── retrieve.py     # Core logic for the AdvancedRAGRetriever
└── .env                    # For storing secrets like API keys and DB URLs
```

##  Setup and Installation

### 1. Prerequisites

*   Python 3.10+
*   PostgreSQL database server running.
*   An OpenAI API key.

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd fhir_rag
```

### 3. Set Up Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Download Embedding Models

The system uses `BAAI/bge-m3` for embeddings and `BAAI/bge-reranker-base` for reranking. You need to download these and place them in the `models` directory.

```bash
# Create the models directory
mkdir -p models

# You can use git to clone the models
git clone https://huggingface.co/BAAI/bge-m3 models/bge-m3
git clone https://huggingface.co/BAAI/bge-reranker-base models/bge-reranker-base
```

### 6. Configure Environment Variables

Create a `.env` file in the project root and add your credentials.

```env
# .env

# OpenAI API Key
OPENAI_API_KEY="sk-..."

# PostgreSQL Connection URL
# Format: postgresql://<user>:<password>@<host>:<port>/<database_name>
DATABASE_URL="postgresql://admin:admin@localhost:5432/Spice_BD"

# Langfuse Observability (Optional)
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_HOST="https://cloud.langfuse.com"
```

### 7. Set Up the Database

Ensure your PostgreSQL server is running. Create the `Spice_BD` database and populate it with your schema and data. The application expects the tables defined in the pipeline (e.g., `patient_tracker`, `patient_diagnosis`, etc.).

##  Running the System

### Step 1: Build the RAG Index

First, you must run the data pipeline to extract data from the database, transform it, and build the ChromaDB vector index.

```bash
# Run the full pipeline
python src/main.py

# For a quick test, process only 100 rows per table
python src/main.py --limit 100
```

This process will create the index in the `./data/indexes/chroma_db_advanced` directory as specified in `config/embedding_config.yaml`.

### Step 2: Launch the Web Application

Once the index is built, you can start the Gradio web interface.

```bash
python main.py
```

Navigate to the local URL provided in the terminal (usually `http://127.0.0.1:7860`) to access the application. The default login credentials are `admin`/`admin`.