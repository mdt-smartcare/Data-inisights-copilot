# API Reference

This document provides a detailed reference for the Data Insights Copilot API.
The API is built with **FastAPI** and follows REST principles.

**Base URL**: `http://localhost:8000/api/v1`

## Authentication (`/auth`)
Handles user login, registration, and session management.

### `POST /auth/login`
Obtain a JWT access token.
- **Request Body**:
    ```json
    {
      "username": "admin",
      "password": "password123"
    }
    ```
- **Response**: `200 OK`
    ```json
    {
      "access_token": "eyJhbGciOiJIUz...",
      "token_type": "bearer",
      "user": { "username": "admin", "role": "super_admin" },
      "expires_in": 43200
    }
    ```

### `POST /auth/register`
Create a new user account.
- **Request Body**:
    ```json
    {
      "username": "jdoe",
      "password": "securePass123",
      "email": "jdoe@example.com",
      "full_name": "John Doe"
    }
    ```
- **Response**: `201 Created` (User object)

---

## Chat (`/chat`)
The core endpoint for interacting with the RAG agent.

### `POST /chat/message`
Send a natural language query to the bot.
- **Headers**: `Authorization: Bearer <token>`
- **Request Body**:
    ```json
    {
      "query": "Show me total sales by region for 2024",
      "session_id": "optional-uuid-for-history"
    }
    ```
- **Response**: `200 OK`
    ```json
    {
      "answer": "Total sales for 2024 were highest in North America...",
      "chart_data": {
        "title": "Sales by Region",
        "type": "bar",
        "data": {
          "labels": ["NA", "EU", "APAC"],
          "values": [50000, 30000, 45000]
        }
      },
      "reasoning_steps": [
        {
          "tool": "sql_query_tool",
          "input": "SELECT region, sum(sales) FROM transactions...",
          "output": "NA|50000, EU|30000..."
        }
      ],
      "trace_id": "abc-123-trace"
    }
    ```

---

## Data Configuration (`/data`)
Manage database connections. *(Requires Admin)*

### `GET /data/connections`
List all configured database connections.

### `POST /data/connections`
Add a new database source.
- **Request Body**:
    ```json
    {
      "name": "Production DB",
      "uri": "postgresql://user:pass@host:5432/dbname",
      "engine_type": "postgresql"
    }
    ```

### `GET /data/connections/{id}/schema`
Fetch the schema (tables/columns) for a specific connection ID.

---

## Embedding Jobs (`/embedding-jobs`)
Manage background ingestion of documents. *(Requires Super Admin)*

### `POST /embedding-jobs`
Start a new embedding job.
- **Request Body**:
    ```json
    {
      "config_id": 1,
      "batch_size": 50,
      "max_concurrent": 5
    }
    ```
- **Response**: `200 OK` with `job_id`.

### `GET /embedding-jobs/{job_id}/progress`
Check the status of a specific job.
- **Response**:
    ```json
    {
      "job_id": "emb-job-123",
      "status": "EMBEDDING",
      "progress_percentage": 45.5,
      "processed_documents": 230,
      "total_documents": 500,
      "estimated_completion_at": "2024-01-01T12:00:00Z"
    }
    ```

---

## System Settings (`/settings`)
Configure global application behavior.

### `GET /settings`
Retrieve all settings grouped by category (Auth, LLM, UI, etc.).

### `PUT /settings/{category}`
Update settings for a category.
- **Request Body**:
    ```json
    {
      "settings": {
        "model_name": "gpt-4-turbo",
        "temperature": 0.5
      },
      "reason": "Upgrading model for better accuracy"
    }
    ```

### `GET /settings/history/{category}`
View audit log of setting changes.

---

## Notifications (`/notifications`)

### `GET /notifications`
Get list of user notifications.
- **Parameters**: `status` (unread, read), `limit`, `offset`.

### `POST /notifications/{id}/read`
Mark a notification as read.
