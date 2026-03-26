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
