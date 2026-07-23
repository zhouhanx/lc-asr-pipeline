ALTER TABLE model_providers
    DROP CONSTRAINT model_providers_model_kind_check,
    DROP CONSTRAINT model_providers_provider_type_check,
    DROP CONSTRAINT model_providers_kind_type_check,
    ADD CONSTRAINT model_providers_model_kind_check
        CHECK (model_kind IN ('speech', 'text', 'ocr')),
    ADD CONSTRAINT model_providers_provider_type_check
        CHECK (
            provider_type IN (
                'local', 'openai_compatible', 'stepfun', 'deepseek', 'paddleocr'
            )
        ),
    ADD CONSTRAINT model_providers_kind_type_check
        CHECK (
            (model_kind = 'speech'
                AND provider_type IN ('local', 'openai_compatible', 'stepfun'))
            OR (model_kind = 'text'
                AND provider_type IN ('openai_compatible', 'deepseek'))
            OR (model_kind = 'ocr' AND provider_type = 'paddleocr')
        );

ALTER TABLE uploaded_files
    ADD COLUMN file_kind varchar(16) NOT NULL DEFAULT 'audio',
    ADD CONSTRAINT uploaded_files_file_kind_check
        CHECK (file_kind IN ('audio', 'image', 'pdf'));

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
    status varchar(24) NOT NULL DEFAULT 'queued'
        CHECK (
            status IN (
                'queued', 'processing', 'refining', 'completed', 'failed', 'cancelled'
            )
        ),
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
    CONSTRAINT ocr_jobs_source_provider_pair_key
        UNIQUE (
            tenant_id, uploaded_file_id, ocr_provider_id, text_provider_id
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

CREATE INDEX ocr_jobs_claim_idx
    ON ocr_jobs(status, next_attempt_at, queued_at)
    WHERE status IN ('queued', 'refining');

CREATE INDEX ocr_jobs_stale_idx
    ON ocr_jobs(last_heartbeat_at)
    WHERE status IN ('processing', 'refining');

CREATE INDEX ocr_jobs_tenant_time_idx
    ON ocr_jobs(tenant_id, queued_at DESC);

CREATE INDEX ocr_results_source_idx
    ON ocr_results(tenant_id, uploaded_file_id);

INSERT INTO model_providers (
    tenant_id, name, provider_type, model_kind, base_url, model_name,
    api_key_env, capabilities, is_default, is_system
)
SELECT
    tenant.id,
    'PaddleOCR 文档识别',
    'paddleocr',
    'ocr',
    'https://paddleocr.aistudio-app.com/api/v2/ocr',
    'PaddleOCR-VL-1.6',
    'PADDLE_API',
    '["ocr", "document_parsing", "markdown", "image", "pdf"]'::jsonb,
    true,
    true
FROM tenants tenant
WHERE NOT EXISTS (
    SELECT 1
    FROM model_providers provider
    WHERE provider.tenant_id = tenant.id
      AND provider.model_kind = 'ocr'
      AND provider.deleted_at IS NULL
);
