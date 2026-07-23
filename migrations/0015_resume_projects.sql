CREATE TABLE resume_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ocr_job_id uuid NOT NULL UNIQUE REFERENCES ocr_jobs(id) ON DELETE CASCADE,
    ocr_result_id uuid NOT NULL UNIQUE REFERENCES ocr_results(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    candidate_name text NOT NULL DEFAULT '未识别姓名',
    phone text,
    email text,
    current_company text,
    extraction_model_name_snapshot varchar(160) NOT NULL,
    raw_profile jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_profile) = 'object'),
    extracted_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resume_projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resume_profile_id uuid NOT NULL
        REFERENCES resume_profiles(id) ON DELETE CASCADE,
    ocr_job_id uuid NOT NULL REFERENCES ocr_jobs(id) ON DELETE CASCADE,
    uploaded_file_id uuid NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    project_index integer NOT NULL CHECK (project_index >= 0),
    project_name text NOT NULL,
    company_name text,
    role_name text,
    start_date_text varchar(40),
    end_date_text varchar(40),
    is_current boolean NOT NULL DEFAULT false,
    description text,
    responsibilities text[] NOT NULL DEFAULT '{}',
    technologies text[] NOT NULL DEFAULT '{}',
    source_excerpt text,
    raw_project jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_project) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resume_projects_profile_index_key
        UNIQUE (resume_profile_id, project_index)
);

CREATE INDEX resume_profiles_tenant_candidate_idx
    ON resume_profiles(tenant_id, candidate_name, extracted_at DESC);

CREATE INDEX resume_projects_tenant_time_idx
    ON resume_projects(tenant_id, start_date_text, end_date_text);

CREATE INDEX resume_projects_company_idx
    ON resume_projects(tenant_id, company_name)
    WHERE company_name IS NOT NULL;

CREATE INDEX resume_projects_source_idx
    ON resume_projects(tenant_id, uploaded_file_id, ocr_job_id);
