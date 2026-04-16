# Audit Log Events Documentation

This document provides a comprehensive list of all audit events tracked in the FHIR RAG system. These events are automatically logged to the `audit_logs` table in the database for compliance, security monitoring, and troubleshooting.

---

## Table of Contents
- [Agent Management Events](#agent-management-events)
- [User Management Events](#user-management-events)
- [Database Connection Events](#database-connection-events)
- [Configuration Events](#configuration-events)
- [Security & Access Control Events](#security--access-control-events)

---

## Agent Management Events

### 1. Agent Created
**When:** A new agent is created by an admin or super admin

**Trigger:** `POST /api/v1/agents`

**Logged Information:**
- **Action:** `AGENT_CREATE`
- **Actor:** User who created the agent (ID, username, role)
- **Resource Type:** `agent`
- **Resource ID:** The newly created agent's UUID
- **Resource Name:** Agent name
- **Details:**
  - `type`: Agent type (e.g., "sql", "file")
  - `description`: Agent description

**Use Case:** Track who creates agents and when, useful for audit trails and capacity planning.

**Location:** `backend/api/routes/agents.py:130`

---

### 2. Agent Updated
**When:** An agent's name or description is modified

**Trigger:** `PUT /api/v1/agents/{agent_id}`

**Logged Information:**
- **Action:** `AGENT_UPDATE`
- **Actor:** User who updated the agent
- **Resource Type:** `agent`
- **Resource ID:** Agent's UUID
- **Resource Name:** Updated agent name
- **Details:**
  - `name`: New name (if changed)
  - `description`: New description (if changed)

**Use Case:** Track configuration changes to agents over time.

**Location:** `backend/api/routes/agents.py:177`

---

### 3. Agent Deleted
**When:** An agent is permanently deleted (including all related data)

**Trigger:** `DELETE /api/v1/agents/{agent_id}`

**Logged Information:**
- **Action:** `AGENT_DELETE`
- **Actor:** User who deleted the agent
- **Resource Type:** `agent`
- **Resource ID:** Deleted agent's UUID
- **Resource Name:** Agent name (before deletion)
- **Details:**
  - `cascade`: true (indicates related data was also deleted)

**Use Case:** Critical for compliance - tracks who deleted agents and when. Helps recover from accidental deletions.

**Location:** `backend/api/routes/agents.py:233`

---

### 4. User Assigned to Agent
**When:** A user is granted access to an agent with a specific role (admin or user)

**Trigger:** `POST /api/v1/agents/{agent_id}/users`

**Logged Information:**
- **Action:** `AGENT_USER_ASSIGN`
- **Actor:** User who granted the access
- **Resource Type:** `agent`
- **Resource ID:** Agent's UUID
- **Details:**
  - `assigned_user_id`: UUID of the user being granted access
  - `assigned_user_name`: Username of the user being granted access
  - `per_agent_role`: Role granted ("admin" or "user")

**Use Case:** Track access control changes - who can access which agents and with what permissions.

**Location:** `backend/api/routes/agents.py:334`

---

### 5. User Access Revoked from Agent
**When:** A user's access to an agent is removed

**Trigger:** `DELETE /api/v1/agents/{agent_id}/users/{user_id}`

**Logged Information:**
- **Action:** `AGENT_USER_REVOKE`
- **Actor:** User who revoked the access
- **Resource Type:** `agent`
- **Resource ID:** Agent's UUID
- **Details:**
  - `revoked_user_id`: UUID of the user losing access
  - `revoked_user_name`: Username of the user losing access

**Use Case:** Security audit - track when users lose access to agents (voluntary or security response).

**Location:** `backend/api/routes/agents.py:374`

---

### 6. Bulk Agent Assignment
**When:** A user is assigned to multiple agents at once

**Trigger:** `POST /api/v1/agents/bulk-assign`

**Logged Information:**
- **Action:** `AGENT_BULK_ASSIGN`
- **Actor:** User who performed the bulk assignment
- **Resource Type:** `agent`
- **Resource ID:** "bulk_operation"
- **Details:**
  - `assigned_user_id`: UUID of user receiving access
  - `assigned_user_name`: Username
  - `agent_ids`: List of agent UUIDs
  - `per_agent_role`: Role granted
  - `agent_count`: Number of agents

**Use Case:** Track bulk operations for onboarding new users or reorganizing access.

**Location:** `backend/api/routes/agents.py:487`

---

### 7. Agent Embedding Configuration Updated
**When:** An agent's embedding model settings are changed (provider, model, dimensions)

**Trigger:** `PUT /api/v1/agents/{agent_id}/embedding`

**Logged Information:**
- **Action:** `AGENT_UPDATE`
- **Actor:** User who changed the embedding config
- **Resource Type:** `agent`
- **Resource ID:** Agent's UUID
- **Resource Name:** Agent name
- **Details:**
  - `action`: "embedding_config_update"
  - `provider`: Embedding provider (e.g., "sentence-transformers")
  - `model_name`: Model name (e.g., "bge-m3")
  - `dimension`: Vector dimension (e.g., 1024)
  - `requires_reindex`: Whether reindexing is needed

**Use Case:** Track changes to AI model configurations that affect search quality and performance.

**Location:** `backend/api/routes/agents.py:613`

---

## User Management Events

### 8. User Profile Updated
**When:** A user's profile information or role is modified by a super admin

**Trigger:** `PATCH /api/v1/users/{user_id}`

**Logged Information:**
- **Action:** `USER_UPDATE`
- **Actor:** Super admin who made the change
- **Resource Type:** `user`
- **Resource ID:** User's UUID
- **Resource Name:** Username
- **Details:** Changed fields (e.g., `role`, `full_name`, `email`)

**Use Case:** Track privilege escalation and profile changes for security auditing.

**Location:** `backend/api/routes/users.py:215`

---

### 9. User Deactivated
**When:** A user account is deactivated (soft delete)

**Trigger:** `POST /api/v1/users/{user_id}/deactivate`

**Logged Information:**
- **Action:** `USER_DEACTIVATE`
- **Actor:** Super admin who deactivated the user
- **Resource Type:** `user`
- **Resource ID:** User's UUID
- **Resource Name:** Username

**Use Case:** Track account suspensions for security incidents or offboarding.

**Location:** `backend/api/routes/users.py:275`

---

### 10. User Activated
**When:** A previously deactivated user account is reactivated

**Trigger:** `POST /api/v1/users/{user_id}/activate`

**Logged Information:**
- **Action:** `USER_UPDATE`
- **Actor:** Super admin who reactivated the user
- **Resource Type:** `user`
- **Resource ID:** User's UUID
- **Resource Name:** Username
- **Details:**
  - `is_active`: true
  - `action`: "activate"

**Use Case:** Track account reactivations after suspensions or false-positive security actions.

**Location:** `backend/api/routes/users.py:321`

---

## Database Connection Events

### 11. Database Connection Created
**When:** A new database connection is added to the system

**Trigger:** `POST /api/v1/data/connections`

**Logged Information:**
- **Action:** `CONNECTION_CREATE`
- **Actor:** Admin who created the connection
- **Resource Type:** `connection`
- **Resource ID:** Connection ID
- **Resource Name:** Connection name
- **Details:**
  - `engine_type`: Database type (e.g., "postgresql", "mysql")

**Use Case:** Track data source additions for compliance and data governance.

**Location:** `backend/api/routes/data.py:131`

---

### 12. Database Connection Deleted
**When:** A database connection is removed from the system

**Trigger:** `DELETE /api/v1/data/connections/{connection_id}`

**Logged Information:**
- **Action:** `CONNECTION_DELETE`
- **Actor:** Admin who deleted the connection
- **Resource Type:** `connection`
- **Resource ID:** Connection ID
- **Resource Name:** Connection name

**Use Case:** Track data source removals for security and compliance auditing.

**Location:** `backend/api/routes/data.py:167`

---

## Configuration Events

### 13. System Prompt Published
**When:** A new version of a system prompt is published (activates new RAG configuration)

**Trigger:** `POST /api/v1/config/publish`

**Logged Information:**
- **Action:** `PROMPT_PUBLISH`
- **Actor:** User who published the prompt
- **Resource Type:** `prompt`
- **Resource ID:** Prompt ID
- **Details:**
  - `version`: Version number
  - `agent_id`: Agent UUID (if agent-specific)
  - `data_source_type`: "database" or "file"

**Use Case:** Track configuration changes that affect system behavior and responses.

**Location:** `backend/api/routes/config.py:636`

---

## Security & Access Control Events

### 14. Unauthorized Access Attempt
**When:** A user without required permissions attempts to access a protected resource

**Trigger:** Any protected endpoint when permission check fails

**Logged Information:**
- **Action:** `UNAUTHORIZED_ACCESS_ATTEMPT`
- **Actor:** User who attempted the action
- **Resource Type:** Varies (e.g., "agent", "user", "connection")
- **Resource ID:** Resource being accessed
- **Details:**
  - `required_role`: Role needed for access
  - `user_role`: User's actual role
  - `endpoint`: API endpoint attempted

**Use Case:** Security monitoring - detect potential intrusion attempts or misconfigured permissions.

**Location:** `backend/core/permissions.py:102`

---

### 15. Permission Denied (Insufficient Role)
**When:** A user's role is insufficient for the requested action

**Trigger:** Role-based access control checks throughout the system

**Logged Information:**
- **Action:** `PERMISSION_DENIED`
- **Actor:** User who was denied
- **Resource Type:** Varies
- **Resource ID:** Resource being accessed
- **Details:**
  - `required_role`: Minimum role needed
  - `user_role`: User's actual role
  - `reason`: Explanation of denial

**Use Case:** Security and compliance - track all permission failures for analysis.

**Location:** `backend/core/permissions.py:122`

---

## Audit Log Schema

All audit events are stored in the `audit_logs` table with the following structure:

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,           -- Action type (e.g., AGENT_CREATE)
    actor_id UUID,                         -- User who performed the action (UUID)
    actor_username VARCHAR(255),           -- Username for readability
    actor_role VARCHAR(50),                -- User's role at time of action
    resource_type VARCHAR(50),             -- Type of resource affected
    resource_id VARCHAR(255),              -- ID of the affected resource
    resource_name VARCHAR(255),            -- Name of the resource (for readability)
    details JSONB,                         -- Additional context (flexible JSON)
    ip_address VARCHAR(45),                -- IP address of the request
    user_agent TEXT,                       -- Browser/client info
    timestamp TIMESTAMP DEFAULT NOW(),     -- When the event occurred
    INDEX idx_audit_action (action),
    INDEX idx_audit_actor (actor_id),
    INDEX idx_audit_timestamp (timestamp)
);
```

---

## Testing Checklist for QA

### Agent Management
- [ ] Create an agent → Verify `AGENT_CREATE` log with correct actor and details
- [ ] Update agent name → Verify `AGENT_UPDATE` log shows old and new values
- [ ] Delete agent → Verify `AGENT_DELETE` log with cascade flag
- [ ] Assign user to agent → Verify `AGENT_USER_ASSIGN` with role details
- [ ] Revoke user access → Verify `AGENT_USER_REVOKE` log
- [ ] Bulk assign agents → Verify `AGENT_BULK_ASSIGN` with agent count
- [ ] Update embedding config → Verify `AGENT_UPDATE` with embedding details

### User Management
- [ ] Update user profile → Verify `USER_UPDATE` log with changed fields
- [ ] Deactivate user → Verify `USER_DEACTIVATE` log
- [ ] Reactivate user → Verify `USER_UPDATE` with action="activate"

### Database Connections
- [ ] Add new connection → Verify `CONNECTION_CREATE` with engine type
- [ ] Delete connection → Verify `CONNECTION_DELETE` log

### Configuration
- [ ] Publish new prompt → Verify `PROMPT_PUBLISH` with version info

### Security Events
- [ ] Attempt to access restricted resource → Verify `UNAUTHORIZED_ACCESS_ATTEMPT`
- [ ] Try to perform action with insufficient role → Verify `PERMISSION_DENIED`

---

## Query Examples for Monitoring

### Recent Security Events
```sql
SELECT * FROM audit_logs 
WHERE action IN ('UNAUTHORIZED_ACCESS_ATTEMPT', 'PERMISSION_DENIED')
ORDER BY timestamp DESC 
LIMIT 50;
```

### Agent Changes by User
```sql
SELECT action, resource_name, timestamp, details
FROM audit_logs
WHERE actor_username = 'specific_user' 
AND action LIKE 'AGENT_%'
ORDER BY timestamp DESC;
```

### All User Deactivations
```sql
SELECT actor_username, resource_name, timestamp
FROM audit_logs
WHERE action = 'USER_DEACTIVATE'
ORDER BY timestamp DESC;
```

### Configuration Changes in Last 7 Days
```sql
SELECT * FROM audit_logs
WHERE action = 'PROMPT_PUBLISH'
AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;
```

---

## Notes for Product Managers

1. **Compliance Ready**: All 15 audit events provide full traceability for SOC 2, HIPAA, and other compliance frameworks.

2. **Security Monitoring**: Events 14 and 15 specifically track unauthorized access attempts, enabling proactive security monitoring.

3. **Change Tracking**: Every configuration change (agents, prompts, connections) is logged with actor information for rollback and troubleshooting.

4. **User Activity**: Complete audit trail of user account lifecycle (creation via OIDC JIT, updates, deactivation, reactivation).

5. **Performance Impact**: Audit logging is asynchronous and does not block API responses.

---

**Last Updated:** 2026-03-25  
**Total Audit Events:** 15  
**Maintained By:** Backend Team
