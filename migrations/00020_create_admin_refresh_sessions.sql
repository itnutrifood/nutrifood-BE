-- +goose Up
CREATE TABLE admin_refresh_sessions (
    jti_hash CHAR(64) PRIMARY KEY,
    admin_id UUID NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    family_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT admin_refresh_sessions_jti_hash_hex CHECK (jti_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT admin_refresh_sessions_expiry_valid CHECK (expires_at > created_at)
);

CREATE INDEX admin_refresh_sessions_admin_family_idx
ON admin_refresh_sessions (admin_id, family_id);

CREATE INDEX admin_refresh_sessions_expiry_idx
ON admin_refresh_sessions (expires_at)
WHERE consumed_at IS NULL AND revoked_at IS NULL;

-- +goose Down
DROP TABLE IF EXISTS admin_refresh_sessions;
