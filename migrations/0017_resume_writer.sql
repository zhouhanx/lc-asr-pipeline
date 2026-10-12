CREATE TABLE resume_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    source_resume_profile_id uuid
        REFERENCES resume_profiles(id) ON DELETE CASCADE,
    title varchar(300) NOT NULL,
    template_key varchar(32) NOT NULL DEFAULT 'classic'
        CHECK (template_key IN ('classic', 'sidebar', 'timeline')),
    theme_color varchar(7) NOT NULL DEFAULT '#2457d6'
        CHECK (theme_color ~ '^#[0-9A-Fa-f]{6}$'),
    content jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(content) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX resume_documents_source_key
    ON resume_documents(tenant_id, source_resume_profile_id)
    WHERE source_resume_profile_id IS NOT NULL;

CREATE INDEX resume_documents_tenant_time_idx
    ON resume_documents(tenant_id, updated_at DESC);

CREATE TABLE resume_document_photos (
    resume_document_id uuid PRIMARY KEY
        REFERENCES resume_documents(id) ON DELETE CASCADE,
    media_type varchar(32) NOT NULL
        CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
    image_bytes bytea NOT NULL
        CHECK (octet_length(image_bytes) BETWEEN 1 AND 5242880),
    updated_at timestamptz NOT NULL DEFAULT now()
);
