import os
from datetime import datetime, timedelta, date

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator

PROJECT_ROOT = "/opt/airflow"          # db.py / ingest.py use relative path data/raw, so chdir first
MONTHLY_CREDITS = 100                  # free plan quota
SAFETY_MARGIN = 10                     # keep a buffer
INITIAL_CREDITS_USED = 50              # initial ingestion already used (confirm with Part A)
KNOWN_MISSING_CLOSE = 70               # known gaps in the initial raw data (kept as-is)
MAX_MISSING_CLOSE_RATIO = 0.02         # above 2% is treated as abnormal

CREATE_RUNS_TABLE = """
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
"""


def _prepare():
    os.chdir(PROJECT_ROOT)


def _end_date(ctx):
    return ctx["params"]["date_to"] or ctx["ds"]


def branch_fn(**ctx):
    """Skip the API when not requested or on weekends, to save credits."""
    if not ctx["params"]["run_ingest"]:
        return "skip_ingest"
    if date.fromisoformat(_end_date(ctx)).weekday() >= 5:
        print("End date is a weekend, skipping API calls.")
        return "skip_ingest"
    return "credit_guard"


def credit_guard_fn(**ctx):
    from src import db
    _prepare()
    n = len(ctx["params"]["symbols"])
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_RUNS_TABLE)
        cur.execute(
            """
            SELECT COALESCE(SUM(api_credits_used), 0) FROM pipeline_runs
            WHERE date_trunc('month', started_at) = date_trunc('month', now())
            """
        )
        used = INITIAL_CREDITS_USED + int(cur.fetchone()[0])
    print(f"Credits used so far: {used}; this run needs: {n}")
    if used + n > MONTHLY_CREDITS - SAFETY_MARGIN:
        raise AirflowFailException(
            f"Credit budget exceeded: {used}+{n} > {MONTHLY_CREDITS - SAFETY_MARGIN}"
        )


def ingest_fn(**ctx):
    _prepare()
    from src import ingest
    from src.api_client import MarketstackClient
    symbols = ctx["params"]["symbols"]
    end = _end_date(ctx)
    client = MarketstackClient()
    saved = [ingest.ingest_eod_incremental(client, s, date_to=end) for s in symbols]
    return {"credits": len(symbols), "files": sum(1 for p in saved if p)}


def load_tickers_fn(**_):
    from src import db
    _prepare()
    with db.get_connection() as conn:
        return db.load_tickers(conn)


def load_eod_fn(**_):
    from src import db
    _prepare()
    with db.get_connection() as conn:
        return db.load_eod_data(conn)


def quality_fn(**_):
    from src import db
    _prepare()
    with db.get_connection() as conn:
        r = db.run_quality_checks(conn)

    total = r["eod_prices"]
    if total == 0:
        raise AirflowFailException("eod_prices is empty")
    if r["duplicate_eod_keys"] != 0:
        raise AirflowFailException("Duplicate (ticker, date) rows found")

    ratio = r["missing_close"] / total
    if ratio > MAX_MISSING_CLOSE_RATIO:
        raise AirflowFailException(f"missing close ratio too high: {ratio:.2%}")
    if r["missing_close"] > KNOWN_MISSING_CLOSE:
        print(f"WARNING: {r['missing_close']} missing close "
              f"(known baseline {KNOWN_MISSING_CLOSE}); new data may add gaps.")
    if r["missing_close"] != r["missing_adj_close"]:
        print("WARNING: missing close and adj_close counts differ.")

    r["missing_close_ratio"] = round(ratio, 4)
    return r


def log_metrics_fn(**ctx):
    """Write per-task duration/status/rows/credits to pipeline_runs, plus end-to-end total."""
    from src import db
    dag_run, ti = ctx["dag_run"], ctx["ti"]
    rows, starts, ends = [], [], []

    for t in dag_run.get_task_instances():
        if t.task_id == ti.task_id:
            continue
        out = ti.xcom_pull(task_ids=t.task_id)
        rows_loaded = None
        credits = 0
        if isinstance(out, int):
            rows_loaded = out
        elif isinstance(out, dict):
            rows_loaded = out.get("eod_prices")
            credits = out.get("credits", 0)
        if t.start_date:
            starts.append(t.start_date)
        if t.end_date:
            ends.append(t.end_date)
        rows.append((dag_run.run_id, t.task_id, t.state, t.start_date, t.end_date,
                     t.duration, rows_loaded, credits))

    if starts and ends:
        total = (max(ends) - min(starts)).total_seconds()
        rows.append((dag_run.run_id, "__pipeline_total__", "success",
                     min(starts), max(ends), total, None, 0))

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_RUNS_TABLE)
        cur.executemany(
            """
            INSERT INTO pipeline_runs
            (run_id, task_id, status, started_at, ended_at, duration_sec,
             rows_loaded, api_credits_used)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )


with DAG(
    dag_id="marketstack_pipeline",
    description="Marketstack ingest -> Postgres load -> quality check -> metrics",
    start_date=datetime(2026, 11, 1),
    schedule=None,                 # manual trigger to protect the free-tier quota
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    params={
        "run_ingest": Param(False, type="boolean",
                            description="True calls the Marketstack API (uses credits)"),
        "symbols": Param(["AAPL", "JPM", "XOM", "SPY"], type="array"),
        "date_to": Param(None, type=["null", "string"],
                         description="Incremental end date YYYY-MM-DD; empty = run date"),
    },
    tags=["marketstack"],
) as dag:

    branch = BranchPythonOperator(task_id="branch_ingest", python_callable=branch_fn)
    credit_guard = PythonOperator(task_id="credit_guard", python_callable=credit_guard_fn)
    ingest_task = PythonOperator(task_id="ingest_incremental", python_callable=ingest_fn)
    skip_ingest = EmptyOperator(task_id="skip_ingest")

    load_tickers = PythonOperator(task_id="load_tickers", python_callable=load_tickers_fn,
                                  trigger_rule="none_failed_min_one_success")
    load_eod = PythonOperator(task_id="load_eod", python_callable=load_eod_fn)
    quality = PythonOperator(task_id="quality_checks", python_callable=quality_fn)
    log_metrics = PythonOperator(task_id="log_run_metrics", python_callable=log_metrics_fn,
                                 trigger_rule="all_done")

    branch >> [credit_guard, skip_ingest]
    credit_guard >> ingest_task
    [ingest_task, skip_ingest] >> load_tickers >> load_eod >> quality >> log_metrics
