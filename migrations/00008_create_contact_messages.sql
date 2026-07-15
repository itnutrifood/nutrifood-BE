-- +goose Up
CREATE TYPE contact_message_status AS ENUM ('read', 'unread');

CREATE TABLE contact_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(150) NOT NULL,
    email varchar(320) NOT NULL,
    subject varchar(255) NOT NULL,
    message text NOT NULL,
    status contact_message_status NOT NULL DEFAULT 'unread',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT contact_messages_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT contact_messages_email_not_blank CHECK (btrim(email) <> ''),
    CONSTRAINT contact_messages_email_lowercase CHECK (email = lower(email)),
    CONSTRAINT contact_messages_subject_not_blank CHECK (btrim(subject) <> ''),
    CONSTRAINT contact_messages_message_not_blank CHECK (btrim(message) <> ''),
    CONSTRAINT contact_messages_message_max_length CHECK (char_length(message) <= 10000)
);

CREATE INDEX contact_messages_created_at_idx ON contact_messages(created_at DESC, id DESC);
CREATE INDEX contact_messages_status_created_at_idx
ON contact_messages(status, created_at DESC, id DESC);

CREATE TRIGGER contact_messages_set_updated_at
BEFORE UPDATE ON contact_messages
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS contact_messages_set_updated_at ON contact_messages;
DROP TABLE IF EXISTS contact_messages;
DROP TYPE IF EXISTS contact_message_status;
