CREATE TABLE IF NOT EXISTS vault (
    code        TEXT PRIMARY KEY,
    owner_id    BIGINT NOT NULL,
    file_id     TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('photo', 'video')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_vault_owner ON vault (owner_id);

CREATE TABLE IF NOT EXISTS group_settings (
    chat_id       BIGINT PRIMARY KEY,
    welcome_text  TEXT,
    welcome_on    BOOLEAN DEFAULT TRUE
);