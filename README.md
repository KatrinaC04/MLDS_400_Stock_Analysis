
# MLDS 400 Stock Analysis

## 1. Project Overview

This project builds a Python-based data ingestion pipeline for stock market analysis using the Marketstack V2 API.

The dataset includes 24 U.S. stocks across six sectors and SPY (S&P 500 ETF) as a market benchmark.

The pipeline supports:
- Historical End-of-Day (EOD) data collection
- Ticker information retrieval
- API pagination, retries, and request throttling
- Incremental EOD ingestion
- Raw JSON storage with separate data quality checks

The collected data will support downstream database development and exploratory data analysis (EDA).

## 2. Data Scope

### Stock Universe

| Sector | Symbols |
|---|---|
| Technology | AAPL, MSFT, NVDA, AVGO |
| Financials | JPM, BAC, GS, MS |
| Healthcare | JNJ, MRK, ABBV, LLY |
| Consumer Staples | WMT, PG, KO, COST |
| Energy | XOM, CVX, COP, EOG |
| Industrials | CAT, DE, HON, UNP |
| Benchmark | SPY |

**Total:** 25 symbols (24 stocks + SPY)

### Historical Period

- Start date: January 1, 2026
- End date: November 19, 2026
- Frequency: Daily (trading days only)
- Source: Marketstack V2 API

The initial dataset uses a fixed date range for consistency and reproducibility.

### API Endpoints

| Endpoint | Purpose |
|---|---|
| `/v2/eod` | Historical daily market data |
| `/v2/tickers/{symbol}` | Ticker and company information |

All available API fields are preserved in the raw JSON files.

EOD records include dates, OHLC prices, adjusted prices, volume, dividends, and split factors, among other fields.

Ticker records include symbols, company names, sectors, industries, and other available metadata.

## 3. Project Structure

```text
MLDS_400_Stock_Analysis/
├── src/
│   ├── __init__.py
│   ├── api_client.py
│   └── ingest.py
├── tests/
│   ├── test_api_client.py
│   └── test_ingest.py
├── data/
│   └── raw/                  # Local data, excluded from Git
│       ├── eod/
│       └── tickers/
├── .env                      # Local API key, excluded from Git
├── .gitignore
├── requirements.txt
└── README.md
```

- `api_client.py`: Handles API requests, pagination, retries, and throttling.
- `ingest.py`: Defines the stock universe, retrieval functions, file storage, and CLI.
- `tests/`: Contains unit tests using mocked API responses.
- `data/raw/`: Stores unmodified API records as JSON files.

## 4. Environment Setup

### Create and Activate the Environment

Python 3.12 is used for this project.

```bash
conda create -n stock_pipeline python=3.12 -y
conda activate stock_pipeline
```

Install the required dependencies:

```bash
python -m pip install -r requirements.txt
```

### Configure the API Key

Create a `.env` file in the project root:

```text
MARKETSTACK_API_KEY=your_api_key_here
```

Obtain an API key from [Marketstack](https://marketstack.com/).

Never commit API keys to GitHub. Each team member can configure their own key locally.

## 5. Running the Pipeline

Run the following commands from the project root directory.

### Preview Mode

Inspect the stock universe and date range without sending API requests.

```bash
python -m src.ingest --mode preview
```

### Initial EOD Ingestion

Download historical EOD data for all 25 symbols:

```bash
python -m src.ingest --mode eod --confirm-live
```

To retrieve one symbol only:

```bash
python -m src.ingest --mode eod --symbols AAPL --confirm-live
```

Existing output files are skipped to avoid unnecessary repeated requests.

### Ticker Information Ingestion

Download ticker information for the 24 individual stocks:

```bash
python -m src.ingest --mode tickers --confirm-live
```

SPY is excluded from the default ticker selection but can be downloaded separately:

```bash
python -m src.ingest --mode tickers --symbols SPY --confirm-live
```

### Incremental EOD Ingestion

Update an existing stock dataset to a specified end date:

```bash
python -m src.ingest --mode incremental --symbols AAPL --date-to 2026-11-23 --confirm-live
```

The pipeline identifies the latest locally saved trading date and requests records starting from the following calendar day.

**Notes:**
- Initial EOD ingestion must be completed first.
- Already covered date ranges are skipped.
- Incremental results are saved separately without overwriting existing files.
- Incremental ingestion does not automatically detect or backfill missing historical dates.
- Use an end date for which market data is available.

**API usage:** Live requests consume API credits. Pagination and retries may result in additional calls. Monitor usage in the Marketstack dashboard.

## 6. Raw Data Storage

Data is stored as JSON without filtering or imputing fields.

Example output files:

```text
data/raw/eod/AAPL_2026-01-01_2026-11-19.json
data/raw/tickers/AAPL.json
```

Incremental EOD data is saved in additional date-range-specific files.

**Initial ingestion results:**

| Dataset | Files | Records |
|---|---:|---:|
| EOD | 25 | 5,575 |
| Ticker Information | 25 | 25 |

Each symbol has 223 EOD records in the initial dataset.

Raw data is excluded from Git through `.gitignore` and must be shared separately with downstream team members.

## 7. Data Quality Findings

Basic validation was performed on the initial EOD and ticker datasets.

### EOD Data

| Check | Result |
|---|---:|
| Total records | 5,575 |
| Duplicate dates within symbols | 0 |
| Invalid symbols or out-of-range dates | 0 |
| Missing `close` | 70 |
| Missing `adj_close` | 70 |

Missing adjusted closing prices are concentrated on:

| Date | Affected symbols |
|---|---:|
| 2026-06-09 | 24 |
| 2026-06-10 | 24 |
| 2026-06-15 | 22 |

These missing values are preserved in the raw dataset. Their upstream cause has not been confirmed.

### Ticker Information

All 25 ticker files passed the basic checks for symbol consistency and required company metadata.

Some API classifications differ from the project's sector labels:
- Financials → Financial Services
- Consumer Staples → Consumer Defensive

SPY does not have an assigned sector, as it is an ETF benchmark.

Sector standardization and missing-value treatment are left to downstream data processing.

## 8. Testing

Run all unit tests:

```bash
python -m pytest tests/ -v
```

The current test suite contains 14 passing tests covering:
- API pagination, retries, and rate limiting
- Stock universe configuration
- EOD and ticker retrieval
- Raw JSON storage
- Skipping existing files
- Incremental ingestion
- Incremental CLI argument handling

Tests use mocked responses and do not consume API credits.

Initial EOD and ticker ingestion were also verified using live Marketstack requests. Incremental ingestion has been unit-tested but has not yet undergone a live integration test.

## 9. Limitations and Next Steps

- API access and historical coverage depend on the Marketstack subscription plan.
- Existing files are skipped; the pipeline does not automatically repair incomplete files.
- Incremental ingestion uses the latest saved date and does not detect historical gaps.
- Raw data is not cleaned, normalized, or loaded into a database by this component.
- Exchange, dividend, and split attributes may appear in the retrieved records, but separate ingestion pipelines for those endpoints are not included.

Next steps include downstream schema design, data transformation, sector standardization, missing-value handling, and EDA.

## 10. Data Handoff

The repository contains the ingestion code, dependencies, and tests.

The 50 initial raw JSON files are stored locally and are not included in GitHub. Team members requiring these files should obtain the dataset separately.

Downstream processing should preserve source records, distinguish SPY from individual stocks, and document any transformations applied.
