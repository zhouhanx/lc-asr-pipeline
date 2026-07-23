ALTER TABLE transcription_jobs
    DROP CONSTRAINT transcription_jobs_status_check,
    ADD COLUMN asr_result_checkpoint jsonb,
    ADD COLUMN asr_completed_at timestamptz,
    ADD COLUMN refinement_attempts integer NOT NULL DEFAULT 0
        CHECK (refinement_attempts >= 0),
    ADD CONSTRAINT transcription_jobs_status_check
        CHECK (status IN (
            'queued', 'processing', 'refining', 'completed', 'failed', 'cancelled'
        )),
    ADD CONSTRAINT transcription_jobs_asr_checkpoint_check
        CHECK (
            asr_result_checkpoint IS NULL
            OR jsonb_typeof(asr_result_checkpoint) = 'object'
        ),
    ADD CONSTRAINT transcription_jobs_asr_checkpoint_time_check
        CHECK (
            (asr_result_checkpoint IS NULL AND asr_completed_at IS NULL)
            OR (asr_result_checkpoint IS NOT NULL AND asr_completed_at IS NOT NULL)
        );

DROP INDEX transcription_jobs_claim_idx;
CREATE INDEX transcription_jobs_claim_idx
    ON transcription_jobs(status, next_attempt_at, queued_at)
    WHERE status IN ('queued', 'refining');

DROP INDEX transcription_jobs_stale_idx;
CREATE INDEX transcription_jobs_stale_idx
    ON transcription_jobs(last_heartbeat_at)
    WHERE status IN ('processing', 'refining');
