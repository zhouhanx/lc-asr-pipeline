ALTER TABLE ocr_jobs
    ADD COLUMN file_attribute varchar(16) NOT NULL DEFAULT 'document',
    ADD CONSTRAINT ocr_jobs_file_attribute_check
        CHECK (file_attribute IN ('resume', 'document'));

ALTER TABLE ocr_jobs
    DROP CONSTRAINT ocr_jobs_source_provider_pair_key,
    ADD CONSTRAINT ocr_jobs_source_provider_profile_key
        UNIQUE (
            tenant_id, uploaded_file_id, ocr_provider_id, text_provider_id,
            file_attribute
        );
