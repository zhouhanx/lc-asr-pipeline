ALTER TABLE model_providers
    ADD COLUMN model_kind varchar(16) NOT NULL DEFAULT 'speech',
    ADD COLUMN api_key_ciphertext bytea,
    ADD COLUMN configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN is_system boolean NOT NULL DEFAULT false;

ALTER TABLE model_providers
    ADD CONSTRAINT model_providers_model_kind_check
        CHECK (model_kind IN ('speech', 'text')),
    DROP CONSTRAINT model_providers_provider_type_check,
    ADD CONSTRAINT model_providers_provider_type_check
        CHECK (provider_type IN ('local', 'openai_compatible', 'stepfun', 'deepseek')),
    ADD CONSTRAINT model_providers_kind_type_check
        CHECK (
            (model_kind = 'speech' AND provider_type IN ('local', 'openai_compatible', 'stepfun'))
            OR (model_kind = 'text' AND provider_type IN ('openai_compatible', 'deepseek'))
        );

UPDATE model_providers SET is_system = true WHERE provider_type = 'local';

DROP INDEX model_providers_one_default_idx;
CREATE UNIQUE INDEX model_providers_one_default_kind_idx
    ON model_providers(tenant_id, model_kind) WHERE is_default;

ALTER TABLE transcription_jobs
    ADD COLUMN text_provider_id uuid REFERENCES model_providers(id) ON DELETE RESTRICT,
    ADD COLUMN api_key_ciphertext_snapshot bytea,
    ADD COLUMN text_provider_type_snapshot varchar(32),
    ADD COLUMN text_base_url_snapshot text,
    ADD COLUMN text_model_name_snapshot varchar(160),
    ADD COLUMN text_api_key_ciphertext_snapshot bytea,
    ADD COLUMN text_capabilities_snapshot jsonb;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_text_provider_type_check
        CHECK (
            text_provider_type_snapshot IS NULL
            OR text_provider_type_snapshot IN ('openai_compatible', 'deepseek')
        ),
    DROP CONSTRAINT transcription_jobs_source_provider_mode_key,
    ADD CONSTRAINT transcription_jobs_source_provider_pair_mode_key
        UNIQUE (tenant_id, uploaded_file_id, provider_id, text_provider_id, speaker_mode);

CREATE INDEX model_providers_tenant_kind_idx
    ON model_providers(tenant_id, model_kind, is_enabled);
