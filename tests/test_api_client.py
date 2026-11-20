from unittest.mock import Mock, patch
import pytest
from src.api_client import MarketstackClient


def test_pagination():
    client = MarketstackClient(api_key="fake-key")

    pages = [
        {"data": [1, 2], "pagination": {"total": 5}},
        {"data": [3, 4], "pagination": {"total": 5}},
        {"data": [5], "pagination": {"total": 5}},
    ]

    with patch.object(client, "get", side_effect=pages) as mock_get:
        result = client.get_all_pages("eod", limit=2)

    assert result == [1, 2, 3, 4, 5]
    assert mock_get.call_count == 3
    offsets = [call.args[1]["offset"] for call in mock_get.call_args_list]
    assert offsets == [0, 2, 4]

def test_retry_on_server_error():
    client = MarketstackClient(api_key="fake-key")

    error_response = Mock(status_code=503)
    success_response = Mock(status_code=200)
    success_response.json.return_value = {"data": [{"symbol": "AAPL"}]}

    with patch("src.api_client.requests.get",
               side_effect=[error_response, error_response, success_response]) as mock_get:
        with patch("src.api_client.time.sleep") as mock_sleep:
            with patch("src.api_client.time.monotonic",
                       side_effect=[10.0, 11.0, 13.0]):
                result = client.get("eod")

    assert result["data"][0]["symbol"] == "AAPL"
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2


def test_no_retry_on_unauthorized():
    client = MarketstackClient(api_key="fake-key")
    error_response = Mock(status_code=401)

    with patch("src.api_client.requests.get", return_value=error_response) as mock_get:
        with pytest.raises(RuntimeError, match="HTTP 401"):
            client.get("eod")

    assert mock_get.call_count == 1

def test_rate_limiting():
    client = MarketstackClient(api_key="fake-key")

    success_response = Mock(status_code=200)
    success_response.json.return_value = {"data": []}

    with patch("src.api_client.requests.get", return_value=success_response) as mock_get:
        with patch("src.api_client.time.monotonic",
                   side_effect=[10.0, 10.1, 10.5]):
            with patch("src.api_client.time.sleep") as mock_sleep:
                client.get("eod")
                client.get("eod")

    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args.args[0] == pytest.approx(0.4)
