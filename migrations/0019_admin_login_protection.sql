ALTER TABLE platform_admins
    ADD COLUMN failed_login_attempts integer NOT NULL DEFAULT 0
        CHECK (failed_login_attempts >= 0),
    ADD COLUMN failed_login_window_started_at timestamptz,
    ADD COLUMN last_failed_login_at timestamptz,
    ADD COLUMN locked_until timestamptz;

CREATE INDEX platform_admins_locked_until_idx
    ON platform_admins(locked_until)
    WHERE locked_until IS NOT NULL;

CREATE TABLE platform_admin_login_limits (
    scope varchar(24) NOT NULL
        CHECK (scope IN ('source', 'identity_source')),
    key_hash char(64) NOT NULL,
    window_started_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    blocked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key_hash)
);

CREATE INDEX platform_admin_login_limits_cleanup_idx
    ON platform_admin_login_limits(updated_at, blocked_until);

GRANT SELECT, INSERT, UPDATE, DELETE ON platform_admin_login_limits
TO lc_asr_app_system;
