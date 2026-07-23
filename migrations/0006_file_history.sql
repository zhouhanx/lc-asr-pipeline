CREATE INDEX uploaded_files_tenant_content_idx
    ON uploaded_files(tenant_id, sha256, size_bytes, created_at DESC)
    WHERE status = 'ready' AND sha256 IS NOT NULL AND archive_type IS NULL;

CREATE INDEX transcription_jobs_tenant_status_idx
    ON transcription_jobs(tenant_id, status, queued_at DESC);
