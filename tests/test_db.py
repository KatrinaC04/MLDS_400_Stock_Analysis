import json
from unittest.mock import Mock

from src import db


def test_load_json(tmp_path):
    """A JSON object is loaded as a Python dictionary."""
    file_path = tmp_path / "sample.json"
    file_path.write_text(
        json.dumps({"symbol": "AAPL"}),
        encoding="utf-8",
    )

    assert db.load_json(file_path) == {"symbol": "AAPL"}


def test_get_json_files_are_sorted(tmp_path, monkeypatch):
    """Ticker and EOD file paths are returned in stable order."""
    ticker_dir = tmp_path / "tickers"
    eod_dir = tmp_path / "eod"
    ticker_dir.mkdir()
    eod_dir.mkdir()

    (ticker_dir / "MSFT.json").write_text("{}", encoding="utf-8")
    (ticker_dir / "AAPL.json").write_text("{}", encoding="utf-8")
    (eod_dir / "MSFT.json").write_text("[]", encoding="utf-8")
    (eod_dir / "AAPL.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(db, "RAW_DATA_DIR", tmp_path)

    assert [path.name for path in db.get_ticker_files()] == [
        "AAPL.json",
        "MSFT.json",
    ]
    assert [path.name for path in db.get_eod_files()] == [
        "AAPL.json",
        "MSFT.json",
    ]


def test_upsert_exchange_returns_exchange_id():
    """An exchange upsert returns the database-generated ID."""
    cursor = Mock()
    cursor.fetchone.return_value = (3,)
    exchange_data = {
        "mic": "XNAS",
        "name": "NASDAQ - ALL MARKETS",
        "country_code": "US",
    }

    result = db.upsert_exchange(cursor, exchange_data)

    assert result == 3
    parameters = cursor.execute.call_args.args[1]
    assert parameters[0] == "XNAS"
    assert parameters[1] == "NASDAQ - ALL MARKETS"
    assert parameters[4] == "US"


def test_upsert_eod_price_converts_date_and_volume():
    """EOD dates and floating-point volume values are normalized."""
    cursor = Mock()
    cursor.fetchone.return_value = (101,)
    eod_data = {
        "date": "2026-01-02T00:00:00+0000",
        "close": None,
        "volume": 37746172.0,
        "adj_volume": 37838054.0,
        "price_currency": "USD",
    }

    result = db.upsert_eod_price(
        cursor,
        eod_data,
        ticker_id=1,
        source_file="AAPL.json",
    )

    assert result == 101
    parameters = cursor.execute.call_args.args[1]
    assert parameters[0] == 1
    assert parameters[1] == "2026-01-02"
    assert parameters[5] is None
    assert parameters[10] == 37746172
    assert parameters[11] == 37838054


def test_upsert_dividend_skips_non_positive_amounts():
    """Zero dividends do not create database rows."""
    cursor = Mock()

    result = db.upsert_dividend(
        cursor,
        {"dividend": 0.0},
        ticker_id=1,
        source_file="AAPL.json",
    )

    assert result is None
    cursor.execute.assert_not_called()


def test_upsert_dividend_returns_id_for_positive_amount():
    """A positive dividend is mapped and returns its database ID."""
    cursor = Mock()
    cursor.fetchone.return_value = (9,)
    eod_data = {
        "date": "2026-02-06T00:00:00+0000",
        "dividend": 0.25,
        "price_currency": "USD",
    }

    result = db.upsert_dividend(
        cursor,
        eod_data,
        ticker_id=1,
        source_file="AAPL.json",
    )

    assert result == 9
    parameters = cursor.execute.call_args.args[1]
    assert parameters == (
        1,
        "2026-02-06",
        0.25,
        "USD",
        "AAPL.json",
    )
