ALTER TABLE upload_batches
    ADD COLUMN expires_at timestamptz NOT NULL DEFAULT (now() + interval '7 days');

CREATE INDEX upload_batches_expiry_idx
    ON upload_batches(expires_at)
    WHERE status IN ('uploading', 'cancelled', 'failed');
