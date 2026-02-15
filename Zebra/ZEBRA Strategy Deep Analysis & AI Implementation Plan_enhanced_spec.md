<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# yes

Here’s the structured design doc with explicit data schemas, APIs, and workflows that Antigravity can build from directly. It’s aligned 1:1 with the logic in your ZEBRA PDF and the enhancements we discussed.[^1]

***

## 1. Core data models

### 1.1 TradeCandidate

Represents a stock selected by the ML engine as a ZEBRA candidate.

```json
TradeCandidate {
  "symbol": "string",
  "direction": "LONG | SHORT",
  "directional_confidence": "number",     // 0–100
  "expected_move_pct": "number",          // 30‑day expected move
  "liquidity_score": "number",            // 0–100
  "capital_efficiency": "number",         // delta per $ vs stock
  "anti_crowding_score": "number",        // 0–100
  "composite_score": "number",            // ranking score
  "thesis_horizon_days": "integer",       // e.g. 30, 90
  "rationale": "string"                   // human‑readable explanation
}
```


### 1.2 ZebraStructure

Represents a fully specified ZEBRA trade.

```json
ZebraStructure {
  "symbol": "string",
  "direction": "LONG | SHORT",
  "expiry": "YYYY-MM-DD",
  "legs": [
    {
      "type": "CALL | PUT",
      "side": "BUY | SELL",
      "strike": "number",
      "quantity": "integer",
      "delta": "number"
    }
  ],
  "net_debit": "number",
  "max_loss": "number",
  "breakeven_price": "number",
  "net_delta": "number",
  "net_theta": "number",
  "net_vega": "number",
  "capital_efficiency": "number",
  "net_extrinsic": "number",
  "construction_score": "number",
  "slippage_flag": "boolean"
}
```


### 1.3 OrderRequest

Abstraction over Tastytrade orders.

```json
OrderRequest {
  "broker": "TASTYTRADE",
  "type": "ZEBRA_OPEN | ZEBRA_CLOSE | ZEBRA_ROLL | OVERLAY_OPEN | HEDGE_OPEN",
  "zebra_id": "string | null",
  "structure": "ZebraStructure | null",
  "limit_price": "number",
  "max_slippage_pct": "number",   // e.g. 3.0 = 3%
  "time_in_force": "DAY | GTC"
}
```


### 1.4 Position / ZebraPosition

```json
ZebraPosition {
  "zebra_id": "string",
  "symbol": "string",
  "direction": "LONG | SHORT",
  "structure": "ZebraStructure",
  "entry_time": "ISO-8601",
  "entry_debit": "number",
  "initial_dte": "integer",
  "directional_confidence_at_entry": "number",
  "anti_crowding_score_at_entry": "number",
  "status": "OPEN | CLOSING | CLOSED",
  "metadata": {
    "reason_open": "string",
    "tags": ["string"]
  }
}
```


### 1.5 TradeLogEntry

```json
TradeLogEntry {
  "zebra_id": "string",
  "symbol": "string",
  "entry_time": "ISO-8601",
  "exit_time": "ISO-8601",
  "entry_debit": "number",
  "exit_credit": "number",
  "pnl_abs": "number",
  "pnl_pct": "number",
  "max_drawdown_pct": "number",
  "exit_reason": "PROFIT_TARGET | TIME_EXIT | STOP_LOSS | RECENTER_UP | RECENTER_DOWN | ASSIGNMENT_RISK | DIVIDEND_RISK",
  "directional_confidence_entry": "number",
  "realized_30d_move_pct": "number",
  "anti_crowding_score_entry": "number",
  "slippage_bps": "number"
}
```


***

## 2. Service layer \& APIs

### 2.1 Universe \& feature service

**Responsibilities**

- Build and maintain eligible universe (S\&P 500 + liquid mid‑caps with your filters).[^1]
- Expose feature vectors for ML.

**APIs**

- `GET /universe/daily`
    - Response:
        - `symbols: [ { symbol, adv, atm_spread, atm_oi } ]`
- `GET /features/{symbol}`
    - Response:
        - Price/technical indicators (RSI, MACD, MAs, ATR, volume trend).[^1]
        - Fundamentals (earnings surprise, growth, revisions, PE vs sector).[^1]
        - Options metrics (IV, IVR, skew, term structure, spreads, OI).[^1]
        - Flow \& sentiment (unusual activity, sweeps, dark pool, news/social NLP, insider).[^1]


### 2.2 ML signal engine

**APIs**

- `POST /signals/generate-daily`
    - Input: `as_of_date`.
    - Steps:
        - Pull `/universe/daily`.
        - For each symbol, call `/features/{symbol}`.
        - Run ensemble model → Directional Confidence \& expected move.[^1]
        - Compute liquidity, capital efficiency, anti‑crowding scores.[^1]
        - Compute composite score using your formula.[^1]
    - Output: `[TradeCandidate]` (sorted by composite_score desc).
- `GET /signals/candidates?limit=10`
    - Returns top N `TradeCandidate` with rationale strings.

***

## 3. ZEBRA construction engine

### 3.1 API

- `POST /zebra/construct`
    - Input:
        - `TradeCandidate`
        - config:
            - `max_debit_pct` (vs 100‑share cost).
            - `long_delta_range`: [0.65, 0.80].
            - `short_delta_range`: [0.45, 0.55].
    - Steps:

1. Determine expiry window using 2× horizon rule.[^1]
2. Pull full chain for candidate symbol (Tastytrade or data provider).
3. Filter expiries in target DTE and with adequate liquidity.
4. For each expiry and valid strike combination:
            - Compute extrinsic values, Net Extrinsic.[^1]
            - Compute Greeks, debit, max loss, breakeven, capital efficiency.[^1]
            - Compute Construction Score; check slippage spread ≤ 2% of debit.[^1]
5. Apply anti‑crowding module to penalize crowded strikes/expiries.[^1]
6. Select top 3 `ZebraStructure` for this symbol.
    - Output:
        - `structures: [ZebraStructure]` (top 3).
        - `best_structure: ZebraStructure`.

***

## 4. Anti‑crowding module

### 4.1 API

- `POST /anticrowding/evaluate`
    - Input:
        - `symbol`, candidate strikes/expiries, OI history, spread history, social metrics, options‑flow metrics.[^1]
    - Steps (mechanisms 1–6):
        - OI change detection for target strikes.[^1]
        - 20‑day spread anomaly detection.[^1]
        - Social/media spike detection for ZEBRA terms.[^1]
        - Strike parameter jitter within delta ranges.[^1]
        - Unusual institutional flow counter‑signals.[^1]
        - Expiration cycle rotation away from the most popular monthly.[^1]
    - Output:
        - `anti_crowding_score: number`
        - `crowding_flags: [string]`
        - `recommended_strike_adjustments: [...]`
        - `recommended_expiry_adjustment: ...`

This module is called during candidate scoring and again in construction to tweak strikes/expiries.

***

## 5. Tastytrade execution adapter

### 5.1 API

- `POST /broker/tastytrade/order`
    - Input: `OrderRequest`.
    - Adapter translates `ZebraStructure` into Tastytrade complex order syntax.
    - Execution logic:
        - Start at mid‑price.
        - Retry by ±0.05 increments up to 3% slippage, with 15‑minute timeout.[^1]
        - Time window 10:00–11:30 ET by default.[^1]
    - Output:
        - `order_id`, `status`, `fill_price`, `timestamp`, `reject_reason?`.
- `POST /broker/tastytrade/cancel`
    - Input: `order_id`.
- `GET /broker/tastytrade/order/{order_id}`
    - Latest status and fills.

***

## 6. Lifecycle \& risk engine

### 6.1 Position evaluation

- `POST /positions/evaluate`
    - Input: `ZebraPosition` + latest market/option data.
    - Steps:
        - Compute current P\&L vs entry_debit.[^1]
        - Compute Time Used = (now − entry_time) / initial_dte.[^1]
        - Compute net extrinsic drift.[^1]
        - Check assignment \& dividend calendars.[^1]
        - Apply decision tree thresholds.[^1]
    - Output:
        - `action`:
            - `HOLD | TAKE_PROFIT | TIME_EXIT | STOP_LOSS | RECENTER_UP | RECENTER_DOWN | ASSIGNMENT_EXIT | DIVIDEND_EXIT`.
        - `reason`: string.


### 6.2 Risk \& portfolio capacity

- `POST /portfolio/check-capacity`
    - Input: proposed `ZebraStructure` + current portfolio snapshot.
    - Checks: position count, sector concentration, correlation filter, delta budget, VIX regime rules.[^1]
    - Output: `allowed: boolean`, `reason`.


### 6.3 Execution of lifecycle actions

- `POST /positions/execute-action`
    - Input: `zebra_id`, `action`.
    - Maps actions to:
        - Close: `OrderRequest` with `ZEBRA_CLOSE`.
        - Re‑center: `ZEBRA_CLOSE` old + `ZEBRA_OPEN` new at adjusted strikes.[^1]
        - Roll short: specialized `ZEBRA_ROLL` order for short leg.[^1]

***

## 7. Analytics \& feedback loop

### 7.1 Trade logging

- `POST /analytics/log-trade`
    - Called after a ZEBRA is fully closed.
    - Persists `TradeLogEntry`.[^1]


### 7.2 Reporting

- `GET /analytics/overview`
    - Strategy‑level metrics: win rate, avg P\&L, Sharpe, max DD, avg holding period.[^1]
- `GET /analytics/model-performance`
    - Directional accuracy by confidence bucket and regime.[^1]
- `GET /analytics/anticrowding-impact`
    - P\&L comparison of crowded vs uncrowded entries.[^1]


### 7.3 Model retraining

- Cron job (weekly):
    - Pull all `TradeLogEntry` + feature histories.
    - Retrain ensemble models on rolling 2‑year window.[^1]
    - Feature importance / alpha‑decay analysis; mark deprecations.[^1]

***

## 8. Daily automation workflows

### 8.1 Morning

1. 07:30 – `signals/generate-daily` → list of `TradeCandidate`.[^1]
2. 08:00 – `anticrowding/evaluate` update for key strikes/expiries; update scores.[^1]
3. 09:45 – For top N candidates:
    - `/zebra/construct` → best structures.
    - `/portfolio/check-capacity` for each.
    - Prepare proposals for UI/agent.

### 8.2 Entry window

4. 10:00 – For approved trades (auto or user):
    - Build `OrderRequest` (ZEBRA_OPEN).
    - Send to `/broker/tastytrade/order`.

### 8.3 Intraday management

5. 10:15, 12:00, 14:00 – For each OPEN `ZebraPosition`:
    - `/positions/evaluate` → action.
    - If not HOLD, call `/positions/execute-action`.

### 8.4 End‑of‑day

6. 15:30 – Pre‑close sweep for expiring, assignment, dividend risk.[^1]
7. 16:15 – Sync fills, close statuses; call `/analytics/log-trade` for newly closed.
8. 17:00 – Generate daily report from `/analytics/*` and push via TradeMind.bot / email.

***

## 9. Optional ZEEHBS hedge flow

- Separate module with:
    - `POST /hedge/evaluate` → when \#ZEBRAs > threshold or VIX rising, suggest hedges.[^1]
    - `POST /hedge/execute` → synthetic short index orders via Tastytrade.[^1]

***

This spec gives Antigravity concrete types, endpoints, and workflows while staying true to your original ZEBRA deep‑analysis and AI design.[^1]

<div align="center">⁂</div>

[^1]: ZEBRA-Strategy-Deep-Analysis-AI-Implementation-Plan.pdf

