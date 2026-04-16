-- Migration: 002_notifications.sql
-- Description: Create notification system tables for multi-channel delivery
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-01-28

-- ============================================
-- Notifications Table
-- Stores all notifications across channels
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    
    -- Notification Content
    type TEXT NOT NULL,                        -- embedding_started, embedding_complete, config_published, etc.
    priority TEXT NOT NULL DEFAULT 'medium',   -- low, medium, high, critical
    title TEXT NOT NULL,
    message TEXT,
    
    -- Action Support
    action_url TEXT,                           -- URL to navigate to on click
    action_label TEXT,                         -- Button text (e.g., "View Details")
    
    -- Related Entity
    related_entity_type TEXT,                  -- rag_configuration, embedding_job, etc.
    related_entity_id INTEGER,
    
    -- Delivery Channels (JSON array)
    channels TEXT DEFAULT '["in_app"]',        -- ["in_app", "email", "webhook"]
    
    -- Status Tracking
    status TEXT DEFAULT 'unread',              -- unread, read, dismissed
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_status ON notifications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);
CREATE INDEX IF NOT EXISTS idx_notifications_priority ON notifications(priority);

-- ============================================
-- Notification Preferences Table
-- User-specific notification settings
-- ============================================
CREATE TABLE IF NOT EXISTS notification_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    
    -- Channel Toggles
    in_app_enabled INTEGER DEFAULT 1,          -- Boolean: Enable in-app notifications
    email_enabled INTEGER DEFAULT 1,           -- Boolean: Enable email notifications
    webhook_enabled INTEGER DEFAULT 0,         -- Boolean: Enable webhook notifications
    
    -- Webhook Configuration
    webhook_url TEXT,                          -- Custom webhook URL
    webhook_format TEXT DEFAULT 'slack',       -- slack, teams, generic
    
    -- Notification Type Preferences (JSON object)
    -- Example: {"embedding_complete": true, "config_published": true}
    notification_types TEXT DEFAULT '{}',
    
    -- Quiet Hours (for non-critical notifications)
    quiet_hours_enabled INTEGER DEFAULT 0,
    quiet_hours_start TEXT,                    -- Time format: "22:00"
    quiet_hours_end TEXT,                      -- Time format: "08:00"
    quiet_hours_timezone TEXT DEFAULT 'UTC',
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- Notification Delivery Log Table
-- Tracks delivery attempts across channels
-- ============================================
CREATE TABLE IF NOT EXISTS notification_delivery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL,
    
    -- Delivery Details
    channel TEXT NOT NULL,                     -- in_app, email, webhook
    status TEXT NOT NULL,                      -- pending, sent, delivered, failed
    
    -- Attempt Tracking
    attempt_count INTEGER DEFAULT 1,
    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_retry_at TIMESTAMP,
    
    -- Response Details
    response_code INTEGER,                     -- HTTP status code for email/webhook
    response_body TEXT,                        -- Response from external service
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    
    FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_delivery_log_notification ON notification_delivery_log(notification_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_status ON notification_delivery_log(status);
CREATE INDEX IF NOT EXISTS idx_delivery_log_channel ON notification_delivery_log(channel);
