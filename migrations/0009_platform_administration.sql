ALTER TABLE users
    ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;

CREATE TABLE platform_admins (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username varchar(64) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    must_change_password boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT platform_admins_username_lowercase CHECK (username = lower(username)),
    CONSTRAINT platform_admins_username_format CHECK (username ~ '^[a-z][a-z0-9_-]{2,63}$')
);

INSERT INTO platform_admins (username, password_hash, must_change_password)
VALUES (
    'root',
    '$argon2id$v=19$m=65536,t=3,p=4$R9mAlIKZ7xsqE2rNNYc73Q$W+RJasmQlwOSyNtpBOzGcuJbSPh3Bbk9fFnAs/+otkA',
    true
)
ON CONFLICT (username) DO NOTHING;

CREATE INDEX platform_admins_status_idx ON platform_admins(status);
CREATE INDEX users_status_idx ON users(status);
