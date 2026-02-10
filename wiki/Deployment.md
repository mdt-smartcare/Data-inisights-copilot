# Deployment & Setup Guide

This guide covers how to deploy the Data Insights Copilot using Docker.

## Prerequisites

- **Docker** and **Docker Compose** installed.
- **OpenAI API Key**.

## Quick Start (Docker Compose)

The easiest way to run the full stack is using Docker Compose.

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/mdt-smartcare/Data-inisights-copilot.git
    cd Data-inisights-copilot
    ```

2.  **Environment Setup**:
    Create a `.env` file in the root directory (or ensure relevant variables are exported in your shell).
    ```bash
    export OPENAI_API_KEY=sk-your-key-here
    ```

3.  **Run with Docker Compose**:
    ```bash
    docker-compose up --build -d
    ```

    This will start:
    - **Frontend**: http://localhost:3000
    - **Backend API**: http://localhost:8000
    - **PostgreSQL**: Port 5432

    **Default Login**:
    - **Username**: `admin`
    - **Password**: `admin123`

## Manual Installation (Development)

### Backend

1.  Navigate to `backend/`.
2.  Create virtual environment: `python -m venv venv && source venv/bin/activate`.
3.  Install deps: `pip install -r requirements.txt`.
4.  Run: `./run_dev.sh`.

### Frontend

1.  Navigate to `frontend/`.
2.  **Environment Setup**:
    ```bash
    cp .env.example .env
    ```
3.  Install deps: `npm install`.
4.  Run: `npm run dev`.

## Production Considerations

- **Security**:
    - Change `SECRET_KEY` in `docker-compose.yml` or `.env`.
    - Change default database passwords (`POSTGRES_PASSWORD`).
    - Use HTTPS (e.g., via Nginx reverse proxy).

- **Data Persistence**:
    - Postgres data is persisted in the `postgres_data` volume.
    - Vector store data (ChromaDB) is persisted in `./backend/data`.

## Configuration
See **[Backend Documentation](Backend.md#2-getting-started)** for detailed environment variable setup.

## Troubleshooting
See **[Troubleshooting Guide](Troubleshooting.md)** for common deployment issues.
