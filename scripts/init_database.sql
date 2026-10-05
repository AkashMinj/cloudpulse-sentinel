-- CloudPulse Sentinel Database Schema
-- This script initializes the complete database schema

-- Create system_metrics table if not exists
CREATE TABLE IF NOT EXISTS system_metrics (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    cpu_usage_percent DECIMAL(5, 2) NOT NULL,
    cpu_count INTEGER NOT NULL,
    memory_usage_percent DECIMAL(5, 2) NOT NULL,
    memory_total_gb DECIMAL(10, 2) NOT NULL,
    memory_available_gb DECIMAL(10, 2) NOT NULL,
    disk_usage_percent DECIMAL(5, 2) NOT NULL,
    disk_total_gb DECIMAL(10, 2) NOT NULL,
    disk_free_gb DECIMAL(10, 2) NOT NULL,
    latency_ms DECIMAL(10, 2),
    error_rate_percent DECIMAL(5, 2),
    request_rate DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Upgrade existing system_metrics tables with telemetry columns
ALTER TABLE system_metrics
    ADD COLUMN IF NOT EXISTS latency_ms DECIMAL(10, 2);

ALTER TABLE system_metrics
    ADD COLUMN IF NOT EXISTS error_rate_percent DECIMAL(5, 2);

ALTER TABLE system_metrics
    ADD COLUMN IF NOT EXISTS request_rate DECIMAL(10, 4);


CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_system_metrics_instance_id ON system_metrics(instance_id);

-- Create incidents table if not exists
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    metric_id INTEGER REFERENCES system_metrics(id),
    incident_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    metric_value DECIMAL(10, 2) NOT NULL,
    threshold_value DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'open',
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incidents_instance_id ON incidents(instance_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_detected_at ON incidents(detected_at DESC);

-- Create incident_events table for Incident Replay (NEW)
CREATE TABLE IF NOT EXISTS incident_events (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_message TEXT NOT NULL,
    metadata JSONB,
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_id ON incident_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_timestamp ON incident_events(event_timestamp);

-- Create anomaly_detections table for ML integration (NEW)
CREATE TABLE IF NOT EXISTS anomaly_detections (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    metric_id INTEGER REFERENCES system_metrics(id),
    is_anomaly BOOLEAN NOT NULL,
    anomaly_score DECIMAL(10, 6) NOT NULL,
    model_version VARCHAR(50),
    features JSONB,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_anomaly_detections_instance_id ON anomaly_detections(instance_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_detections_detected_at ON anomaly_detections(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_detections_is_anomaly ON anomaly_detections(is_anomaly);

-- Create users table for authentication (NEW)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'read_only',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create api_tokens table for token-based authentication (NEW)
CREATE TABLE IF NOT EXISTS api_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_token_hash ON api_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id);

-- Insert default admin user (password: admin123)
-- This is for demo purposes only - change in production!
INSERT INTO users (username, email, hashed_password, full_name, role)
VALUES (
    'admin',
    'admin@cloudpulse.local',
    '$2b$12$zH5O0c/JrYR/XcBFIQdaoO0yPuh7RW2hzbHTjbc9AtVLFMkwd.382',
    'Administrator',
    'admin'
)
ON CONFLICT (username) DO NOTHING;

-- Insert demo analyst user (password: analyst123)
INSERT INTO users (username, email, hashed_password, full_name, role)
VALUES (
    'analyst',
    'analyst@cloudpulse.local',
    '$2b$12$kcYW93Pd.VMn.BeFtoEd8.iyssS4aiFl1egbAB3w5uM/A1bTJlsEK',
    'Operations Analyst',
    'analyst'
)
ON CONFLICT (username) DO NOTHING;

-- Success message
SELECT 'CloudPulse Sentinel database schema initialized successfully!' AS status;
