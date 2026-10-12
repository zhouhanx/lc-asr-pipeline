DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lc_asr_app_runtime') THEN
        CREATE ROLE lc_asr_app_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lc_asr_app_system') THEN
        CREATE ROLE lc_asr_app_system NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE lc_asr_app_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOBYPASSRLS;
ALTER ROLE lc_asr_app_system NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOBYPASSRLS;

GRANT lc_asr_app_runtime, lc_asr_app_system TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO lc_asr_app_runtime, lc_asr_app_system;

ALTER TABLE role_permissions ADD COLUMN tenant_id uuid;
UPDATE role_permissions mapping
SET tenant_id = role.tenant_id
FROM roles role
WHERE role.id = mapping.role_id;
ALTER TABLE role_permissions ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE membership_roles ADD COLUMN tenant_id uuid;
UPDATE membership_roles mapping
SET tenant_id = membership.tenant_id
FROM memberships membership
WHERE membership.id = mapping.membership_id;
ALTER TABLE membership_roles ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE upload_chunks ADD COLUMN tenant_id uuid;
UPDATE upload_chunks chunk
SET tenant_id = uploaded.tenant_id
FROM uploaded_files uploaded
WHERE uploaded.id = chunk.file_id;
ALTER TABLE upload_chunks ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE transcript_segments ADD COLUMN tenant_id uuid;
UPDATE transcript_segments segment
SET tenant_id = transcript.tenant_id
FROM transcripts transcript
WHERE transcript.id = segment.transcript_id;
ALTER TABLE transcript_segments ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE resume_document_photos ADD COLUMN tenant_id uuid;
UPDATE resume_document_photos photo
SET tenant_id = document.tenant_id
FROM resume_documents document
WHERE document.id = photo.resume_document_id;
ALTER TABLE resume_document_photos ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE roles ADD CONSTRAINT roles_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE memberships ADD CONSTRAINT memberships_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE uploaded_files ADD CONSTRAINT uploaded_files_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE transcripts ADD CONSTRAINT transcripts_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE resume_documents ADD CONSTRAINT resume_documents_id_tenant_key
    UNIQUE (id, tenant_id);

ALTER TABLE role_permissions
    ADD CONSTRAINT role_permissions_role_tenant_fk
    FOREIGN KEY (role_id, tenant_id) REFERENCES roles(id, tenant_id) ON DELETE CASCADE;
ALTER TABLE membership_roles
    ADD CONSTRAINT membership_roles_membership_tenant_fk
    FOREIGN KEY (membership_id, tenant_id)
    REFERENCES memberships(id, tenant_id) ON DELETE CASCADE;
ALTER TABLE membership_roles
    ADD CONSTRAINT membership_roles_role_tenant_fk
    FOREIGN KEY (role_id, tenant_id) REFERENCES roles(id, tenant_id) ON DELETE CASCADE;
ALTER TABLE upload_chunks
    ADD CONSTRAINT upload_chunks_file_tenant_fk
    FOREIGN KEY (file_id, tenant_id)
    REFERENCES uploaded_files(id, tenant_id) ON DELETE CASCADE;
ALTER TABLE transcript_segments
    ADD CONSTRAINT transcript_segments_transcript_tenant_fk
    FOREIGN KEY (transcript_id, tenant_id)
    REFERENCES transcripts(id, tenant_id) ON DELETE CASCADE;
ALTER TABLE resume_document_photos
    ADD CONSTRAINT resume_document_photos_document_tenant_fk
    FOREIGN KEY (resume_document_id, tenant_id)
    REFERENCES resume_documents(id, tenant_id) ON DELETE CASCADE;

CREATE INDEX role_permissions_tenant_idx ON role_permissions(tenant_id);
CREATE INDEX membership_roles_tenant_idx ON membership_roles(tenant_id);
CREATE INDEX upload_chunks_tenant_idx ON upload_chunks(tenant_id);
CREATE INDEX transcript_segments_tenant_idx ON transcript_segments(tenant_id);
CREATE INDEX resume_document_photos_tenant_idx ON resume_document_photos(tenant_id);

GRANT SELECT ON tenants, users, permissions TO lc_asr_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    memberships,
    roles,
    role_permissions,
    membership_roles,
    refresh_sessions,
    audit_events,
    model_providers,
    upload_batches,
    uploaded_files,
    upload_chunks,
    transcription_jobs,
    transcripts,
    transcript_segments,
    ocr_jobs,
    ocr_results,
    resume_profiles,
    resume_projects,
    resume_documents,
    resume_document_photos
TO lc_asr_app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
TO lc_asr_app_system;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
TO lc_asr_app_runtime, lc_asr_app_system;

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'memberships',
        'roles',
        'role_permissions',
        'membership_roles',
        'refresh_sessions',
        'audit_events',
        'model_providers',
        'upload_batches',
        'uploaded_files',
        'upload_chunks',
        'transcription_jobs',
        'transcripts',
        'transcript_segments',
        'ocr_jobs',
        'ocr_results',
        'resume_profiles',
        'resume_projects',
        'resume_documents',
        'resume_document_photos'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I TO lc_asr_app_runtime '
            'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
            'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)',
            table_name
        );
        EXECUTE format(
            'CREATE POLICY system_access ON %I TO lc_asr_app_system '
            'USING (true) WITH CHECK (true)',
            table_name
        );
    END LOOP;
END
$$;
