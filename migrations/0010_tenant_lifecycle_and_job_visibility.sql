ALTER TABLE tenants
    DROP CONSTRAINT tenants_status_check,
    ADD CONSTRAINT tenants_status_check
        CHECK (status IN ('active', 'suspended', 'deleted')),
    ADD COLUMN deleted_at timestamptz;

ALTER TABLE transcription_jobs
    ADD COLUMN visibility varchar(16) NOT NULL DEFAULT 'private',
    ADD CONSTRAINT transcription_jobs_visibility_check
        CHECK (visibility IN ('private', 'public'));

CREATE INDEX transcription_jobs_public_time_idx
    ON transcription_jobs(queued_at DESC)
    WHERE visibility = 'public';

CREATE INDEX uploaded_files_admin_recordings_idx
    ON uploaded_files(tenant_id, created_at DESC)
    WHERE status = 'ready' AND archive_type IS NULL;
