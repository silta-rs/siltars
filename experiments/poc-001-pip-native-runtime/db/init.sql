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

CREATE TABLE IF NOT EXISTS public.rates (
    id BIGSERIAL PRIMARY KEY,
    rate_type TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    rate NUMERIC(18, 8) NOT NULL,
    ts_utc TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS rates_latest_pair_idx
    ON public.rates (base, quote, ts_utc DESC);

CREATE INDEX IF NOT EXISTS rates_latest_idx
    ON public.rates (ts_utc DESC);

CREATE TABLE IF NOT EXISTS public.silta_rate_sources (
    source TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    region TEXT NOT NULL,
    tier TEXT NOT NULL
);

INSERT INTO public.silta_rate_sources (source, provider, region, tier)
VALUES ('silta-poc-seed', 'Silta POC Market Data', 'local', 'alpha')
ON CONFLICT (source) DO UPDATE
SET provider = EXCLUDED.provider,
    region = EXCLUDED.region,
    tier = EXCLUDED.tier;

INSERT INTO public.rates (rate_type, asset_class, base, quote, rate, ts_utc, source)
SELECT
    'spot',
    'fiat',
    pair.base,
    pair.quote,
    pair.seed_rate + ((series.value % 1000)::numeric / 100000),
    now() - make_interval(secs => series.value),
    'silta-poc-seed'
FROM generate_series(1, 50000) AS series(value)
CROSS JOIN (
    VALUES
        ('EUR', 'USD', 1.08000000::numeric),
        ('USD', 'EUR', 0.92500000::numeric),
        ('GBP', 'USD', 1.27000000::numeric),
        ('USD', 'JPY', 146.50000000::numeric),
        ('BTC', 'USD', 65000.00000000::numeric)
) AS pair(base, quote, seed_rate)
WHERE NOT EXISTS (
    SELECT 1 FROM public.rates WHERE source = 'silta-poc-seed'
);

CREATE TABLE IF NOT EXISTS public.silta_settings (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1
);

INSERT INTO public.silta_settings (id, name, value, version)
VALUES (1, 'alpha', 'enabled', 1)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    value = EXCLUDED.value;
