/**
 * Authentication-related types and interfaces
 * 
 * This file contains all type definitions related to user authentication,
 * including user profiles, login/register requests and responses.
 */

/**
 * User information
 * Represents an authenticated user's profile data
 */
export interface User {
  username: string;      // Primary identifier for the user
  email?: string;        // Optional email address
  full_name?: string;    // Optional display name
  role?: string;         // Optional user role (e.g., 'admin', 'user')
  id?: number;          // Optional database ID
  created_at?: string;  // Optional account creation timestamp
}

/**
 * Login request payload
 * Sent to backend for authentication
 */
export interface LoginRequest {
  username: string;     // Username for authentication
  password: string;     // Plain text password (encrypted in transit via HTTPS)
}

/**
 * Login response from backend API
 * Returned after successful authentication
 */
export interface LoginResponse {
  access_token: string;     // JWT token for authentication
  token_type: string;       // Token type (always 'bearer')
  user: User;               // Authenticated user information
  expires_in: number;       // Token validity duration in seconds
}

/**
 * Registration request payload
 * Sent to backend to create a new user account
 */
export interface RegisterRequest {
  username: string;      // Unique username (min 3 chars)
  password: string;      // Password (min 6 chars)
  email?: string;        // Optional email address
  full_name?: string;    // Optional full name
  role?: string;         // Optional role (defaults to 'user')
}

/**
 * Registration response from backend API
 * Returned after successful user creation
 */
export interface RegisterResponse {
  id: number;                     // Database-generated user ID
  username: string;               // Username (confirmed unique)
  email: string | null;           // Email if provided
  full_name: string | null;       // Full name if provided
  role: string;                   // Assigned role
  created_at: string;             // ISO timestamp of account creation
}
