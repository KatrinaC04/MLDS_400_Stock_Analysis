import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.marketstack.com/v2"

# Load the API key from the project root
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class MarketstackClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("MARKETSTACK_API_KEY")

        if not self.api_key:
            raise ValueError("Marketstack API key is missing.")
        self.min_interval = 0.5
        self._last_request_time = None

    def _wait_for_slot(self):
        now = time.monotonic()

        if self._last_request_time is not None:
            elapsed = now - self._last_request_time
            remaining = self.min_interval - elapsed

            if remaining > 0:
                time.sleep(remaining)
                now = time.monotonic()

        self._last_request_time = now

    def get(self, endpoint, params=None):
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        query = {**(params or {}), "access_key": self.api_key}
        retry_statuses = {429, 500, 502, 503, 504}

        for attempt in range(3):
            try:
                self._wait_for_slot()
                response = requests.get(url, params=query, timeout=30)

            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 2:
                    raise RuntimeError("Network request failed after 3 attempts.") from exc

            else:
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise RuntimeError("Invalid JSON response.") from exc

                    if isinstance(data, dict) and "error" in data:
                        raise RuntimeError("Marketstack returned an API error.")

                    return data

                if response.status_code not in retry_statuses or attempt == 2:
                    raise RuntimeError(
                        f"Marketstack request failed: HTTP {response.status_code}"
                    )

            time.sleep(2 ** attempt)

    def get_all_pages(self, endpoint, params=None, limit=1000):
        if not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000.")

        query = dict(params or {})
        offset = query.pop("offset", 0)
        query.pop("limit", None)
        all_records = []

        while True:
            page = self.get(
                endpoint,
                {**query, "limit": limit, "offset": offset}
            )

            records = page.get("data")
            pagination = page.get("pagination")

            if not isinstance(records, list) or not isinstance(pagination, dict):
                raise ValueError("Unexpected API response structure.")

            all_records.extend(records)
            offset += len(records)

            if offset >= pagination["total"]:
                break
            if not records:
                raise RuntimeError("Pagination stopped making progress.")

        return all_records
