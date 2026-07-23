ALTER TABLE transcription_jobs
    ADD COLUMN speaker_mode varchar(16) NOT NULL DEFAULT 'single'
        CHECK (speaker_mode IN ('single', 'double', 'multiple'));

ALTER TABLE transcription_jobs
    DROP CONSTRAINT transcription_jobs_tenant_id_uploaded_file_id_provider_id_key,
    ADD CONSTRAINT transcription_jobs_source_provider_mode_key
        UNIQUE (tenant_id, uploaded_file_id, provider_id, speaker_mode);
