# Role-Based Access Control (RBAC) System

This system implements a 4-level role hierarchy to manage access to the application.

## Roles & Permissions

### 1. Super Admin (`admin`)
**Purpose:** System-wide governance and configuration.
- **Can:** Manage connections, Edit/Publish prompts, Chat, View history.
- **Cannot:** (No technical restrictions).

### 2. Editor (`editor`)
**Purpose:** AI configuration and prompt engineering.
- **Can:** Edit/Publish prompts, Chat, View history, View connections.
- **Cannot:** Create/Delete connections.

### 3. User (`user`)
**Purpose:** Consumption of insights.
- **Can:** Chat, View history, View connections (read-only).
- **Cannot:** Edit prompts, Manage connections.

### 4. Viewer (`viewer`)
**Purpose:** Compliance and audit.
- **Can:** View connections, View history.
- **Cannot:** Chat (Input disabled), Edit prompts, Manage connections.

## Implementation Details

- **Backend:** `backend/core/permissions.py` defines roles. `data.py`, `config.py`, and `chat.py` enforce them using `require_role`.
- **Frontend:** `src/utils/permissions.ts` centralizes permission logic. `ConfigPage.tsx` and `ChatPage.tsx` use these utils to toggle UI elements.
