-- PostgreSQL 17 schema snapshot for lc-asr-pipeline.
-- Executable changes belong in migrations/; keep this readable snapshot synchronized.

CREATE TABLE schema_migrations (
    version text PRIMARY KEY,
    checksum char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug varchar(63) NOT NULL UNIQUE,
    name varchar(160) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'deleted')),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tenants_slug_lowercase CHECK (slug = lower(slug)),
    CONSTRAINT tenants_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$')
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email varchar(320) NOT NULL,
    normalized_email varchar(320) NOT NULL UNIQUE,
    display_name varchar(120) NOT NULL,
    password_hash text NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    must_change_password boolean NOT NULL DEFAULT false,
    email_verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform_admins (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username varchar(64) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    must_change_password boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT platform_admins_username_lowercase CHECK (username = lower(username)),
    CONSTRAINT platform_admins_username_format CHECK (username ~ '^[a-z][a-z0-9_-]{2,63}$')
);

CREATE TABLE memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status varchar(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'invited', 'suspended')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code varchar(64) NOT NULL,
    name varchar(120) NOT NULL,
    is_system boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);

CREATE TABLE permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(100) NOT NULL UNIQUE,
    description varchar(240) NOT NULL
);

CREATE TABLE role_permissions (
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE membership_roles (
    membership_id uuid NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (membership_id, role_id)
);

CREATE TABLE refresh_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    membership_id uuid NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    token_hash char(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    replaced_by_id uuid REFERENCES refresh_sessions(id) ON DELETE SET NULL,
    user_agent varchar(512),
    ip_address inet,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE email_verification_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash char(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid REFERENCES tenants(id) ON DELETE SET NULL,
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    event_type varchar(100) NOT NULL,
    target_type varchar(100),
    target_id varchar(160),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX memberships_user_id_idx ON memberships(user_id);
CREATE INDEX platform_admins_status_idx ON platform_admins(status);
CREATE INDEX users_status_idx ON users(status);
CREATE INDEX roles_tenant_id_idx ON roles(tenant_id);
CREATE INDEX refresh_sessions_lookup_idx ON refresh_sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;
CREATE INDEX audit_events_tenant_time_idx ON audit_events(tenant_id, created_at DESC);

CREATE TABLE model_providers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name varchar(120) NOT NULL,
    provider_type varchar(32) NOT NULL
        CHECK (provider_type IN ('local', 'openai_compatible', 'stepfun', 'deepseek')),
    model_kind varchar(16) NOT NULL DEFAULT 'speech'
        CHECK (model_kind IN ('speech', 'text')),
    base_url text NOT NULL,
    model_name varchar(160) NOT NULL,
    api_key_env varchar(120),
    api_key_ciphertext bytea,
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_system boolean NOT NULL DEFAULT false,
    capabilities jsonb NOT NULL DEFAULT '["transcription"]'::jsonb,
    is_enabled boolean NOT NULL DEFAULT true,
    is_default boolean NOT NULL DEFAULT false,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (model_kind = 'speech' AND provider_type IN ('local', 'openai_compatible', 'stepfun'))
        OR (model_kind = 'text' AND provider_type IN ('openai_compatible', 'deepseek'))
    )
);

CREATE UNIQUE INDEX model_providers_one_default_kind_idx
    ON model_providers(tenant_id, model_kind)
    WHERE is_default AND deleted_at IS NULL;
CREATE UNIQUE INDEX model_providers_active_tenant_name_idx
    ON model_providers(tenant_id, name)
    WHERE deleted_at IS NULL;

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
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '7 days'),
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
    provider_type_snapshot varchar(32) NOT NULL
        CHECK (provider_type_snapshot IN ('local', 'openai_compatible', 'stepfun')),
    base_url_snapshot text NOT NULL,
    model_name_snapshot varchar(160) NOT NULL,
    api_key_env_snapshot varchar(120),
    api_key_ciphertext_snapshot bytea,
    capabilities_snapshot jsonb NOT NULL,
    text_provider_id uuid REFERENCES model_providers(id) ON DELETE RESTRICT,
    text_provider_type_snapshot varchar(32)
        CHECK (text_provider_type_snapshot IS NULL OR text_provider_type_snapshot IN ('openai_compatible', 'deepseek')),
    text_base_url_snapshot text,
    text_model_name_snapshot varchar(160),
    text_api_key_ciphertext_snapshot bytea,
    text_capabilities_snapshot jsonb,
    status varchar(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
    visibility varchar(16) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'public')),
    language varchar(40),
    diarize boolean NOT NULL DEFAULT true,
    speaker_mode varchar(16) NOT NULL DEFAULT 'single'
        CHECK (speaker_mode IN ('single', 'double', 'multiple')),
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts smallint NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    progress_percent smallint NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    next_attempt_at timestamptz,
    last_heartbeat_at timestamptz,
    cancel_requested_at timestamptz,
    error_code varchar(80),
    error_message text,
    queued_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT transcription_jobs_source_provider_pair_mode_key
        UNIQUE (tenant_id, uploaded_file_id, provider_id, text_provider_id, speaker_mode)
);

CREATE INDEX uploaded_files_tenant_content_idx
    ON uploaded_files(tenant_id, sha256, size_bytes, created_at DESC)
    WHERE status = 'ready' AND sha256 IS NOT NULL AND archive_type IS NULL;

CREATE INDEX transcription_jobs_tenant_status_idx
    ON transcription_jobs(tenant_id, status, queued_at DESC);
CREATE INDEX transcription_jobs_public_time_idx
    ON transcription_jobs(queued_at DESC)
    WHERE visibility = 'public';
CREATE INDEX uploaded_files_admin_recordings_idx
    ON uploaded_files(tenant_id, created_at DESC)
    WHERE status = 'ready' AND archive_type IS NULL;

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
CREATE INDEX model_providers_tenant_kind_idx
    ON model_providers(tenant_id, model_kind, is_enabled);
CREATE INDEX upload_batches_tenant_time_idx ON upload_batches(tenant_id, created_at DESC);
CREATE INDEX upload_batches_expiry_idx ON upload_batches(expires_at)
    WHERE status IN ('uploading', 'cancelled', 'failed');
CREATE INDEX uploaded_files_batch_status_idx ON uploaded_files(batch_id, status);
CREATE INDEX transcription_jobs_claim_idx
    ON transcription_jobs(status, next_attempt_at, queued_at)
    WHERE status = 'queued';
CREATE INDEX transcription_jobs_stale_idx ON transcription_jobs(last_heartbeat_at)
    WHERE status = 'processing';
CREATE INDEX transcription_jobs_tenant_time_idx
    ON transcription_jobs(tenant_id, queued_at DESC);
CREATE INDEX transcripts_source_idx ON transcripts(tenant_id, uploaded_file_id);
