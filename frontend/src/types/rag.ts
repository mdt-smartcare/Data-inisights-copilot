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
    delta_check_batch_size?: number; // 1000-100000, default 50000
}

/**
 * Configuration for medical terminology enrichment.
 * Improves embedding quality by expanding clinical abbreviations.
 */
export interface MedicalContextConfig {
    // Medical abbreviation mappings (column_name -> human_readable_name)
    // Example: {"bp": "Blood Pressure", "hr": "Heart Rate"}
    medical_context: Record<string, string>;

    // Clinical boolean flag prefixes to recognize
    // Example: ["is_", "has_", "history_of_"]
    clinical_flag_prefixes: string[];

    // Whether to merge with YAML defaults
    use_yaml_defaults: boolean;
}

/**
 * Request model for starting a new embedding job.
 * Only config_id is required - all settings are read from agent_config table.
 */
export interface EmbeddingJobCreate {
    config_id: number;
    incremental?: boolean;  // default false
    batch_size?: number;
    max_concurrent?: number;
    chunking?: ChunkingConfig;
    parallelization?: ParallelizationConfig;
    medical_context_config?: MedicalContextConfig;
    max_consecutive_failures?: number;
    retry_attempts?: number;
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
