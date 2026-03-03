# Role-Based Access Control (RBAC) System

This system implements a 3-level role hierarchy to manage access to the application, with per-agent role assignments for granular control.

## System Roles

### 1. Super Admin (`super_admin`)
**Purpose:** System-wide governance and full access to all resources.
- **Can:** View all audit logs, Manage users (edit/deactivate admins and users), Manage connections, Edit/Publish prompts, Chat, View history.
- **Agent Access:** Can see and configure ALL agents (bypasses per-agent roles).
- **User Management:** Can edit role and deactivate admins/users. Cannot edit other super_admins.
- **Agent Assignment:** Can assign any agent to any user with any per-agent role (admin or user).

### 2. Admin (`admin`)
**Purpose:** AI configuration and agent management with scoped access.
- **Can:** View audit logs, View users, Manage connections, Edit prompts, Chat, Create agents.
- **Agent Access:** Can only see agents they created OR are assigned to. Per-agent role determines if they can configure or just chat.
- **User Management:** Cannot edit roles or deactivate users (super_admin only).
- **Agent Assignment:** Can assign agents they have admin access to, with chat-only (`user`) per-agent role.
- **Cannot:** Access agents they weren't assigned to, Publish prompts, Edit/Deactivate users, Grant admin per-agent role.

### 3. User (`user`)
**Purpose:** Consumption of insights.
- **Can:** Chat with assigned agents, Execute queries.
- **Agent Access:** Can only see assigned agents, chat-only access.
- **Cannot:** Edit prompts, Create agents, Manage connections, Configure agents, Manage users.

## Per-Agent Roles

The `user_agents` table tracks per-agent assignments with roles:

| Per-Agent Role | Permissions |
|----------------|-------------|
| `admin` | Can configure agent (prompts, connections, settings), manage agent users |
| `user` | Can only chat with the agent |

**Note:** Super Admins bypass per-agent roles - they have `admin` access to all agents.

## Agent Visibility Matrix

| System Role | Agents Visible | Can Configure Agent? |
|-------------|----------------|----------------------|
| `super_admin` | ALL agents | YES (all) |
| `admin` | Created + Assigned | Only if per-agent role = `admin` |
| `user` | Assigned only | NO (chat only) |

## User Management Matrix

| Actor | Can Edit/Deactivate |
|-------|---------------------|
| `super_admin` | Admins and Users (not other super_admins) |
| `admin` | No one (view only) |
| `user` | No one |

## Agent Assignment Matrix

| Actor | Can Assign Agents To | Per-Agent Role Options |
|-------|----------------------|------------------------|
| `super_admin` | Admins and Users | `admin` or `user` |
| `admin` | Admins and Users | `user` only (chat access) |
| `user` | No one | N/A |

**Important:** Admins can only assign agents they have `admin` per-agent role on.

## Implementation Details

- **Backend:** 
  - `backend/core/roles.py` defines roles and hierarchy
  - `backend/core/permissions.py` provides FastAPI dependencies (`require_admin`, `require_super_admin`, etc.)
  - `backend/api/routes/agents.py` enforces role-based agent listing and per-agent authorization
  - `backend/api/routes/users.py` enforces super_admin-only for edit/deactivate operations
  
- **Frontend:** 
  - `src/utils/permissions.ts` centralizes permission logic
  - `roleAtLeast()`, `isSuperAdmin()`, `isAtLeastAdmin()` helpers
  - Components check `user_role` from agent response for per-agent access
  - UsersPage: `canAssignAgents()` and `canEditOrDeactivate()` enforce UI visibility

## API Endpoints

| Endpoint | Required Role | Notes |
|----------|---------------|-------|
| `GET /agents` | `user`+ | Returns agents based on system role |
| `GET /agents/all` | `super_admin` | DEPRECATED - use GET /agents |
| `POST /agents` | `admin`+ | Create new agent (creator gets admin per-agent role) |
| `GET /agents/{id}/users` | `admin`+ | Requires admin per-agent role on agent |
| `POST /agents/{id}/users` | `admin`+ | Requires admin per-agent role; admin can only assign `user` role |
| `DELETE /agents/{id}/users/{uid}` | `admin`+ | Requires admin per-agent role on agent |
| `POST /agents/bulk-assign` | `admin`+ | Checks per-agent auth; admin can only assign `user` role |
| `GET /users` | `admin`+ | List all users |
| `PATCH /users/{id}` | `super_admin` | Edit user role/profile; cannot edit super_admins |
| `POST /users/{id}/deactivate` | `super_admin` | Cannot deactivate super_admins |
| `POST /users/{id}/activate` | `super_admin` | Reactivate user |
| `GET /users/{id}/agents` | `admin`+ | Get user's assigned agents with per-agent roles |
