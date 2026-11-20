import json
import pytest
from unittest.mock import Mock, patch
from src.ingest import (
    fetch_eod,
    fetch_ticker,
    get_symbols,
    save_raw_json,
    ingest_eod_batch,
    ingest_ticker_batch,
    get_latest_eod_date,
    get_latest_saved_eod_date,
    ingest_eod_incremental,
    main,
    DATE_FROM,
    DATE_TO,
)

def test_stock_universe():
    symbols = get_symbols()

    assert len(symbols) == 25
    assert len(set(symbols)) == 25
    assert symbols[-1] == "SPY"


def test_fetch_eod():
    client = Mock()
    sample_data = [{"symbol": "AAPL", "date": "2026-11-19", "close": 270.0}]
    client.get_all_pages.return_value = sample_data

    result = fetch_eod(client, "AAPL")

    assert result == sample_data
    client.get_all_pages.assert_called_once_with(
        "eod",
        params={
            "symbols": "AAPL",
            "date_from": DATE_FROM,
            "date_to": DATE_TO,
            "sort": "ASC"
        },
        limit=1000
    )

def test_fetch_ticker():
    client = Mock()

    sample_info = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics"
    }
    client.get.return_value = sample_info

    result = fetch_ticker(client, "AAPL")

    assert result == sample_info
    assert result["sector"] == "Technology"
    client.get.assert_called_once_with("tickers/AAPL")

def test_save_raw_json(tmp_path):
    sample_data = [
        {
            "symbol": "AAPL",
            "date": "2026-11-19",
            "adj_close": 270.0,
            "volume": 1000000,
            "extra_field": {"source": "Marketstack"}
        }
    ]

    file_path = tmp_path / "raw" / "eod" / "AAPL.json"
    saved_path = save_raw_json(sample_data, file_path)

    assert saved_path.exists()
    assert json.loads(file_path.read_text(encoding="utf-8")) == sample_data

    with pytest.raises(FileExistsError):
        save_raw_json(sample_data, file_path)

def test_ingest_eod_batch_skips_existing(tmp_path):
    client = Mock()
    sample_data = [{"symbol": "AAPL", "date": "2026-11-19"}]

    with patch("src.ingest.fetch_eod", return_value=sample_data) as mock_fetch:
        first_run = ingest_eod_batch(
            client, symbols=["AAPL"], raw_dir=tmp_path
        )
        second_run = ingest_eod_batch(
            client, symbols=["AAPL"], raw_dir=tmp_path
        )

    file_path = tmp_path / "eod" / f"AAPL_{DATE_FROM}_{DATE_TO}.json"

    assert file_path.exists()
    assert json.loads(file_path.read_text()) == sample_data
    assert len(first_run) == 1
    assert second_run == []
    assert mock_fetch.call_count == 1

def test_ingest_ticker_batch_skips_existing(tmp_path):
    client = Mock()
    sample_info = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology"
    }

    with patch("src.ingest.fetch_ticker", return_value=sample_info) as mock_fetch:
        first_run = ingest_ticker_batch(
            client, symbols=["AAPL"], raw_dir=tmp_path
        )
        second_run = ingest_ticker_batch(
            client, symbols=["AAPL"], raw_dir=tmp_path
        )

    file_path = tmp_path / "tickers" / "AAPL.json"

    assert file_path.exists()
    assert json.loads(file_path.read_text()) == sample_info
    assert len(first_run) == 1
    assert second_run == []
    assert mock_fetch.call_count == 1

def test_get_latest_eod_date(tmp_path):
    sample_data = [
        {"symbol": "AAPL", "date": "2026-11-18T00:00:00+0000"},
        {"symbol": "AAPL", "date": "2026-11-19T00:00:00+0000"},
        {"symbol": "AAPL", "date": "2026-11-17T00:00:00+0000"}
    ]

    file_path = tmp_path / "eod" / "AAPL.json"
    save_raw_json(sample_data, file_path)

    latest_date = get_latest_eod_date(file_path)

    assert latest_date == "2026-11-19"
    assert get_latest_eod_date(tmp_path / "missing.json") is None


def test_get_latest_saved_eod_date(tmp_path):
    eod_dir = tmp_path / "eod"

    first_data = [
        {"symbol": "AAPL", "date": "2026-11-18"},
        {"symbol": "AAPL", "date": "2026-11-19"}
    ]
    second_data = [
        {"symbol": "AAPL", "date": "2026-11-20"},
        {"symbol": "AAPL", "date": "2026-11-23"}
    ]

    save_raw_json(first_data, eod_dir / "AAPL_part1.json")
    save_raw_json(second_data, eod_dir / "AAPL_part2.json")

    assert get_latest_saved_eod_date("AAPL", tmp_path) == "2026-11-23"
    assert get_latest_saved_eod_date("MSFT", tmp_path) is None

def test_ingest_eod_incremental(tmp_path):
    client = Mock()

    initial_data = [{"symbol": "AAPL", "date": "2026-11-19"}]
    initial_file = tmp_path / "eod" / "AAPL_initial.json"
    save_raw_json(initial_data, initial_file)

    new_data = [{"symbol": "AAPL", "date": "2026-11-23"}]

    with patch("src.ingest.fetch_eod", return_value=new_data) as mock_fetch:
        saved_path = ingest_eod_incremental(
            client, "AAPL", "2026-11-23", tmp_path
        )
        second_run = ingest_eod_incremental(
            client, "AAPL", "2026-11-23", tmp_path
        )

    mock_fetch.assert_called_once_with(
        client, "AAPL", "2026-11-20", "2026-11-23"
    )
    assert json.loads(saved_path.read_text()) == new_data
    assert second_run is None

def test_cli_incremental():
    args = [
        "ingest", "--mode", "incremental",
        "--symbols", "AAPL",
        "--date-to", "2026-11-23",
        "--confirm-live"
    ]

    with patch("sys.argv", args):
        with patch("src.ingest.MarketstackClient") as mock_client:
            with patch("src.ingest.ingest_eod_incremental") as mock_ingest:
                main()

    mock_ingest.assert_called_once_with(
        mock_client.return_value,
        "AAPL",
        date_to="2026-11-23"
    )
