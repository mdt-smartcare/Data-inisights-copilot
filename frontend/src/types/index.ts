/**
 * Centralized type definitions barrel file
 * 
 * This file re-exports all types from their respective domain modules,
 * providing a single, convenient import point for the entire application.
 * 
 * Usage:
 *   import { User, Message, ChatRequest, FeedbackRequest } from '@/types';
 *   // or
 *   import { User, Message, ChatRequest, FeedbackRequest } from '../types';
 * 
 * Organization:
 * - auth.ts: Authentication and user-related types
 * - chat.ts: Chat messages, responses, and visualization types
 * - feedback.ts: User feedback types
 */

// Authentication types (User, LoginRequest, LoginResponse, etc.)
export * from './auth';

export type UserRole =  'admin' | 'user';

export interface User {
    id?: number;
    username: string;
    email?: string;
    full_name?: string;
    role?: UserRole;
}

// Chat types (Message, ChatRequest, ChatResponse, ChartData, Source)
export * from './chat';

// Feedback types (FeedbackRequest)
export * from './feedback';

// Agent types
export * from './agent';

