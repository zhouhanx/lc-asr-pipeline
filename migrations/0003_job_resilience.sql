ALTER TABLE transcription_jobs
    ADD COLUMN provider_type_snapshot varchar(32),
    ADD COLUMN base_url_snapshot text,
    ADD COLUMN model_name_snapshot varchar(160),
    ADD COLUMN api_key_env_snapshot varchar(120),
    ADD COLUMN capabilities_snapshot jsonb,
    ADD COLUMN progress_percent smallint NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    ADD COLUMN max_attempts smallint NOT NULL DEFAULT 3
        CHECK (max_attempts BETWEEN 1 AND 10),
    ADD COLUMN next_attempt_at timestamptz,
    ADD COLUMN last_heartbeat_at timestamptz,
    ADD COLUMN cancel_requested_at timestamptz;

UPDATE transcription_jobs j
SET provider_type_snapshot = p.provider_type,
    base_url_snapshot = p.base_url,
    model_name_snapshot = p.model_name,
    api_key_env_snapshot = p.api_key_env,
    capabilities_snapshot = p.capabilities
FROM model_providers p
WHERE p.id = j.provider_id;

ALTER TABLE transcription_jobs
    ALTER COLUMN provider_type_snapshot SET NOT NULL,
    ALTER COLUMN base_url_snapshot SET NOT NULL,
    ALTER COLUMN model_name_snapshot SET NOT NULL,
    ALTER COLUMN capabilities_snapshot SET NOT NULL,
    ADD CONSTRAINT transcription_jobs_provider_type_snapshot_check
        CHECK (provider_type_snapshot IN ('local', 'openai_compatible'));

DROP INDEX transcription_jobs_claim_idx;
CREATE INDEX transcription_jobs_claim_idx
    ON transcription_jobs(status, next_attempt_at, queued_at)
    WHERE status = 'queued';

CREATE INDEX transcription_jobs_stale_idx
    ON transcription_jobs(last_heartbeat_at)
    WHERE status = 'processing';
