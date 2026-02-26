/**
 * TypeScript types for embedding jobs and notifications.
 */

// ============================================
// Embedding Job Types
// ============================================

export type EmbeddingJobStatus =
    | 'QUEUED'
    | 'PREPARING'
    | 'EMBEDDING'
    | 'VALIDATING'
    | 'STORING'
    | 'COMPLETED'
    | 'FAILED'
    | 'CANCELLED';

export interface EmbeddingJobProgress {
    job_id: string;
    status: EmbeddingJobStatus;
    phase: string | null;
    total_documents: number;
    processed_documents: number;
    failed_documents: number;
    progress_percentage: number;
    current_batch: number;
    total_batches: number;
    documents_per_second: number | null;
    estimated_time_remaining_seconds: number | null;
    elapsed_seconds: number | null;
    errors_count: number;
    recent_errors: string[];
    started_at: string | null;
    completed_at: string | null;
}

export interface EmbeddingJobSummary {
    job_id: string;
    status: EmbeddingJobStatus;
    total_documents: number;
    processed_documents: number;
    failed_documents: number;
    duration_seconds: number | null;
    average_speed: number | null;
    validation_passed: boolean;
    error_message: string | null;
    started_at: string | null;
    completed_at: string | null;
}

/**
 * Configuration for parent-child chunking strategy.
 * Controls how documents are split for embedding.
 */
export interface ChunkingConfig {
    parent_chunk_size: number;      // 200-2000, default 800
    parent_chunk_overlap: number;   // 0-500, default 150
    child_chunk_size: number;       // 50-500, default 200
    child_chunk_overlap: number;    // 0-100, default 50
}

/**
 * Configuration for parallel processing.
 * Controls worker count and batch sizes.
 */
export interface ParallelizationConfig {
    num_workers?: number;           // 1-16, null = auto
    chunking_batch_size?: number;   // 100-50000, null = auto
    delta_check_batch_size: number; // 1000-100000, default 50000
}

/**
 * Request model for starting a new embedding job.
 * All optional fields have sensible defaults on the backend.
 */
export interface EmbeddingJobCreate {
    config_id: number;
    
    // Batch Processing Config
    batch_size?: number;            // 10-500, default 50
    max_concurrent?: number;        // 1-20, default 5
    incremental?: boolean;          // default true
    
    // Chunking Config (optional)
    chunking?: ChunkingConfig;
    
    // Parallelization Config (optional)
    parallelization?: ParallelizationConfig;
    
    // Circuit Breaker Config
    max_consecutive_failures?: number;  // 1-20, default 5
    retry_attempts?: number;            // 1-10, default 3
}

// ============================================
// Notification Types
// ============================================

export type NotificationType =
    | 'embedding_started'
    | 'embedding_progress'
    | 'embedding_complete'
    | 'embedding_failed'
    | 'embedding_cancelled'
    | 'config_published'
    | 'config_rolled_back'
    | 'schema_change_detected';

export type NotificationPriority = 'low' | 'medium' | 'high' | 'critical';

export type NotificationStatus = 'unread' | 'read' | 'dismissed';

export interface Notification {
    id: number;
    user_id: number;
    type: NotificationType;
    priority: NotificationPriority;
    title: string;
    message: string | null;
    action_url: string | null;
    action_label: string | null;
    status: NotificationStatus;
    related_entity_type: string | null;
    related_entity_id: number | null;
    channels: string[];
    read_at: string | null;
    created_at: string;
}

export interface NotificationPreferences {
    in_app_enabled: boolean;
    email_enabled: boolean;
    webhook_enabled: boolean;
    webhook_url: string | null;
    webhook_format: 'slack' | 'teams' | 'generic';
    notification_types: Record<string, boolean>;
    quiet_hours_enabled: boolean;
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
    quiet_hours_timezone: string;
}

export interface NotificationPreferencesUpdate {
    in_app_enabled?: boolean;
    email_enabled?: boolean;
    webhook_enabled?: boolean;
    webhook_url?: string;
    webhook_format?: 'slack' | 'teams' | 'generic';
    notification_types?: Record<string, boolean>;
    quiet_hours_enabled?: boolean;
    quiet_hours_start?: string;
    quiet_hours_end?: string;
    quiet_hours_timezone?: string;
}

// ============================================
// WebSocket Message Types
// ============================================

export interface WebSocketProgressMessage {
    event: 'embedding_progress';
    job_id: string;
    status: EmbeddingJobStatus;
    phase: string | null;
    progress: {
        total_documents: number;
        processed_documents: number;
        failed_documents: number;
        percentage: number;
        current_batch: number;
        total_batches: number;
    };
    performance: {
        documents_per_second: number | null;
        estimated_time_remaining_seconds: number | null;
        elapsed_seconds: number | null;
    };
    errors: {
        count: number;
        recent: string[];
    };
    timestamp: string;
}

export interface WebSocketJobFinishedMessage {
    event: 'job_finished';
    job_id: string;
    status: EmbeddingJobStatus;
    final_progress: number;
}

export type WebSocketMessage = WebSocketProgressMessage | WebSocketJobFinishedMessage;
