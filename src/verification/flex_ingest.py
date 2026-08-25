#!/usr/bin/env python3
"""
IBKR Flex Web Service ingest for live track-record verification.

Pulls per-account Flex Activity queries (trades, positions, cash, NAV) from
IBKR's report servers and upserts into the app Postgres so the public
transparency page can be computed from BROKER data, not TradeMind's own
ledger. Raw XML is archived for audit and re-migration.

Tables (created idempotently):
  verified_trades      one row per execution
  verified_positions   daily position snapshot per account
  verified_nav         daily NAV snapshot per account
  flex_pull_log        every pull attempt, with status

Config (env or .env):
  FLEX_TOKEN_LEAPS    Flex Web Service token from the LEAPS login
  FLEX_TOKEN_BASIC    Flex Web Service token from the QQQ Basic login
  FLEX_TOKEN          fallback token used for both (single-login setups)
  FLEX_QUERY_LEAPS    Activity Flex Query ID for the LEAPS account
  FLEX_QUERY_BASIC    Activity Flex Query ID for the QQQ Basic account
  FLEX_RAW_DIR        optional, default ~/flex_raw

Note: Flex tokens are per IB LOGIN, not per account. Two separate logins
require two tokens; linked sub-accounts under one login share one token.

Usage:
  python3 -m src.verification.flex_ingest            # nightly pull, both accounts
  python3 -m src.verification.flex_ingest --smoke    # schema + parse test only, no network
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("flex_ingest")

REQUEST_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"

SCHEMA = """
CREATE TABLE IF NOT EXISTS verified_trades (
    id              BIGSERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    trade_id        TEXT,
    symbol          TEXT NOT NULL,
    asset_type      TEXT,
    description     TEXT,
    trade_date      DATE,
    settle_date     DATE,
    trade_time      TIMESTAMPTZ,
    quantity        NUMERIC,
    trade_price     NUMERIC,
    proceeds        NUMERIC,
    commission      NUMERIC,
    net_cash        NUMERIC,
    raw             JSONB,
    pulled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, trade_id)
);
CREATE TABLE IF NOT EXISTS verified_positions (
    id              BIGSERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    as_of           DATE NOT NULL,
    symbol          TEXT NOT NULL,
    asset_type      TEXT,
    quantity        NUMERIC,
    mark_price      NUMERIC,
    position_value  NUMERIC,
    raw             JSONB,
    pulled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, as_of, symbol)
);
CREATE TABLE IF NOT EXISTS verified_nav (
    id              BIGSERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    as_of           DATE NOT NULL,
    nav             NUMERIC,
    cash            NUMERIC,
    deposits        NUMERIC,
    withdrawals     NUMERIC,
    raw             JSONB,
    pulled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, as_of)
);
ALTER TABLE verified_nav ADD COLUMN IF NOT EXISTS deposits NUMERIC;
ALTER TABLE verified_nav ADD COLUMN IF NOT EXISTS withdrawals NUMERIC;
CREATE TABLE IF NOT EXISTS flex_pull_log (
    id              BIGSERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL,
    detail          TEXT
);
"""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _db_connect():
    import psycopg2
    url = _env("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


def init_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def request_statement(token: str, query_id: str, timeout: int = 60) -> str:
    """Ask IBKR to generate the statement; returns the reference code."""
    url = f"{REQUEST_URL}?t={token}&q={query_id}&v=3"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    root = ET.fromstring(body)
    status = root.findtext("Status")
    if status != "Success":
        raise RuntimeError(f"SendRequest failed: {root.findtext('ErrorCode')}: {root.findtext('ErrorMessage')}")
    return root.findtext("ReferenceCode")


def fetch_statement(token: str, ref: str, attempts: int = 6, wait_s: int = 15) -> bytes:
    """Poll until the generated statement is ready, then return raw XML bytes."""
    url = f"{GET_URL}?t={token}&q={ref}&v=3"
    for i in range(attempts):
        with urllib.request.urlopen(url, timeout=60) as r:
            body = r.read()
        # IBKR returns an XML error envelope while the report is still generating
        head = body[:200].decode("utf-8", "replace")
        if "Statement generation in progress" in head or "<FlexStatementResponse" in head and "<ErrorCode>1019" in head:
            time.sleep(wait_s)
            continue
        if head.lstrip().startswith("<FlexQueryResponse"):
            return body
        # Any other response: surface it
        raise RuntimeError(f"Unexpected Flex response: {head}")
    raise RuntimeError("Statement not ready after polling")


def _f(v):
    try:
        return float(v) if v not in (None, "", "--") else None
    except (TypeError, ValueError):
        return None


def parse_and_store(conn, account_id: str, strategy: str, xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    counts = {"trades": 0, "positions": 0, "nav": 0}
    today = datetime.now(timezone.utc).date().isoformat()

    with conn.cursor() as cur:
        for tr in root.iter("Trade"):
            a = tr.attrib
            tid = a.get("tradeID") or a.get("ibExecID") or ""
            cur.execute(
                """INSERT INTO verified_trades
                   (account_id, strategy, trade_id, symbol, asset_type, description,
                    trade_date, settle_date, trade_time, quantity, trade_price,
                    proceeds, commission, net_cash, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, trade_id) DO NOTHING""",
                (account_id, strategy, tid, a.get("symbol", ""), a.get("assetCategory", ""),
                 a.get("description", ""), a.get("tradeDate") or None, a.get("settleDateTarget") or None,
                 (a.get("tradeDate", "")[:8] + " " + a.get("tradeTime", "")).strip() or None,
                 _f(a.get("quantity")), _f(a.get("tradePrice")),
                 _f(a.get("proceeds")), _f(a.get("ibCommission")), _f(a.get("netCash")),
                 json.dumps(dict(a))),
            )
            counts["trades"] += cur.rowcount

        for p in root.iter("OpenPosition"):
            a = p.attrib
            cur.execute(
                """INSERT INTO verified_positions
                   (account_id, strategy, as_of, symbol, asset_type, quantity,
                    mark_price, position_value, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, as_of, symbol) DO UPDATE SET
                     quantity=excluded.quantity, mark_price=excluded.mark_price,
                     position_value=excluded.position_value, raw=excluded.raw,
                     pulled_at=now()""",
                (account_id, strategy, today, a.get("symbol", ""), a.get("assetCategory", ""),
                 _f(a.get("position")), _f(a.get("markPrice")), _f(a.get("positionValue")),
                 json.dumps(dict(a))),
            )
            counts["positions"] += 1

        # NAV: use the ending value from the Net Asset Value section if present.
        # Deposits/withdrawals from the CashReport are REQUIRED: the public
        # equity curve is unit-accounted (NAV-per-unit), so cash movements must
        # be separable from P&L or added capital would look like performance.
        nav_val, cash_val, nav_raw = None, None, {}
        deposits, withdrawals = None, None
        for eq in root.iter("EquitySummaryByReportDateInBase"):
            a = eq.attrib
            if a.get("reportDate"):
                nav_val = _f(a.get("total"))
                nav_raw = dict(a)
        for cs in root.iter("CashReportCurrency"):
            a = cs.attrib
            if a.get("currency") == "BASE_SUMMARY":
                cash_val = _f(a.get("endingCash"))
                deposits = _f(a.get("deposits"))
                withdrawals = _f(a.get("withdrawals"))
                break
        if nav_val is not None:
            cur.execute(
                """INSERT INTO verified_nav (account_id, strategy, as_of, nav, cash, deposits, withdrawals, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, as_of) DO UPDATE SET
                     nav=excluded.nav, cash=excluded.cash, deposits=excluded.deposits,
                     withdrawals=excluded.withdrawals, raw=excluded.raw, pulled_at=now()""",
                (account_id, strategy, today, nav_val, cash_val, deposits, withdrawals, json.dumps(nav_raw)),
            )
            counts["nav"] += 1

    conn.commit()
    return counts


def pull_account(conn, token: str, query_id: str, account_id: str, strategy: str, raw_dir: Path) -> dict:
    started = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO flex_pull_log (account_id, started_at, status) VALUES (%s,%s,%s) RETURNING id",
                    (account_id, started, "STARTED"))
        log_id = cur.fetchone()[0]
    conn.commit()
    try:
        ref = request_statement(token, query_id)
        xml_bytes = fetch_statement(token, ref)
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{account_id}_{started.date().isoformat()}.xml").write_bytes(xml_bytes)
        counts = parse_and_store(conn, account_id, strategy, xml_bytes)
        status, detail = "OK", json.dumps(counts)
    except Exception as e:
        status, detail, counts = "ERROR", str(e)[:500], {}
        log.exception("pull failed for %s", account_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE flex_pull_log SET finished_at=now(), status=%s, detail=%s WHERE id=%s",
                    (status, detail, log_id))
    conn.commit()
    return {"account": account_id, "status": status, **counts}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    smoke = "--smoke" in sys.argv

    conn = _db_connect()
    init_schema(conn)
    log.info("schema ensured")

    if smoke:
        # Parser smoke test on a synthetic minimal statement
        sample = b"""<FlexQueryResponse queryName="t" type="AF"><FlexStatements count="1"><FlexStatement accountId="U999" fromDate="2026-01-01" toDate="2026-08-24" whenGenerated="2026-08-24;21:00:00">
<Trades><Trade accountId="U999" tradeID="12345" assetCategory="STK" symbol="QQQ" description="ISHARES" tradeDate="20260824" settleDateTarget="20260825" tradeTime="093001" quantity="10" tradePrice="700.00" proceeds="-7000" ibCommission="-1.00" netCash="-7001"/></Trades>
<OpenPositions><OpenPosition accountId="U999" assetCategory="STK" symbol="QQQ" position="10" markPrice="701.00" positionValue="7010"/></OpenPositions>
<EquitySummaryInBase><EquitySummaryByReportDateInBase accountId="U999" reportDate="20260824" total="25000"/></EquitySummaryInBase>
<CashReport><CashReportCurrency accountId="U999" currency="BASE_SUMMARY" endingCash="18000"/></CashReport>
</FlexStatement></FlexStatements></FlexQueryResponse>"""
        counts = parse_and_store(conn, "SMOKE_TEST", "TEST", sample)
        log.info("smoke parse: %s", counts)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM verified_trades WHERE account_id='SMOKE_TEST'")
            cur.execute("DELETE FROM verified_positions WHERE account_id='SMOKE_TEST'")
            cur.execute("DELETE FROM verified_nav WHERE account_id='SMOKE_TEST'")
        conn.commit()
        log.info("smoke rows cleaned up")
        return 0

    # Per-login tokens with FLEX_TOKEN fallback: two separate IB logins each
    # mint their own token, so allow FLEX_TOKEN_LEAPS / FLEX_TOKEN_BASIC.
    queries = [
        ("FLEX_QUERY_LEAPS", "QQQ_LEAPS", _env("FLEX_TOKEN_LEAPS") or _env("FLEX_TOKEN")),
        ("FLEX_QUERY_BASIC", "QQQ_BASIC", _env("FLEX_TOKEN_BASIC") or _env("FLEX_TOKEN")),
    ]

    raw_dir = Path(_env("FLEX_RAW_DIR", str(Path.home() / "flex_raw")))
    results = []
    for env_name, strategy, token in queries:
        qid = _env(env_name)
        acct = _env(env_name + "_ACCOUNT")
        if not qid:
            log.info("%s not set - skipping %s", env_name, strategy)
            continue
        if not token:
            log.error("No Flex token for %s (set FLEX_TOKEN_%s or FLEX_TOKEN)", strategy, strategy.split("_")[-1])
            results.append({"account": strategy, "status": "ERROR"})
            continue
        results.append(pull_account(conn, token, qid, acct or env_name, strategy, raw_dir))

    for r in results:
        log.info("result: %s", r)
    conn.close()
    return 0 if all(r["status"] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
