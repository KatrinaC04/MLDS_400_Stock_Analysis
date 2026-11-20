import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from src.api_client import MarketstackClient
# Stock universe: 6 sectors, 4 stocks each
STOCKS_BY_SECTOR = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO"],
    "Financials": ["JPM", "BAC", "GS", "MS"],
    "Healthcare": ["JNJ", "MRK", "ABBV", "LLY"],
    "Consumer Staples": ["WMT", "PG", "KO", "COST"],
    "Energy": ["XOM", "CVX", "COP", "EOG"],
    "Industrials": ["CAT", "DE", "HON", "UNP"]
}

BENCHMARK = "SPY"

DATE_FROM = "2026-01-01"
DATE_TO = "2026-11-19"


def get_symbols():
    stocks = [
        symbol
        for sector_stocks in STOCKS_BY_SECTOR.values()
        for symbol in sector_stocks
    ]
    return stocks + [BENCHMARK]

def fetch_eod(client, symbol, date_from=DATE_FROM, date_to=DATE_TO):
    params = {
        "symbols": symbol,
        "date_from": date_from,
        "date_to": date_to,
        "sort": "ASC"
    }

    records = client.get_all_pages("eod", params=params, limit=1000)
    return records

def fetch_ticker(client, symbol):
    endpoint = f"tickers/{symbol}"
    ticker_info = client.get(endpoint)

    return ticker_info

def save_raw_json(data, file_path):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raise FileExistsError(f"File already exists: {path}")

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return path

def ingest_eod_batch(client, symbols=None, date_from=DATE_FROM,
                     date_to=DATE_TO, raw_dir="data/raw"):
    if symbols is None:
        symbols = get_symbols()

    saved_files = []

    for symbol in symbols:
        file_path = (
            Path(raw_dir) / "eod" /
            f"{symbol}_{date_from}_{date_to}.json"
        )

        if file_path.exists():
            print(f"Skipping {symbol}: file already exists.")
            continue

        records = fetch_eod(client, symbol, date_from, date_to)

        if not records:
            raise ValueError(f"No EOD data returned for {symbol}.")

        saved_files.append(save_raw_json(records, file_path))
        print(f"Saved {symbol}: {len(records)} records.")

    return saved_files

def ingest_ticker_batch(client, symbols=None, raw_dir="data/raw"):
    if symbols is None:
        symbols = [s for s in get_symbols() if s != BENCHMARK]

    saved_files = []

    for symbol in symbols:
        file_path = Path(raw_dir) / "tickers" / f"{symbol}.json"

        if file_path.exists():
            print(f"Skipping {symbol}: ticker file already exists.")
            continue

        ticker_info = fetch_ticker(client, symbol)

        if not isinstance(ticker_info, dict) or not ticker_info:
            raise ValueError(f"No ticker information returned for {symbol}.")

        saved_files.append(save_raw_json(ticker_info, file_path))
        print(f"Saved ticker information for {symbol}.")

    return saved_files

def get_latest_eod_date(file_path):
    path = Path(file_path)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("EOD file must contain a list of records.")

    if not records:
        return None

    dates = [date.fromisoformat(row["date"][:10]) for row in records]
    return max(dates).isoformat()

def get_latest_saved_eod_date(symbol, raw_dir="data/raw"):
    eod_dir = Path(raw_dir) / "eod"
    latest_dates = []

    for file_path in eod_dir.glob(f"{symbol}_*.json"):
        latest_date = get_latest_eod_date(file_path)

        if latest_date is not None:
            latest_dates.append(latest_date)

    if not latest_dates:
        return None

    return max(latest_dates)

def ingest_eod_incremental(client, symbol, date_to, raw_dir="data/raw"):
    latest = get_latest_saved_eod_date(symbol, raw_dir)

    if latest is None:
        raise ValueError(f"No saved EOD data for {symbol}. Run initial ingestion first.")

    start_date = date.fromisoformat(latest) + timedelta(days=1)
    end_date = date.fromisoformat(date_to)

    if start_date > end_date:
        print(f"Skipping {symbol}: already up to date.")
        return None

    date_from = start_date.isoformat()
    records = fetch_eod(client, symbol, date_from, date_to)

    if not records:
        print(f"No new EOD records for {symbol}.")
        return None

    file_path = Path(raw_dir) / "eod" / f"{symbol}_{date_from}_{date_to}.json"
    saved_path = save_raw_json(records, file_path)

    print(f"Saved {len(records)} new records for {symbol}.")
    return saved_path

def main():
    parser = argparse.ArgumentParser(description="Marketstack data ingestion")
    parser.add_argument(
        "--mode",
        choices=["preview", "eod", "tickers", "incremental"],
        default="preview"
    )
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--date-to", default=DATE_TO)
    parser.add_argument("--confirm-live", action="store_true")

    args = parser.parse_args()
    if args.symbols:
        symbols = args.symbols
    elif args.mode == "tickers":
        symbols = [s for s in get_symbols() if s != BENCHMARK]
    else:
        symbols = get_symbols()

    if args.mode == "preview":
        print("Total symbols:", len(symbols))
        print("Symbols:", symbols)
        print("Date range:", DATE_FROM, "to", DATE_TO)
        print("Preview only: no API requests sent.")
        return

    if not args.confirm_live:
        parser.error("Live API requests require --confirm-live")

    client = MarketstackClient()

    if args.mode == "eod":
        ingest_eod_batch(client, symbols=symbols)

    elif args.mode == "tickers":
        ingest_ticker_batch(client, symbols=symbols)

    elif args.mode == "incremental":
        for symbol in symbols:
            ingest_eod_incremental(
                client,
                symbol,
                date_to=args.date_to
            )



if __name__ == "__main__":
    main()
