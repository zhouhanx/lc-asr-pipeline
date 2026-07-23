CREATE TABLE model_providers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name varchar(120) NOT NULL,
    provider_type varchar(32) NOT NULL
        CHECK (provider_type IN ('local', 'openai_compatible')),
    base_url text NOT NULL,
    model_name varchar(160) NOT NULL,
    api_key_env varchar(120),
    capabilities jsonb NOT NULL DEFAULT '["transcription"]'::jsonb,
    is_enabled boolean NOT NULL DEFAULT true,
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX model_providers_one_default_idx
    ON model_providers(tenant_id) WHERE is_default;

CREATE TABLE upload_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name varchar(160) NOT NULL,
    total_bytes bigint NOT NULL CHECK (total_bytes BETWEEN 1 AND 5368709120),
    received_bytes bigint NOT NULL DEFAULT 0
        CHECK (received_bytes >= 0 AND received_bytes <= total_bytes),
    file_count integer NOT NULL CHECK (file_count BETWEEN 1 AND 10000),
    status varchar(24) NOT NULL DEFAULT 'uploading'
        CHECK (status IN ('uploading', 'ready', 'processing', 'completed', 'failed', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE uploaded_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id uuid NOT NULL REFERENCES upload_batches(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    parent_file_id uuid REFERENCES uploaded_files(id) ON DELETE CASCADE,
    relative_path text NOT NULL,
    original_name text NOT NULL,
    media_type varchar(160),
    archive_type varchar(16)
        CHECK (archive_type IS NULL OR archive_type IN ('zip', 'tar', 'tar.gz', 'tgz')),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    chunk_size integer NOT NULL CHECK (chunk_size BETWEEN 1048576 AND 67108864),
    expected_chunks integer NOT NULL CHECK (expected_chunks >= 1),
    received_chunks integer NOT NULL DEFAULT 0
        CHECK (received_chunks >= 0 AND received_chunks <= expected_chunks),
    sha256 char(64),
    storage_path text,
    status varchar(24) NOT NULL DEFAULT 'uploading'
        CHECK (status IN ('uploading', 'uploaded', 'extracting', 'ready', 'failed', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_id, relative_path)
);

CREATE TABLE upload_chunks (
    file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    offset_bytes bigint NOT NULL CHECK (offset_bytes >= 0),
    size_bytes integer NOT NULL CHECK (size_bytes > 0),
    sha256 char(64) NOT NULL,
    storage_path text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (file_id, chunk_index)
);

CREATE TABLE transcription_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    status varchar(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
    language varchar(40),
    diarize boolean NOT NULL DEFAULT true,
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    error_code varchar(80),
    error_message text,
    queued_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, uploaded_file_id, provider_id)
);

CREATE TABLE transcripts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_id uuid NOT NULL UNIQUE REFERENCES transcription_jobs(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    language varchar(40),
    text text NOT NULL,
    duration_seconds numeric(14,3),
    raw_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transcript_segments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transcript_id uuid NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    segment_index integer NOT NULL CHECK (segment_index >= 0),
    start_seconds numeric(14,3) NOT NULL CHECK (start_seconds >= 0),
    end_seconds numeric(14,3) NOT NULL CHECK (end_seconds >= start_seconds),
    speaker varchar(80),
    text text NOT NULL,
    UNIQUE (transcript_id, segment_index)
);

CREATE INDEX model_providers_tenant_idx ON model_providers(tenant_id, is_enabled);
CREATE INDEX upload_batches_tenant_time_idx ON upload_batches(tenant_id, created_at DESC);
CREATE INDEX uploaded_files_batch_status_idx ON uploaded_files(batch_id, status);
CREATE INDEX transcription_jobs_claim_idx ON transcription_jobs(status, queued_at)
    WHERE status = 'queued';
CREATE INDEX transcription_jobs_tenant_time_idx
    ON transcription_jobs(tenant_id, queued_at DESC);
CREATE INDEX transcripts_source_idx ON transcripts(tenant_id, uploaded_file_id);

INSERT INTO model_providers (
    tenant_id, name, provider_type, base_url, model_name, api_key_env,
    capabilities, is_default
)
SELECT
    id, '本地 Qwen3-ASR 1.7B', 'local', 'http://127.0.0.1:8765',
    'qwen3-asr-1.7b-mlx-8bit', 'MLX_ASR_API_KEY',
    '["transcription", "timestamps", "diarization"]'::jsonb, true
FROM tenants;

