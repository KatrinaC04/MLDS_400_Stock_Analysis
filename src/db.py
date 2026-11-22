"""
Database utilities for the stock analysis pipeline.

This module connects to PostgreSQL and loads the raw
Marketstack JSON files into the exchanges, tickers, eod_prices,
and dividends tables.
"""

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Load database settings from the local .env file.
load_dotenv()

# Directory containing the raw EOD and ticker JSON files.
RAW_DATA_DIR = Path("data/raw")

# 1. Database connection
def get_connection():
    """
    Create and return a connection to the PostgreSQL database.
    
    Database settings are read from environment variables loaded from
    the local .env file.
    """
    return psycopg.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
    )

def test_connection():
    """
    Test the PostgreSQL connection and print the database and user names.
    
    This function does not create tables or insert data.
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user;")
            result = cursor.fetchone()
    print(f"Connected to database: {result}")


# 2. Raw JSON file reading
def load_json(file_path):
    """
    Read a JSON file and return its contents as Python data.

    A ticker JSON file becomes a dictionary, while an EOD JSON file
    becomes a list of dictionaries.
    """
    with file_path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)

    
def get_ticker_files():
    """
    Return a sorted list of all ticker JSON files.
    
    The files are read from the data/raw/tickers directory.
    """
    ticker_directory = RAW_DATA_DIR / "tickers"
    return sorted(ticker_directory.glob("*.json"))

def get_eod_files():
    """
    Return a sorted list of all EOD JSON files.
    
    The files are read from the data/raw/eod directory.
    """
    eod_directory = RAW_DATA_DIR / "eod"
    return sorted(eod_directory.glob("*.json"))


# 3. Exchange and ticker loading
def upsert_exchange(cursor, exchange_data):
    """
    Insert or update one exchange and return its exchange_id.
    
    The exchange is identified by its unique MIC code.
    """
    cursor.execute(
        """
        INSERT INTO exchanges (
            mic,
            name,
            acronym,
            country,
            country_code,
            city,
            website,
            operating_mic,
            legal_entity_name,
            exchange_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (mic)
        DO UPDATE SET
            name = EXCLUDED.name,
            acronym = EXCLUDED.acronym,
            country = EXCLUDED.country,
            country_code = EXCLUDED.country_code,
            city = EXCLUDED.city,
            website = EXCLUDED.website,
            operating_mic = EXCLUDED.operating_mic,
            legal_entity_name = EXCLUDED.legal_entity_name,
            exchange_status = EXCLUDED.exchange_status,
            loaded_at = CURRENT_TIMESTAMP
        RETURNING exchange_id;
        """,

        (
            exchange_data["mic"],
            exchange_data["name"],
            exchange_data.get("acronym"),
            exchange_data.get("country"),
            exchange_data.get("country_code"),
            exchange_data.get("city"),
            exchange_data.get("website"),
            exchange_data.get("operating_mic"),
            exchange_data.get("legal_entity_name"),
            exchange_data.get("exchange_status"),
        ),
    )

    return cursor.fetchone()[0]

def upsert_ticker(cursor, ticker_data, exchange_id):
    """
    Insert or update one ticker and return its ticker_id.
    
    The ticker is identified by its unique symbol and linked to 
    an exchange through exchange_id.
    """

    cursor.execute(
        """
        INSERT INTO tickers (
            symbol,
            name,
            item_type,
            sector,
            industry,
            cik,
            isin,
            cusip,
            ein_employer_id,
            lei,
            series_id,
            sic_code,
            sic_name,
            exchange_id
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (symbol)
        DO UPDATE SET
            name = EXCLUDED.name,
            item_type = EXCLUDED.item_type,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            cik = EXCLUDED.cik,
            isin = EXCLUDED.isin,
            cusip = EXCLUDED.cusip,
            ein_employer_id = EXCLUDED.ein_employer_id,
            lei = EXCLUDED.lei,
            series_id = EXCLUDED.series_id,
            sic_code = EXCLUDED.sic_code,
            sic_name = EXCLUDED.sic_name,
            exchange_id = EXCLUDED.exchange_id,
            loaded_at = CURRENT_TIMESTAMP
        RETURNING ticker_id;
        """,

        (
            ticker_data["symbol"],
            ticker_data["name"],
            ticker_data.get("item_type"),
            ticker_data.get("sector"),
            ticker_data.get("industry"),
            ticker_data.get("cik"),
            ticker_data.get("isin"),
            ticker_data.get("cusip"),
            ticker_data.get("ein_employer_id"),
            ticker_data.get("lei"),
            ticker_data.get("series_id"),
            ticker_data.get("sic_code"),
            ticker_data.get("sic_name"),
            exchange_id,
        ),
    )

    return cursor.fetchone()[0]

    

def load_tickers(connection):
    """
    Load all exchange and ticker records from the raw ticker JSON files.
    
    Exchanges are loaded before tickers because each ticker
    requires an exchange_id foreign key.
    """
    ticker_files = get_ticker_files()

    if not ticker_files:
        raise FileNotFoundError(
            "No ticker JSON files found in data/raw/tickers."
        )

    with connection.cursor() as cursor:
        for file_path in ticker_files:
            ticker_data = load_json(file_path)

            if not isinstance(ticker_data, dict):
                raise ValueError(
                    f"Ticker file must contain a JSON object: {file_path}"
                )

            exchange_data = ticker_data.get("stock_exchange")

            if not isinstance(exchange_data, dict):
                raise ValueError(f"Missing stock_exchange data: {file_path}")

            exchange_id = upsert_exchange(cursor, exchange_data)
            upsert_ticker(cursor, ticker_data, exchange_id)

    print(f"Loaded {len(ticker_files)} ticker files.")
    return len(ticker_files)

# 4. EOD price and dividend loading
def upsert_eod_price(cursor, eod_data, ticker_id, source_file):
    """
    Insert or update one daily EOD record.
    
    The record is uniquely identified by ticker_id and price_date.
    
    Missing price values are preserved as database NULL values.
    """
    # PostgreSQL BIGINT stores volume as a whole number.
    volume = eod_data.get("volume")
    adj_volume = eod_data.get("adj_volume")

    if volume is not None:
        volume = int(volume)

    if adj_volume is not None:
        adj_volume = int(adj_volume)

    cursor.execute(
        """
        INSERT INTO eod_prices (
            ticker_id,
            price_date,
            open,
            high,
            low,
            close,
            adj_open,
            adj_high,
            adj_low,
            adj_close,
            volume,
            adj_volume,
            split_factor,
            price_currency,
            source_file
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (ticker_id, price_date)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            adj_open = EXCLUDED.adj_open,
            adj_high = EXCLUDED.adj_high,
            adj_low = EXCLUDED.adj_low,
            adj_close = EXCLUDED.adj_close,
            volume = EXCLUDED.volume,
            adj_volume = EXCLUDED.adj_volume,
            split_factor = EXCLUDED.split_factor,
            price_currency = EXCLUDED.price_currency,
            source_file = EXCLUDED.source_file,
            loaded_at = CURRENT_TIMESTAMP
        RETURNING eod_price_id;
        """,
        (
            ticker_id,
            eod_data["date"][:10],
            eod_data.get("open"),
            eod_data.get("high"),
            eod_data.get("low"),
            eod_data.get("close"),
            eod_data.get("adj_open"),
            eod_data.get("adj_high"),
            eod_data.get("adj_low"),
            eod_data.get("adj_close"),
            volume,
            adj_volume,
            eod_data.get("split_factor"),
            eod_data.get("price_currency"),
            source_file,
        ),
    )

    return cursor.fetchone()[0]

def upsert_dividend(cursor, eod_data, ticker_id, source_file):
    """
    Insert or update one positive dividend record.

    Dividend information is extracted from an EOD record.

    Records with missing, zero, or negative dividend amounts are skipped.
    """
    # Only positive dividend events belong in the dividends table.
    amount = eod_data.get("dividend")

    if amount is None or amount <= 0:
        return None

    cursor.execute(
        """
        INSERT INTO dividends (
            ticker_id,
            dividend_date,
            amount,
            currency,
            source_file
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (ticker_id, dividend_date)
        DO UPDATE SET
            amount = EXCLUDED.amount,
            currency = EXCLUDED.currency,
            source_file = EXCLUDED.source_file,
            loaded_at = CURRENT_TIMESTAMP
        RETURNING dividend_id;
        """,
        (
            ticker_id,
            eod_data["date"][:10],
            amount,
            eod_data.get("price_currency"),
            source_file,
        ),
    )

    return cursor.fetchone()[0]


def load_eod_data(connection):
    """
    Load all EOD price and dividend records from the raw EOD files.

    Each EOD file belongs to one ticker. The ticker_id is queried once per
    file and reused for every daily record in that file.
    """
    eod_files = get_eod_files()

    if not eod_files:
        raise FileNotFoundError(
            "No EOD JSON files found in data/raw/eod."
        )

    eod_count = 0
    dividend_count = 0

    with connection.cursor() as cursor:
        for file_path in eod_files:
            records = load_json(file_path)

            if not isinstance(records, list) or not records:
                raise ValueError(
                    f"EOD file must contain a non-empty JSON list: {file_path}"
                )

            # One EOD file contains records for one symbol.
            symbol = records[0]["symbol"]

            cursor.execute(
                """
                SELECT ticker_id
                FROM tickers
                WHERE symbol = %s;
                """,
                (symbol,),
            )

            ticker_result = cursor.fetchone()

            if ticker_result is None:
                raise ValueError(f"Ticker not found in database: {symbol}")

            ticker_id = ticker_result[0]

            for eod_data in records:
                upsert_eod_price(
                    cursor,
                    eod_data,
                    ticker_id,
                    file_path.name,
                )
                eod_count += 1

                dividend_id = upsert_dividend(
                    cursor,
                    eod_data,
                    ticker_id,
                    file_path.name,
                )

                if dividend_id is not None:
                    dividend_count += 1

    print(f"Loaded {eod_count} EOD price records.")
    print(f"Loaded {dividend_count} dividend records.")

    return {
        "eod_prices": eod_count,
        "dividends": dividend_count,
    }


# 5. Data quality checks
def run_quality_checks(connection):
    """
    Run database quality checks and return the results.
    
    The checks report table row counts, missing closing prices, and
    duplicate ticker-date combinations.
    """
    checks = {
        "exchanges": "SELECT COUNT(*) FROM exchanges;",
        "tickers": "SELECT COUNT(*) FROM tickers;",
        "eod_prices": "SELECT COUNT(*) FROM eod_prices;",
        "dividends": "SELECT COUNT(*) FROM dividends;",
        "missing_close": """
            SELECT COUNT(*)
            FROM eod_prices
            WHERE close IS NULL;
        """,
        "missing_adj_close": """
            SELECT COUNT(*)
            FROM eod_prices
            WHERE adj_close IS NULL;
        """,
        "duplicate_eod_keys": """
            SELECT COUNT(*)
            FROM (
                SELECT ticker_id, price_date
                FROM eod_prices
                GROUP BY ticker_id, price_date
                HAVING COUNT(*) > 1
            ) AS duplicates;
        """,
    }


    results = {}

    with connection.cursor() as cursor:
        for check_name, query in checks.items():
            cursor.execute(query)
            results[check_name] = cursor.fetchone()[0]

    print("Database quality check results:")
    for check_name, result in results.items():
        print(f"  {check_name}: {result}")

    return results


# 6. Complete database loading pipeline
def main():
    """Load all raw stock data and run database quality checks."""
    # The connection context commits on success and rolls back on error.
    with get_connection() as connection:
        load_tickers(connection)
        load_eod_data(connection)
        run_quality_checks(connection)


if __name__ == "__main__":
    main()
