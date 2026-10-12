CREATE TABLE storage_deletion_queue (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    root_file_id uuid,
    exact_storage_path text,
    reason varchar(32) NOT NULL
        CHECK (reason IN (
            'history_delete',
            'job_delete',
            'batch_cancel',
            'expired_upload',
            'orphan_scan'
        )),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error_type varchar(160),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (root_file_id IS NOT NULL OR exact_storage_path IS NOT NULL)
);

CREATE INDEX storage_deletion_queue_pending_idx
    ON storage_deletion_queue(next_attempt_at, id)
    WHERE completed_at IS NULL;

CREATE INDEX storage_deletion_queue_tenant_idx
    ON storage_deletion_queue(tenant_id, created_at DESC);

ALTER TABLE storage_deletion_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_deletion_queue FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON storage_deletion_queue
TO lc_asr_app_runtime
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);

CREATE POLICY system_access ON storage_deletion_queue
TO lc_asr_app_system
USING (true)
WITH CHECK (true);

GRANT SELECT, INSERT ON storage_deletion_queue TO lc_asr_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON storage_deletion_queue TO lc_asr_app_system;
GRANT USAGE, SELECT ON SEQUENCE storage_deletion_queue_id_seq
TO lc_asr_app_runtime, lc_asr_app_system;
