# User Authentication Flow — Sequence Diagram

> [!NOTE]
> This diagram is reverse-engineered from the actual codebase: [auth.py](file:///Users/adityanbhatt/Documents/Data-inisights-copilot/backend/api/routes/auth.py), [permissions.py](file:///Users/adityanbhatt/Documents/Data-inisights-copilot/backend/core/permissions.py), [LoginPage.tsx](file:///Users/adityanbhatt/Documents/Data-inisights-copilot/frontend/src/pages/LoginPage.tsx), [AuthContext.tsx](file:///Users/adityanbhatt/Documents/Data-inisights-copilot/frontend/src/contexts/AuthContext.tsx), and [api.ts](file:///Users/adityanbhatt/Documents/Data-inisights-copilot/frontend/src/services/api.ts).

---

## Participants

| Participant | Type | Description |
|---|---|---|
| **User** | Actor | End-user interacting with the login form |
| **LoginPage (React)** | Frontend | `LoginPage.tsx` — form submission, error display, navigation |
| **Axios Interceptor** | Frontend | `api.ts` — token injection, expiry check, 401 redirect |
| **FastAPI Gateway** | Backend | `/auth/login` route in `auth.py` |
| **Auth Service** | Backend | `permissions.py` — JWT creation & validation via `python-jose` |
| **SQLite Database** | Persistence | `DatabaseService` — user lookup, bcrypt password verification |
| **AuthContext** | Frontend | `AuthContext.tsx` — global session state, session restoration |

---

## Mermaid Sequence Diagram

```mermaid
sequenceDiagram
    autonumber

    actor User
    participant LP as LoginPage<br/>(React)
    participant AX as Axios<br/>Interceptor
    participant GW as FastAPI<br/>Gateway
    participant AS as Auth<br/>Service
    participant DB as SQLite<br/>Database
    participant AC as Auth<br/>Context

    %% ─── Login Flow ───────────────────────────────────
    rect rgb(240, 248, 255)
    Note over User, AC: Login Flow
    User ->> LP: Submit username & password
    LP ->> LP: setIsLoading(true), clear errors
    LP ->> AX: POST /api/v1/auth/login {username, password}
    Note right of AX: Public endpoint — no token injected
    AX ->> GW: Forward POST request (HTTPS)

    GW ->> DB: get_user_by_username(username)
    DB -->> GW: user record or null

    %% ─── Alt: User Exists vs Not Found ───────────────
    alt User NOT found
        GW -->> AX: 401 Unauthorized "Invalid username or password"
        AX -->> LP: Error response
        LP ->> LP: setError(message), setIsLoading(false)
        LP -->> User: Display error alert
    else User found
        GW ->> GW: Check user.is_active

        alt Account deactivated
            GW -->> AX: 403 Forbidden "Account is deactivated"
            AX -->> LP: Error response
            LP ->> LP: setError(message), setIsLoading(false)
            LP -->> User: Display deactivation alert
        else Account active
            GW ->> DB: verify_password(plain, password_hash)
            DB -->> GW: bcrypt match result

            alt Password INVALID
                GW -->> AX: 401 Unauthorized "Invalid username or password"
                AX -->> LP: Error response
                LP ->> LP: setError(message), setIsLoading(false)
                LP -->> User: Display error alert
            else Password VALID
                GW ->> AS: create_access_token(sub=username, exp=720min)
                AS -->> GW: JWT access_token
                GW -->> AX: 200 OK {access_token, token_type, user, expires_in}
                AX -->> LP: LoginResponse

                LP ->> LP: Store token in localStorage
                Note right of LP: localStorage.setItem("auth_token", token)<br/>localStorage.setItem("expiresAt", expiry)

                LP ->> AC: setUser({username, email, full_name, role})

                alt Role = "super_admin"
                    LP ->> LP: navigate("/insights")
                else Other roles
                    LP ->> LP: navigate("/chat")
                end

                LP -->> User: Redirect to dashboard
            end
        end
    end
    end

    %% ─── Session Restoration Flow ────────────────────
    rect rgb(245, 255, 245)
    Note over User, AC: Session Restoration (on App Mount)
    AC ->> AC: Check localStorage for auth_token
    alt Token exists in localStorage
        AC ->> AX: GET /api/v1/auth/me
        AX ->> AX: Inject Authorization: Bearer token
        AX ->> GW: GET /auth/me + Bearer token

        GW ->> AS: jwt.decode(token, secret_key)
        AS -->> GW: payload {sub: username}

        GW ->> DB: get_user_by_username(username)
        DB -->> GW: user record

        alt Valid token & user found
            GW -->> AX: 200 OK User profile
            AX -->> AC: User object
            AC ->> AC: setUser(profile), setIsLoading(false)
        else Invalid/expired token
            GW -->> AX: 401 Unauthorized
            AX ->> AX: Clear localStorage tokens
            AX ->> AX: Redirect to /login
        end
    else No token
        AC ->> AC: setIsLoading(false)
    end
    end

    %% ─── Authenticated Request Flow ──────────────────
    rect rgb(255, 248, 240)
    Note over User, AC: Authenticated API Request
    User ->> LP: Perform action (e.g., send chat query)
    LP ->> AX: API request

    AX ->> AX: Check token expiry vs current time

    alt Token expired
        AX ->> AX: Clear localStorage tokens
        AX ->> AX: Redirect to /login
    else Token valid
        AX ->> AX: Inject Authorization header
        AX ->> GW: Request + Bearer token

        GW ->> AS: get_current_user(token)
        AS ->> AS: jwt.decode(token)
        AS ->> DB: get_user_by_username(sub)
        DB -->> AS: user record

        alt RBAC check passes
            AS -->> GW: User object
            GW -->> AX: 200 OK response
            AX -->> LP: Response data
        else 403 Forbidden
            GW -->> AX: 403 "Operation not permitted"
            AX -->> LP: Error
            LP -->> User: Access denied message
        end
    end
    end

    %% ─── Logout Flow ─────────────────────────────────
    rect rgb(255, 240, 240)
    Note over User, AC: Logout Flow
    User ->> LP: Click Logout
    LP ->> AC: logout()
    AC ->> AC: setUser(null)
    AC ->> AC: localStorage.removeItem("auth_token")
    AC ->> AC: localStorage.removeItem("expiresAt")
    LP -->> User: Redirect to /login
    end
```

---

## Key Design Decisions

| Aspect | Implementation Detail |
|---|---|
| **Token Type** | JWT (HS256) via `python-jose`, stored in `localStorage` |
| **Token Lifetime** | 720 minutes (12 hours), configurable via `access_token_expire_minutes` |
| **Password Hashing** | bcrypt via `DatabaseService.verify_password()` |
| **RBAC Model** | Hierarchical: `super_admin > editor > user > viewer` |
| **Session Restore** | On app mount, `AuthContext` calls `GET /auth/me` if token exists |
| **401 Handling** | Axios response interceptor clears tokens and redirects to `/login` |
| **Frontend Routing** | Role-based redirect: `super_admin` → `/insights`, others → `/chat` |
