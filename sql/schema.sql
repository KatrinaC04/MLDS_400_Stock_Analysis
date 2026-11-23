CREATE TABLE IF NOT EXISTS
exchanges (exchange_id BIGSERIAL PRIMARY KEY,
           mic VARCHAR(12) NOT NULL UNIQUE,
           name TEXT NOT NULL,
           acronym TEXT,
           country TEXT,
           country_code VARCHAR(2),
           city TEXT,
           website TEXT,
           operating_mic VARCHAR(12),
           legal_entity_name TEXT,
           exchange_status TEXT,
           loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
    
CREATE TABLE IF NOT EXISTS tickers (
    ticker_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    item_type TEXT,
    sector TEXT,
    industry TEXT,
    cik TEXT,
    isin TEXT,
    cusip TEXT,
    ein_employer_id TEXT,
    lei TEXT,
    series_id TEXT,
    sic_code TEXT,
    sic_name TEXT,
    exchange_id BIGINT NOT NULL REFERENCES exchanges(exchange_id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eod_prices (
    eod_price_id BIGSERIAL PRIMARY KEY,
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id),
    price_date DATE NOT NULL,
    open NUMERIC(20, 6),
    high NUMERIC(20, 6),
    low NUMERIC(20, 6),
    close NUMERIC(20, 6),
    adj_open NUMERIC(20, 6),
    adj_high NUMERIC(20, 6),
    adj_low NUMERIC(20, 6),
    adj_close NUMERIC(20, 6),
    volume BIGINT,
    adj_volume BIGINT,
    split_factor NUMERIC(16, 8),
    price_currency VARCHAR(8),
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_eod_prices_ticker_date UNIQUE(ticker_id, price_date)
);

CREATE TABLE IF NOT EXISTS dividends (
    dividend_id BIGSERIAL PRIMARY KEY,
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id),
    dividend_date DATE NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    currency VARCHAR(8),
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_dividends_positive CHECK (amount > 0),
    CONSTRAINT uq_dividends_ticker_date UNIQUE(ticker_id, dividend_date)
);

CREATE INDEX IF NOT EXISTS 
    idx_tickers_exchange_id ON tickers(exchange_id);

CREATE INDEX IF NOT EXISTS
    idx_eod_prices_price_date ON eod_prices(price_date);

CREATE INDEX IF NOT EXISTS
    idx_dividends_dividend_date ON dividends(dividend_date);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_sec NUMERIC(12, 3),
    rows_loaded BIGINT,
    api_credits_used INT NOT NULL DEFAULT 0,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
