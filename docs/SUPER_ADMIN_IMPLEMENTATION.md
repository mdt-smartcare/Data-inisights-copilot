# Super Admin Role Implementation - Context Document

**Last Updated:** February 27, 2026  
**Status:** Implementation Complete  
**Purpose:** This document captures the full context of the super_admin role implementation for session continuity.

---

## 1. Project Overview

### Goal
Implement a 3-tier role hierarchy (`super_admin` > `admin` > `user`) with per-agent role assignments for granular access control.

### Key Requirements (Confirmed with User)
1. **Super Admin**: Full access to ALL agents, can edit/deactivate admins and users
2. **Admin**: Scoped access - only sees agents they created or are assigned to
3. **Per-Agent Roles**: `admin` (configure) vs `user` (chat only) - applies to admins
4. **Super Admin bypasses** per-agent role checks
5. **Admin can assign agents** to other admins/users but **only with `user` per-agent role** (chat access)
6. **Only Super Admin** can grant `admin` per-agent role (configure access)

---

## 2. Architecture

### Role Hierarchy
```
super_admin (index 0) > admin (index 1) > user (index 2)
```
Lower index = more privileges. Use `roleAtLeast(userRole, requiredRole)` to check hierarchy.

### Per-Agent Roles (stored in `user_agents` table)
| Per-Agent Role | Access Level |
|----------------|--------------|
| `admin` | Configure agent (prompts, connections, settings) |
| `user` | Chat only |

### Database Schema
```sql
-- user_agents table
CREATE TABLE user_agents (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    role TEXT DEFAULT 'user',  -- 'admin' or 'user'
    granted_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);
```

---

## 3. Files Modified

### Backend

#### `backend/core/roles.py`
- Added `SUPER_ADMIN = "super_admin"` to Role enum
- Updated `ROLE_HIERARCHY = ["super_admin", "admin", "user"]`
- Added Keycloak role mappings for super_admin

#### `backend/core/permissions.py`
- `require_super_admin` is now a real dependency (not alias)
- `require_admin` accepts both `super_admin` and `admin`

#### `backend/api/routes/agents.py` (Major Refactor)
- Added helper functions:
  - `resolve_user_id(db, current_user)` - DRY user ID resolution
  - `check_agent_admin_access(db, agent_id, current_user)` - Per-agent authorization
- `list_agents()`: Role-based agent listing (super_admin sees all, admin sees created+assigned)
- `create_agent()`: Auto-assigns creator with `admin` per-agent role
- `get_agent_users()`: Added per-agent authorization check
- `assign_user()`: Added per-agent auth + blocks admin from granting `admin` per-agent role
- `revoke_access()`: Added per-agent authorization check
- `bulk_assign_agents()`: Per-agent auth check per agent, returns `unauthorized` list
- `/agents/all`: Marked as `deprecated=True`

#### `backend/api/routes/users.py` (Role Hierarchy Enforcement)
- `update_user()`: Changed to `require_super_admin`, blocks editing super_admins, blocks promotion to super_admin
- `deactivate_user()`: Changed to `require_super_admin`, blocks deactivating super_admins
- `activate_user()`: Changed to `require_super_admin`
- `get_user_agents()`: Fixed to return correct per-agent roles for each user type

#### `backend/sqliteDb/db.py`
- Added `get_agents_for_admin(user_id)` method - returns agents created by OR assigned to admin

### Frontend

#### `frontend/src/types/index.ts`
- Updated `UserRole` type: `'super_admin' | 'admin' | 'user'`

#### `frontend/src/utils/permissions.ts`
- `ROLE_HIERARCHY = ['super_admin', 'admin', 'user']`
- Added `isSuperAdmin(user)` helper
- Added `isAtLeastAdmin(user)` helper
- Updated `roleAtLeast()` for hierarchy comparison
- Updated `canPublishPrompt()` and `canRollback()` to allow admin role (for their own agents)

#### `frontend/src/App.tsx`
- `ProtectedRoute` uses `roleAtLeast()` for hierarchy-based access checks
- Super admin can access all admin routes

#### `frontend/src/pages/UsersPage.tsx` (Major Rewrite)
- State: `selectedAgentRoles: Record<number, 'admin' | 'user'>` - per-agent role selection
- Helper: `canAssignAgents(targetUser)` - both super_admin and admin can assign
- Helper: `canEditOrDeactivate(targetUser)` - super_admin only
- Helper: `setAgentRole(agentId, role)` - set per-agent role for selection
- Action buttons: Separate visibility for Edit/Deactivate (super_admin) vs Agents (both)
- Agent modal: Inline role selector per agent row (super_admin only)
- Agent modal: Shows "Chat" badge for admins (they can only assign user role)
- Agent modal: Summary shows breakdown (X configure, Y chat)

#### `frontend/src/pages/CallbackPage.tsx`, `LoginPage.tsx`
- Updated redirect logic to use `roleAtLeast()` for super_admin support

#### Test Files Updated
- `frontend/src/App.test.tsx`
- `frontend/src/pages/UsersPage.test.tsx`
- `frontend/src/utils/permissions.test.ts`

### Documentation

#### `wiki/RBAC.md`
- Added User Management Matrix
- Added Agent Assignment Matrix
- Complete API endpoints table with correct permissions
- Marked `/agents/all` as deprecated

---

## 4. Business Logic Summary

### User Management (UsersPage)

| Actor | See User List | Edit Role | Deactivate | Assign Agents |
|-------|---------------|-----------|------------|---------------|
| Super Admin | ✅ All users | ✅ Admins/Users | ✅ Admins/Users | ✅ Any agent, any role |
| Admin | ✅ All users | ❌ | ❌ | ✅ Their agents, user role only |
| User | ❌ | ❌ | ❌ | ❌ |

### Agent Assignment Flow

**Super Admin assigning agents:**
1. Opens agent modal for any admin/user
2. Sees ALL agents in the system
3. Selects agents with inline role picker (💬 Chat / ⚙️ Config)
4. Can assign with `admin` or `user` per-agent role

**Admin assigning agents:**
1. Opens agent modal for any admin/user
2. Only sees agents they can configure (per-agent role = `admin`)
3. Selects agents (no role picker - always `user`)
4. Backend enforces `user` per-agent role only

### API Authorization Flow

```
POST /agents/{agent_id}/users
  ├── require_admin (super_admin OR admin)
  ├── check_agent_admin_access(agent_id, current_user)
  │     ├── super_admin? → always true
  │     └── admin? → check user_agents.role = 'admin'
  ├── if role == 'admin' AND current_user != super_admin → 403
  └── assign_user_to_agent(...)
```

---

## 5. Testing Checklist

### Backend Tests
```bash
cd backend && pytest tests/
```

### Frontend Tests
```bash
cd frontend && npm run test
```

### Manual Test Scenarios

| Scenario | Expected |
|----------|----------|
| Super admin views Users page | Sees Edit/Deactivate/Agents for admins and users |
| Admin views Users page | Only sees Agents button for users and admins |
| Super admin assigns agent with Config role | Works |
| Admin tries to assign agent with Config role | 403 error |
| Admin assigns agent they don't have access to | 403 error |
| Super admin edits another super_admin | 403 "cannot edit super_admin" |
| Admin tries to edit any user | 403 (requires super_admin) |

---

## 6. Known Considerations

### Keycloak Integration
- Super admin role should be mapped from Keycloak groups/roles
- See `KEYCLOAK_ROLE_MAPPINGS` in `roles.py`
- Super admin promotion must happen via Keycloak, not API

### Migration
- No database migration needed - uses existing `user_agents` table
- Existing admins will have role-based access immediately
- Consider seeding a super_admin user for initial setup

### Future Enhancements (Not Implemented)
- [ ] Per-agent role editing (change user from chat to configure)
- [ ] Bulk role update for existing assignments
- [ ] Agent transfer (change owner/creator)
- [ ] Role change audit logging

---

## 7. Quick Reference

### Frontend Permission Helpers
```typescript
import { isSuperAdmin, isAtLeastAdmin, roleAtLeast } from '@/utils/permissions';

// Check if user is super admin
if (isSuperAdmin(user)) { ... }

// Check if user is admin or higher
if (isAtLeastAdmin(user)) { ... }

// Check role hierarchy
if (roleAtLeast(user.role, 'admin')) { ... }
```

### Backend Permission Dependencies
```python
from backend.core.permissions import require_super_admin, require_admin, require_user

# Super admin only
@router.post("/endpoint")
async def endpoint(current_user: User = Depends(require_super_admin)):
    ...

# Admin or super admin
@router.post("/endpoint")
async def endpoint(current_user: User = Depends(require_admin)):
    ...
```

### Per-Agent Authorization
```python
from backend.api.routes.agents import check_agent_admin_access

if not check_agent_admin_access(db, agent_id, current_user):
    raise HTTPException(status_code=403, detail="No admin access to this agent")
```

---

## 8. Session Continuation Notes

If continuing this work in a new session:

1. **All core implementation is complete** - the 3-tier system is fully functional
2. **Focus areas for future work:**
   - Add tests for new authorization logic
   - Consider audit logging for role changes
   - UI polish for agent assignment modal
3. **Key files to review:**
   - `backend/api/routes/agents.py` - main authorization logic
   - `frontend/src/pages/UsersPage.tsx` - UI implementation
   - `wiki/RBAC.md` - design documentation
