ALTER TABLE model_providers
    ADD COLUMN deleted_at timestamptz;

ALTER TABLE model_providers
    DROP CONSTRAINT model_providers_tenant_id_name_key;

CREATE UNIQUE INDEX model_providers_active_tenant_name_idx
    ON model_providers(tenant_id, name)
    WHERE deleted_at IS NULL;

DROP INDEX model_providers_one_default_kind_idx;

CREATE UNIQUE INDEX model_providers_one_default_kind_idx
    ON model_providers(tenant_id, model_kind)
    WHERE is_default AND deleted_at IS NULL;
