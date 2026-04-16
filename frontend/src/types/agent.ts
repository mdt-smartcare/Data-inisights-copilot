/**
 * Agent-related types and interfaces
 */

export interface Agent {
    id: string;  // UUID
    name: string;
    description?: string;
    type: string;
    db_connection_uri?: string;
    created_at?: string;
    user_role?: string; // Role of the current user for this agent
}

/**
 * Agent with user-specific access information.
 * Returned when fetching agents assigned to a specific user.
 */
export interface UserAgentAssignment {
    id: string;  // UUID
    name: string; // Transformed from 'title' in API response
    title?: string; // Original API field
    description?: string;
    created_by?: string | null;
    created_at: string;
    updated_at: string;
    role: string;  // User's role on this agent (user, editor, admin)
    granted_at: string;
    granted_by?: string | null;
}

/**
 * Response from GET /api/v1/users/{user_id}/agents
 */
export interface GetUserAgentsResponse {
    agents: UserAgentAssignment[];
    total: number;
    user_id: string;
}
