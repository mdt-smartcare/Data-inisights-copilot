# Database Schema

The Data Insights Copilot uses **SQLite** as its primary database (`app.db`). The schema is managed via a custom migration system.

## Core Tables

These tables are initialized by the application core.

### `users`
Stores user accounts and authentication details.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incrementing user ID. |
| `username` | TEXT UNIQUE | Unique username for login. |
| `email` | TEXT UNIQUE | User email address. |
| `password_hash` | TEXT | Bcrypt password hash. |
| `full_name` | TEXT | Display name. |
| `role` | TEXT | Role (`super_admin`, `editor`, `user`, `viewer`). |
| `is_active` | INTEGER | 1 = Active, 0 = Deactivated. |
| `created_at` | TIMESTAMP | Creation time. |

### `system_prompts`
Versioned history of the system prompt used by the Agent.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Prompt ID. |
| `prompt_text` | TEXT | The actual prompt template. |
| `version` | INTEGER | Version number. |
| `is_active` | INTEGER | 1 if this is the currently active prompt. |
| `created_by` | TEXT | Username of creator. |

### `prompt_configs`
Configuration associated with a specific system prompt version.
| Column | Type | Description |
|--------|------|-------------|
| `prompt_id` | INTEGER PK | FK to `system_prompts.id`. |
| `connection_id` | INTEGER | FK to `db_connections.id`. |
| `schema_selection` | TEXT | JSON list of enabled tables. |
| `data_dictionary` | TEXT | Markdown data dictionary content. |
| `reasoning` | TEXT | JSON configuration for reasoning steps. |
| `example_questions` | TEXT | JSON list of few-shot examples. |

### `db_connections`
External database connections that the Agent can query.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Connection ID. |
| `name` | TEXT | Unique display name. |
| `uri` | TEXT | SQLAlchemy connection string. |
| `engine_type` | TEXT | Database type (e.g., `postgresql`). |

---

## RAG & Embeddings (Migrations 001, 003)

### `rag_configurations`
Stores complete configuration snapshots for reproducibility.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Config ID. |
| `version` | TEXT | Semantic version (e.g., "1.0.0"). |
| `status` | TEXT | `draft`, `published`, `archived`. |
| `schema_snapshot` | TEXT | JSON snapshot of schema at time of creation. |
| `config_hash` | TEXT | SHA-256 hash for integrity. |

### `embedding_jobs`
Tracks background embedding generation jobs.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Internal ID. |
| `job_id` | TEXT UNIQUE | Public Job ID (e.g., `emb-job-...`). |
| `status` | TEXT | `QUEUED`, `EMBEDDING`, `COMPLETED`, `FAILED`. |
| `total_documents` | INTEGER | Total docs to process. |
| `progress_percentage` | REAL | 0.0 to 100.0. |

### `embedding_versions`
Links a RAG configuration to a specific set of generated embeddings.
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Version ID. |
| `embedding_model` | TEXT | Model used (e.g., `BAAI/bge-m3`). |
| `embedding_dimension` | INTEGER | Vector size (e.g., 1024). |

---

## System Settings (Migration 006)

### `system_settings`
Key-value store for application configuration (UI, Auth, LLM settings).
| Column | Type | Description |
|--------|------|-------------|
| `category` | TEXT | Group (e.g., `llm`, `auth`). |
| `key` | TEXT | Setting key. |
| `value` | TEXT | JSON-encoded value. |
| `value_type` | TEXT | `string`, `number`, `boolean`, `secret`. |
| `is_sensitive` | INTEGER | 1 if value should be masked (e.g., API keys). |

### `settings_history`
Audit trail for setting changes.
| Column | Type | Description |
|--------|------|-------------|
| `setting_id` | INTEGER | FK to `system_settings`. |
| `previous_value` | TEXT | Value before change. |
| `new_value` | TEXT | Value after change. |
| `changed_by` | TEXT | Username of modifier. |

---

## Notifications (Migration 002)

### `notifications`
In-app notifications for users.
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | INTEGER | Recipient. |
| `type` | TEXT | Event type. |
| `title` | TEXT | Notification title. |
| `status` | TEXT | `unread`, `read`. |

### `notification_preferences`
User settings for notification channels.
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | INTEGER | User ID. |
| `email_enabled` | INTEGER | 1 = Enabled. |
| `webhook_url` | TEXT | Optional Slack/Teams webhook. |
