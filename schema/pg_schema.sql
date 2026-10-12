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
    failed_login_attempts integer NOT NULL DEFAULT 0
        CHECK (failed_login_attempts >= 0),
    failed_login_window_started_at timestamptz,
    last_failed_login_at timestamptz,
    locked_until timestamptz,
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
    UNIQUE (id, tenant_id),
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code varchar(64) NOT NULL,
    name varchar(120) NOT NULL,
    is_system boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, tenant_id),
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
    tenant_id uuid NOT NULL,
    FOREIGN KEY (role_id, tenant_id)
        REFERENCES roles(id, tenant_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE membership_roles (
    membership_id uuid NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    FOREIGN KEY (membership_id, tenant_id)
        REFERENCES memberships(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (role_id, tenant_id)
        REFERENCES roles(id, tenant_id) ON DELETE CASCADE,
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
        CHECK (provider_type IN ('local', 'openai_compatible', 'stepfun', 'deepseek', 'paddleocr')),
    model_kind varchar(16) NOT NULL DEFAULT 'speech'
        CHECK (model_kind IN ('speech', 'text', 'ocr')),
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
        OR (model_kind = 'ocr' AND provider_type = 'paddleocr')
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
    file_kind varchar(16) NOT NULL DEFAULT 'audio'
        CHECK (file_kind IN ('audio', 'image', 'pdf')),
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
    UNIQUE (id, tenant_id),
    UNIQUE (batch_id, relative_path)
);

CREATE TABLE upload_chunks (
    file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    offset_bytes bigint NOT NULL CHECK (offset_bytes >= 0),
    size_bytes integer NOT NULL CHECK (size_bytes > 0),
    sha256 char(64) NOT NULL,
    storage_path text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (file_id, tenant_id)
        REFERENCES uploaded_files(id, tenant_id) ON DELETE CASCADE,
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
        CHECK (status IN (
            'queued', 'processing', 'refining', 'completed', 'failed', 'cancelled'
        )),
    visibility varchar(16) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'public')),
    language varchar(40),
    diarize boolean NOT NULL DEFAULT true,
    speaker_mode varchar(16) NOT NULL DEFAULT 'single'
        CHECK (speaker_mode IN ('single', 'double', 'multiple')),
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    refinement_attempts integer NOT NULL DEFAULT 0 CHECK (refinement_attempts >= 0),
    max_attempts smallint NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    progress_percent smallint NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    next_attempt_at timestamptz,
    last_heartbeat_at timestamptz,
    cancel_requested_at timestamptz,
    error_code varchar(80),
    error_message text,
    queued_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    asr_result_checkpoint jsonb,
    asr_completed_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT transcription_jobs_asr_checkpoint_check
        CHECK (
            asr_result_checkpoint IS NULL
            OR jsonb_typeof(asr_result_checkpoint) = 'object'
        ),
    CONSTRAINT transcription_jobs_asr_checkpoint_time_check
        CHECK (
            (asr_result_checkpoint IS NULL AND asr_completed_at IS NULL)
            OR (asr_result_checkpoint IS NOT NULL AND asr_completed_at IS NOT NULL)
        ),
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
CREATE INDEX uploaded_files_tenant_kind_time_idx
    ON uploaded_files(tenant_id, file_kind, created_at DESC)
    WHERE status = 'ready' AND archive_type IS NULL;

CREATE TABLE ocr_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    ocr_provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    text_provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    ocr_provider_type_snapshot varchar(32) NOT NULL
        CHECK (ocr_provider_type_snapshot = 'paddleocr'),
    ocr_base_url_snapshot text NOT NULL,
    ocr_model_name_snapshot varchar(160) NOT NULL,
    ocr_api_key_env_snapshot varchar(120),
    ocr_api_key_ciphertext_snapshot bytea,
    ocr_capabilities_snapshot jsonb NOT NULL,
    text_provider_type_snapshot varchar(32) NOT NULL
        CHECK (text_provider_type_snapshot IN ('openai_compatible', 'deepseek')),
    text_base_url_snapshot text NOT NULL,
    text_model_name_snapshot varchar(160) NOT NULL,
    text_api_key_ciphertext_snapshot bytea NOT NULL,
    text_capabilities_snapshot jsonb NOT NULL,
    document_kind varchar(16) NOT NULL
        CHECK (document_kind IN ('image', 'pdf')),
    file_attribute varchar(16) NOT NULL DEFAULT 'document'
        CHECK (file_attribute IN ('resume', 'document')),
    status varchar(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued', 'processing', 'refining', 'completed', 'failed', 'cancelled'
        )),
    progress_percent smallint NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    refinement_attempts integer NOT NULL DEFAULT 0
        CHECK (refinement_attempts >= 0),
    max_attempts smallint NOT NULL DEFAULT 3
        CHECK (max_attempts BETWEEN 1 AND 10),
    next_attempt_at timestamptz,
    last_heartbeat_at timestamptz,
    cancel_requested_at timestamptz,
    error_code varchar(80),
    error_message text,
    provider_job_id text,
    ocr_result_checkpoint jsonb,
    queued_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    ocr_completed_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ocr_jobs_checkpoint_check
        CHECK (
            ocr_result_checkpoint IS NULL
            OR jsonb_typeof(ocr_result_checkpoint) = 'object'
        ),
    CONSTRAINT ocr_jobs_checkpoint_time_check
        CHECK (
            (ocr_result_checkpoint IS NULL AND ocr_completed_at IS NULL)
            OR (ocr_result_checkpoint IS NOT NULL AND ocr_completed_at IS NOT NULL)
        ),
    CONSTRAINT ocr_jobs_source_provider_profile_key
        UNIQUE (
            tenant_id, uploaded_file_id, ocr_provider_id, text_provider_id,
            file_attribute
        )
);

CREATE TABLE ocr_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_id uuid NOT NULL UNIQUE REFERENCES ocr_jobs(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    ocr_provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    text_provider_id uuid NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
    markdown_text text NOT NULL,
    page_count integer NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    raw_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resume_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ocr_job_id uuid NOT NULL UNIQUE REFERENCES ocr_jobs(id) ON DELETE CASCADE,
    ocr_result_id uuid NOT NULL UNIQUE REFERENCES ocr_results(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    candidate_name text NOT NULL DEFAULT '未识别姓名',
    phone text,
    email text,
    current_company text,
    extraction_model_name_snapshot varchar(160) NOT NULL,
    raw_profile jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_profile) = 'object'),
    extracted_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resume_projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resume_profile_id uuid NOT NULL
        REFERENCES resume_profiles(id) ON DELETE CASCADE,
    ocr_job_id uuid NOT NULL REFERENCES ocr_jobs(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    project_index integer NOT NULL CHECK (project_index >= 0),
    project_name text NOT NULL,
    company_name text,
    role_name text,
    start_date_text varchar(40),
    end_date_text varchar(40),
    is_current boolean NOT NULL DEFAULT false,
    description text,
    responsibilities text[] NOT NULL DEFAULT '{}',
    technologies text[] NOT NULL DEFAULT '{}',
    project_background text,
    project_responsibilities text[] NOT NULL DEFAULT '{}',
    project_outcomes text[] NOT NULL DEFAULT '{}',
    architecture_score smallint
        CHECK (architecture_score BETWEEN 1 AND 10),
    architecture_reason text,
    credibility_score smallint
        CHECK (credibility_score BETWEEN 1 AND 10),
    credibility_reason text,
    embellishment_risk_score smallint
        CHECK (embellishment_risk_score BETWEEN 1 AND 10),
    embellishment_risk_reason text,
    overall_score numeric(3,1)
        GENERATED ALWAYS AS (
            round(
                (
                    architecture_score
                    + credibility_score
                    + (11 - embellishment_risk_score)
                )::numeric / 3,
                1
            )
        ) STORED,
    source_excerpt text,
    raw_project jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_project) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resume_projects_profile_index_key
        UNIQUE (resume_profile_id, project_index)
);

CREATE TABLE resume_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    source_resume_profile_id uuid
        REFERENCES resume_profiles(id) ON DELETE CASCADE,
    title varchar(300) NOT NULL,
    template_key varchar(32) NOT NULL DEFAULT 'local-template-05'
        CHECK (template_key IN (
            'local-template-01', 'local-template-02', 'local-template-03',
            'local-template-04', 'local-template-05'
        )),
    theme_color varchar(7) NOT NULL DEFAULT '#465A73'
        CHECK (theme_color ~ '^#[0-9A-Fa-f]{6}$'),
    content jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(content) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, tenant_id)
);

CREATE TABLE resume_document_photos (
    resume_document_id uuid PRIMARY KEY
        REFERENCES resume_documents(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    media_type varchar(32) NOT NULL
        CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
    image_bytes bytea NOT NULL
        CHECK (octet_length(image_bytes) BETWEEN 1 AND 5242880),
    FOREIGN KEY (resume_document_id, tenant_id)
        REFERENCES resume_documents(id, tenant_id) ON DELETE CASCADE,
    updated_at timestamptz NOT NULL DEFAULT now()
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
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, tenant_id)
);

CREATE TABLE transcript_segments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transcript_id uuid NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    segment_index integer NOT NULL CHECK (segment_index >= 0),
    start_seconds numeric(14,3) NOT NULL CHECK (start_seconds >= 0),
    end_seconds numeric(14,3) NOT NULL CHECK (end_seconds >= start_seconds),
    speaker varchar(80),
    text text NOT NULL,
    FOREIGN KEY (transcript_id, tenant_id)
        REFERENCES transcripts(id, tenant_id) ON DELETE CASCADE,
    UNIQUE (transcript_id, segment_index)
);

CREATE TABLE platform_admin_login_limits (
    scope varchar(24) NOT NULL
        CHECK (scope IN ('source', 'identity_source')),
    key_hash char(64) NOT NULL,
    window_started_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    blocked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key_hash)
);

CREATE TABLE storage_deletion_queue (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    root_file_id uuid,
    exact_storage_path text,
    reason varchar(32) NOT NULL
        CHECK (reason IN (
            'history_delete', 'job_delete', 'batch_cancel',
            'expired_upload', 'orphan_scan'
        )),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error_type varchar(160),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (root_file_id IS NOT NULL OR exact_storage_path IS NOT NULL)
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
    WHERE status IN ('queued', 'refining');
CREATE INDEX transcription_jobs_stale_idx ON transcription_jobs(last_heartbeat_at)
    WHERE status IN ('processing', 'refining');
CREATE INDEX transcription_jobs_tenant_time_idx
    ON transcription_jobs(tenant_id, queued_at DESC);
CREATE INDEX transcripts_source_idx ON transcripts(tenant_id, uploaded_file_id);
CREATE INDEX ocr_jobs_claim_idx
    ON ocr_jobs(status, next_attempt_at, queued_at)
    WHERE status IN ('queued', 'refining');
CREATE INDEX ocr_jobs_stale_idx ON ocr_jobs(last_heartbeat_at)
    WHERE status IN ('processing', 'refining');
CREATE INDEX ocr_jobs_tenant_time_idx ON ocr_jobs(tenant_id, queued_at DESC);
CREATE INDEX ocr_results_source_idx ON ocr_results(tenant_id, uploaded_file_id);
CREATE INDEX resume_profiles_tenant_candidate_idx
    ON resume_profiles(tenant_id, candidate_name, extracted_at DESC);
CREATE INDEX resume_projects_tenant_time_idx
    ON resume_projects(tenant_id, start_date_text, end_date_text);
CREATE INDEX resume_projects_company_idx
    ON resume_projects(tenant_id, company_name)
    WHERE company_name IS NOT NULL;
CREATE INDEX resume_projects_source_idx
    ON resume_projects(tenant_id, uploaded_file_id, ocr_job_id);
CREATE UNIQUE INDEX resume_documents_source_key
    ON resume_documents(tenant_id, source_resume_profile_id)
    WHERE source_resume_profile_id IS NOT NULL;
CREATE INDEX resume_documents_tenant_time_idx
    ON resume_documents(tenant_id, updated_at DESC);
CREATE INDEX platform_admins_locked_until_idx
    ON platform_admins(locked_until) WHERE locked_until IS NOT NULL;
CREATE INDEX platform_admin_login_limits_cleanup_idx
    ON platform_admin_login_limits(updated_at, blocked_until);
CREATE INDEX role_permissions_tenant_idx ON role_permissions(tenant_id);
CREATE INDEX membership_roles_tenant_idx ON membership_roles(tenant_id);
CREATE INDEX upload_chunks_tenant_idx ON upload_chunks(tenant_id);
CREATE INDEX transcript_segments_tenant_idx ON transcript_segments(tenant_id);
CREATE INDEX resume_document_photos_tenant_idx
    ON resume_document_photos(tenant_id);
CREATE INDEX storage_deletion_queue_pending_idx
    ON storage_deletion_queue(next_attempt_at, id)
    WHERE completed_at IS NULL;
CREATE INDEX storage_deletion_queue_tenant_idx
    ON storage_deletion_queue(tenant_id, created_at DESC);

-- The runtime role is deliberately unable to bypass RLS. Application transactions
-- use SET LOCAL ROLE plus a transaction-local app.tenant_id; background/platform
-- transactions explicitly use the system role.
CREATE ROLE lc_asr_app_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOBYPASSRLS;
CREATE ROLE lc_asr_app_system NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOBYPASSRLS;

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'memberships', 'roles', 'role_permissions', 'membership_roles',
        'refresh_sessions', 'audit_events', 'model_providers',
        'upload_batches', 'uploaded_files', 'upload_chunks',
        'transcription_jobs', 'transcripts', 'transcript_segments',
        'ocr_jobs', 'ocr_results', 'resume_profiles', 'resume_projects',
        'resume_documents', 'resume_document_photos',
        'storage_deletion_queue'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I TO lc_asr_app_runtime '
            'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
            'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
        EXECUTE format(
            'CREATE POLICY system_access ON %I TO lc_asr_app_system '
            'USING (true) WITH CHECK (true)',
            table_name
        );
    END LOOP;
END
$$;
