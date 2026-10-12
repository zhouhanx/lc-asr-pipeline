ALTER TABLE resume_documents
    DROP CONSTRAINT resume_documents_template_key_check;

ALTER TABLE resume_documents
    ALTER COLUMN template_key SET DEFAULT 'local-template-05';

UPDATE resume_documents
SET template_key = 'local-template-05',
    theme_color = '#465A73',
    updated_at = now()
WHERE template_key NOT IN (
    'local-template-01',
    'local-template-02',
    'local-template-03',
    'local-template-04',
    'local-template-05'
);

ALTER TABLE resume_documents
    ADD CONSTRAINT resume_documents_template_key_check
    CHECK (template_key IN (
        'local-template-01',
        'local-template-02',
        'local-template-03',
        'local-template-04',
        'local-template-05'
    ));
