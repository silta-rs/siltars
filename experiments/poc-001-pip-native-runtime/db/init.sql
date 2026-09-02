CREATE SCHEMA IF NOT EXISTS silta_poc;

CREATE TABLE IF NOT EXISTS silta_poc.users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO silta_poc.users (name, email)
VALUES
    ('Ada Lovelace', 'ada@example.com'),
    ('Grace Hopper', 'grace@example.com'),
    ('Katherine Johnson', 'katherine@example.com')
ON CONFLICT (email) DO NOTHING;
