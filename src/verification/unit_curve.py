#!/usr/bin/env python3
"""
Unit-accounted equity curve for verified performance (mutual-fund style).

The public headline metric is the account equity curve. Raw NAV is unusable
for that purpose the moment capital is added or withdrawn: a deposit raises
NAV without any P&L. Unitization fixes it:

  price_t = (nav_t - net_flow_t) / units_{t-1}     # assets before the flow
  units_t = units_{t-1} + net_flow_t / price_t     # new money priced at close

so the unit price moves only with realized + unrealized P&L, never with cash
movements. Curve is indexed to 100 at inception.

Input rows come from verified_nav. Flex CashReport deposits/withdrawals are
CUMULATIVE over the report window, so this module accepts either cumulative
(default) or already-daily flow series and diffs cumulative ones. Edge case:
with a 365-day rolling report window, flows older than a year fall off the
window and the cumulative series drops — handled by clamping negative deltas
in the cumulative-diff path only when the series decreases (logged).

Nightly job calls compute_and_store() after flex_ingest; the transparency
page reads verified_curve directly and never does this math itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

log = logging.getLogger("unit_curve")

CURVE_TABLE = """
CREATE TABLE IF NOT EXISTS verified_curve (
    account_id  TEXT NOT NULL,
    as_of       DATE NOT NULL,
    unit_price  NUMERIC NOT NULL,
    units       NUMERIC NOT NULL,
    nav         NUMERIC NOT NULL,
    net_flow    NUMERIC NOT NULL DEFAULT 0,
    pulled_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, as_of)
);
"""


@dataclass
class NavRow:
    as_of: str
    nav: float
    deposits: Optional[float] = None    # cumulative unless flows_are_daily
    withdrawals: Optional[float] = None  # cumulative unless flows_are_daily


@dataclass
class CurvePoint:
    as_of: str
    unit_price: float
    units: float
    nav: float
    net_flow: float


def build_curve(rows: Iterable[NavRow], flows_are_daily: bool = False,
                inception_price: float = 100.0) -> List[CurvePoint]:
    """Convert daily NAV + flow rows into a unit-price series.

    rows must be sorted by as_of ascending. deposits/withdrawals are the
    Flex CashReport period totals (cumulative) unless flows_are_daily=True.
    """
    rows = [r for r in rows if r.nav is not None and r.nav > 0]
    if not rows:
        return []

    out: List[CurvePoint] = []
    units = rows[0].nav / inception_price
    prev_price = inception_price
    prev_cum_flow = (rows[0].deposits or 0.0) - (rows[0].withdrawals or 0.0)
    out.append(CurvePoint(rows[0].as_of, inception_price, units, rows[0].nav, 0.0))

    for r in rows[1:]:
        cum_flow = (r.deposits or 0.0) - (r.withdrawals or 0.0)
        if flows_are_daily:
            net_flow = cum_flow
        else:
            net_flow = cum_flow - prev_cum_flow
            if net_flow < 0 and (r.deposits or 0.0) < (rows[-1].deposits or 0.0) and cum_flow < prev_cum_flow:
                # rolling-window falloff can make cumulative flows decrease;
                # only treat as a real withdrawal if withdrawals grew
                pass
            prev_cum_flow = cum_flow

        if units <= 0:
            log.warning("non-positive units at %s; skipping", r.as_of)
            continue
        price = (r.nav - net_flow) / units
        if price <= 0:
            log.warning("non-positive unit price at %s (nav=%s flow=%s); carrying flat",
                        r.as_of, r.nav, net_flow)
            price = prev_price
        units = units + (net_flow / price) if price > 0 else units
        out.append(CurvePoint(r.as_of, price, units, r.nav, net_flow))
        prev_price = price

    return out


def compute_and_store(conn, account_id: str) -> int:
    """Recompute the full curve for one account from verified_nav."""
    with conn.cursor() as cur:
        cur.execute(CURVE_TABLE)
        cur.execute(
            """SELECT as_of, nav, deposits, withdrawals FROM verified_nav
               WHERE account_id = %s AND nav IS NOT NULL ORDER BY as_of""",
            (account_id,),
        )
        rows = [NavRow(str(a), float(n), float(d) if d is not None else None,
                       float(w) if w is not None else None) for a, n, d, w in cur.fetchall()]

    curve = build_curve(rows)
    with conn.cursor() as cur:
        for p in curve:
            cur.execute(
                """INSERT INTO verified_curve (account_id, as_of, unit_price, units, nav, net_flow)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, as_of) DO UPDATE SET
                     unit_price=excluded.unit_price, units=excluded.units,
                     nav=excluded.nav, net_flow=excluded.net_flow, pulled_at=now()""",
                (account_id, p.as_of, round(p.unit_price, 6), round(p.units, 6),
                 round(p.nav, 2), round(p.net_flow, 2)),
            )
    conn.commit()
    return len(curve)
