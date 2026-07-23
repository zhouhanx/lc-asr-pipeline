ALTER TABLE model_providers
    DROP CONSTRAINT model_providers_provider_type_check,
    ADD CONSTRAINT model_providers_provider_type_check
        CHECK (provider_type IN ('local', 'openai_compatible', 'stepfun'));

ALTER TABLE transcription_jobs
    DROP CONSTRAINT transcription_jobs_provider_type_snapshot_check,
    ADD CONSTRAINT transcription_jobs_provider_type_snapshot_check
        CHECK (provider_type_snapshot IN ('local', 'openai_compatible', 'stepfun'));
