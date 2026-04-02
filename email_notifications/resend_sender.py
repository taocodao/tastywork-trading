"""
Resend email sender for TurboCore/TurboCore Pro signal alerts.
Called from signal_publisher/turbocore.py immediately after save_signal().

Install: pip install resend
Env var: RESEND_API_KEY=re_...
"""

import os
import re
import logging
from typing import List, Dict

import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_ADDRESS   = os.getenv("SIGNAL_EMAIL_FROM", "TradeMind Signals <signals@trademind.bot>")
APP_URL        = "https://trademind.bot"


# ── OCC Symbol Parser ─────────────────────────────────────────────────────────
# Input:  "QQQ   260515C00622000"
# Output: { underlying: "QQQ", expiry: "May 15, 2026", type: "Call", strike: "$622", raw: "..." }

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def parse_occ(raw: str) -> dict:
    """Parse a 21-char OCC symbol into human-readable components."""
    s = raw.replace(' ', '').strip()
    m = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', s)
    if not m:
        return {"raw": raw.strip(), "display": raw.strip(), "underlying": raw.strip(),
                "expiry": "—", "type": "—", "strike": "—"}
    und, yymmdd, cp, strike_raw = m.groups()
    year   = "20" + yymmdd[:2]
    month  = int(yymmdd[2:4])
    day    = int(yymmdd[4:6])
    expiry = f"{MONTHS[month-1]} {day}, {year}"
    strike = f"${int(strike_raw) / 1000:.0f}"
    return {
        "raw":        raw.strip(),
        "display":    f"{und} {expiry} {strike} {'Call' if cp == 'C' else 'Put'}",
        "underlying": und,
        "expiry":     expiry,
        "type":       "Call" if cp == "C" else "Put",
        "strike":     strike,
    }


# ── Leg Helpers ───────────────────────────────────────────────────────────────

def _is_options_leg(leg: dict) -> bool:
    """True if this leg carries an OCC option symbol (> 6 non-space chars)."""
    return len((leg.get("symbol") or "").replace(" ", "")) > 6

ACTION_LABELS = {
    "BUY_TO_OPEN":   ("BTO", "#22c55e"),
    "SELL_TO_OPEN":  ("STO", "#ef4444"),
    "BUY_TO_CLOSE":  ("BTC", "#3b82f6"),
    "SELL_TO_CLOSE": ("STC", "#f59e0b"),
    "BUY":           ("BUY", "#22c55e"),
    "SELL":          ("SELL","#ef4444"),
}


# ── Main Entry Point ──────────────────────────────────────────────────────────

def notify_signal_subscribers(signal_data: dict, subscribers: List[Dict]) -> None:
    """
    Send a signal alert email to all subscribed users.

    Args:
        signal_data:  Full signal dict from publish_turbocore_rebalance_signal().
                      Must include 'legs', 'regime', 'confidence', 'action', 'cost',
                      'capital_required', 'rationale', 'strategy'.
        subscribers:  List of { email: str, first_name: str | None }
    """
    if not subscribers:
        logger.info("[Resend] No subscribers — skipping.")
        return
    if not resend.api_key:
        logger.warning("[Resend] RESEND_API_KEY not set — skipping email.")
        return

    strategy      = signal_data.get("strategy", "")
    regime        = signal_data.get("regime", "—")
    confidence    = int(float(signal_data.get("confidence", 0)) * 100)
    action        = signal_data.get("action", "REBALANCE")
    legs          = signal_data.get("legs", [])
    limit_price   = float(signal_data.get("cost", 0) or 0)
    capital_req   = float(signal_data.get("capital_required", 0) or 0)
    rationale     = signal_data.get("rationale", "")
    strategy_label = "TurboCore Pro" if "PRO" in strategy else "TurboCore"
    subject        = f"📊 {strategy_label} Signal — {regime} ({confidence}% confidence)"

    sent = failed = 0
    for sub in subscribers:
        email      = sub.get("email")
        first_name = sub.get("first_name") or "Trader"
        if not email:
            continue
        try:
            resend.Emails.send({
                "from":    FROM_ADDRESS,
                "to":      [email],
                "subject": subject,
                "html":    _html(first_name, strategy_label, regime, confidence,
                                 action, legs, limit_price, capital_req, rationale),
                "text":    _text(strategy_label, regime, confidence, action,
                                 legs, limit_price, capital_req, rationale),
            })
            sent += 1
            logger.info(f"[Resend] Sent to {email}")
        except Exception as e:
            failed += 1
            logger.error(f"[Resend] Failed for {email}: {e}")

    logger.info(f"[Resend] Done — sent={sent} failed={failed}")


# ── HTML Builder ──────────────────────────────────────────────────────────────

ACTION_EMOJI = {
    "REBALANCE":       "🔄 Portfolio Rebalance",
    "OPEN_CSP":        "🛡️ Cash-Secured Put",
    "OPEN_ZEBRA":      "📈 ZEBRA Spread",
    "OPEN_ZEBRA_D3":   "📈 Crash Recovery ZEBRA",
    "OPEN_CCS":        "🐻 Bear Call Spread",
    "OPEN_SQQQ":       "⚡ Crash Hedge (SQQQ)",
    "CLOSE_POSITIONS": "🚪 Exit — Close Position",
    "NO_ACTION":       "⏸️ Hold — No Action",
}

REGIME_COLOR = {
    "BULL":     "#22c55e",
    "BEAR":     "#ef4444",
    "SIDEWAYS": "#f59e0b",
    "NEUTRAL":  "#a855f7",
}

def _html(first_name, strategy_label, regime, confidence,
          action, legs, limit_price, capital_req, rationale) -> str:

    rc              = REGIME_COLOR.get(regime, "#a855f7")
    action_display  = ACTION_EMOJI.get(action, action)
    equity_legs     = [l for l in legs if not _is_options_leg(l)]
    options_legs    = [l for l in legs if _is_options_leg(l)]

    # ── Equity allocation rows ────────────────────────────────────────────────
    equity_block = ""
    if equity_legs:
        rows = ""
        for leg in equity_legs:
            sym = (leg.get("symbol") or "").replace("_", "").strip()
            pct = leg.get("target_pct")
            pct_str = f"{int(pct * 100)}%" if pct is not None else "—"
            rows += f"""
            <tr>
              <td style="padding:9px 14px;color:#e5e7eb;font-weight:600;font-size:14px">{sym}</td>
              <td style="padding:9px 14px;color:#a855f7;font-weight:700;font-size:15px;text-align:right">{pct_str}</td>
            </tr>"""
        equity_block = f"""
        <p style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                  letter-spacing:0.06em;margin:0 0 8px">Target Allocation</p>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:rgba(139,92,246,0.06);border:1px solid rgba(139,92,246,0.18);
                      border-radius:10px;overflow:hidden;margin-bottom:22px">
          <thead>
            <tr style="background:rgba(0,0,0,0.25);border-bottom:1px solid rgba(255,255,255,0.06)">
              <th style="padding:7px 14px;color:#6b7280;font-size:10px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;font-weight:600">Symbol</th>
              <th style="padding:7px 14px;color:#6b7280;font-size:10px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:right;font-weight:600">Target %</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    # ── Options legs rows ─────────────────────────────────────────────────────
    options_block = ""
    if options_legs:
        rows = ""
        for leg in options_legs:
            act         = (leg.get("action") or "").upper()
            badge, color = ACTION_LABELS.get(act, (act[:3], "#9ca3af"))
            qty         = leg.get("qty") or leg.get("quantity") or 1
            parsed      = parse_occ(leg.get("symbol") or "")
            rows += f"""
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
              <td style="padding:11px 14px">
                <span style="background:{color}22;color:{color};border:1px solid {color}44;
                             font-size:9px;font-weight:700;padding:3px 7px;border-radius:4px;
                             font-family:monospace;letter-spacing:0.05em">{badge}</span>
              </td>
              <td style="padding:11px 8px">
                <p style="margin:0;color:#e5e7eb;font-weight:600;font-size:14px">
                  {parsed['underlying']} {parsed['strike']} {parsed['type']}
                </p>
                <p style="margin:3px 0 0;color:#6b7280;font-family:monospace;font-size:10px">
                  Exp {parsed['expiry']}
                </p>
              </td>
              <td style="padding:11px 14px;text-align:right;white-space:nowrap">
                <p style="margin:0;color:#e5e7eb;font-weight:700;font-size:13px">×{qty} contracts</p>
                <p style="margin:3px 0 0;color:#4b5563;font-family:monospace;font-size:9px">{parsed['raw']}</p>
              </td>
            </tr>"""

        spread_row = ""
        if limit_price != 0:
            cd       = "Credit" if limit_price > 0 else "Debit"
            cd_color = "#22c55e" if limit_price > 0 else "#ef4444"
            spread_row = f"""
            <tr style="border-top:1px solid rgba(139,92,246,0.2);background:rgba(139,92,246,0.05)">
              <td colspan="3" style="padding:10px 14px">
                <span style="color:#9ca3af;font-size:12px">
                  Net {cd}:&nbsp;
                  <strong style="color:{cd_color}">${abs(limit_price):.2f}/contract</strong>
                  &nbsp;·&nbsp;Capital required:&nbsp;
                  <strong style="color:#e5e7eb">${capital_req:,.0f}</strong>
                </span>
              </td>
            </tr>"""

        options_block = f"""
        <p style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                  letter-spacing:0.06em;margin:0 0 8px">Options Overlay — Order Legs</p>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.07);
                      border-radius:10px;overflow:hidden;margin-bottom:22px">
          <thead>
            <tr style="background:rgba(0,0,0,0.25);border-bottom:1px solid rgba(255,255,255,0.06)">
              <th style="padding:7px 14px;color:#6b7280;font-size:10px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;font-weight:600">Action</th>
              <th style="padding:7px 8px;color:#6b7280;font-size:10px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;font-weight:600">Contract</th>
              <th style="padding:7px 14px;color:#6b7280;font-size:10px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:right;font-weight:600">Qty</th>
            </tr>
          </thead>
          <tbody>
            {rows}
            {spread_row}
          </tbody>
        </table>"""

    rationale_block = ""
    if rationale:
        rationale_block = f"""
        <p style="background:rgba(0,0,0,0.2);border-left:3px solid rgba(139,92,246,0.4);
                  border-radius:0 8px 8px 0;padding:10px 14px;font-size:12px;
                  color:#6b7280;margin:0 0 22px;line-height:1.7">{rationale}</p>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>TradeMind Signal Alert</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0f;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#0a0a0f;padding:32px 16px">
  <tr><td>
  <table width="600" cellpadding="0" cellspacing="0" border="0" align="center"
         style="max-width:600px;background:linear-gradient(135deg,#0f0f19,#141425);
                border:1px solid rgba(139,92,246,0.22);border-radius:16px;overflow:hidden">

    <!-- ─ Header ─ -->
    <tr>
      <td style="background:linear-gradient(90deg,#6d28d9,#a855f7);padding:22px 30px">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td>
            <span style="font-size:21px;font-weight:800;color:#fff;letter-spacing:-0.5px">TradeMind</span><br>
            <span style="font-size:12px;color:rgba(255,255,255,0.65)">{strategy_label} · Daily Signal Alert</span>
          </td>
          <td align="right">
            <span style="background:rgba(0,0,0,0.3);color:#fff;padding:5px 13px;
                         border-radius:20px;font-size:13px;font-weight:700;
                         letter-spacing:0.03em">{regime}</span>
          </td>
        </tr></table>
      </td>
    </tr>

    <!-- ─ Body ─ -->
    <tr><td style="padding:26px 30px">

      <p style="color:#9ca3af;font-size:15px;margin:0 0 5px">Hi {first_name},</p>
      <p style="color:#e5e7eb;font-size:15px;margin:0 0 22px">
        Your <strong style="color:#a855f7">{strategy_label}</strong> signal is ready:
        <span style="color:{rc};font-weight:600"> {action_display}</span>
      </p>

      <!-- ─ Summary Stats ─ -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:rgba(139,92,246,0.07);border:1px solid rgba(139,92,246,0.18);
                    border-radius:12px;margin-bottom:24px">
        <tr>
          <td style="padding:13px 16px;border-right:1px solid rgba(139,92,246,0.15);text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:600;
                      text-transform:uppercase;letter-spacing:0.06em">Regime</p>
            <p style="margin:5px 0 0;color:{rc};font-weight:800;font-size:19px">{regime}</p>
          </td>
          <td style="padding:13px 16px;border-right:1px solid rgba(139,92,246,0.15);text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:600;
                      text-transform:uppercase;letter-spacing:0.06em">ML Confidence</p>
            <p style="margin:5px 0 0;color:#a855f7;font-weight:800;font-size:19px">{confidence}%</p>
          </td>
          <td style="padding:13px 16px;text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:600;
                      text-transform:uppercase;letter-spacing:0.06em">Capital Req.</p>
            <p style="margin:5px 0 0;color:#e5e7eb;font-weight:800;font-size:19px">
              ${capital_req:,.0f}
            </p>
          </td>
        </tr>
      </table>

      {equity_block}
      {options_block}
      {rationale_block}

      <!-- ─ CTA ─ -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding-top:4px">
          <a href="{APP_URL}/signals"
             style="display:inline-block;background:linear-gradient(90deg,#6d28d9,#a855f7);
                    color:#fff;padding:14px 38px;border-radius:10px;text-decoration:none;
                    font-weight:700;font-size:15px;letter-spacing:0.01em">
            Execute Signal →
          </a>
        </td></tr>
      </table>
    </td></tr>

    <!-- ─ Footer ─ -->
    <tr>
      <td style="padding:18px 30px;border-top:1px solid rgba(255,255,255,0.05);text-align:center">
        <p style="color:#374151;font-size:11px;margin:0 0 4px">TradeMind · Automated Trade Signals</p>
        <p style="color:#374151;font-size:11px;margin:0">
          <a href="{APP_URL}/settings" style="color:#4b5563;text-decoration:underline">
            Manage email preferences
          </a>
        </p>
      </td>
    </tr>
  </table>
  </td></tr>
</table>
</body>
</html>"""


# ── Plain-Text Fallback ───────────────────────────────────────────────────────

def _text(strategy_label, regime, confidence, action,
          legs, limit_price, capital_req, rationale) -> str:
    equity_legs  = [l for l in legs if not _is_options_leg(l)]
    options_legs = [l for l in legs if _is_options_leg(l)]

    lines = [
        f"TradeMind — {strategy_label} Signal Alert",
        "=" * 46,
        f"Regime:           {regime}",
        f"ML Confidence:    {confidence}%",
        f"Action:           {action}",
        f"Capital Required: ${capital_req:,.0f}",
        "",
    ]

    if equity_legs:
        lines += ["TARGET ALLOCATION", "-" * 22]
        for leg in equity_legs:
            sym = (leg.get("symbol") or "").replace("_", "").strip()
            pct = leg.get("target_pct")
            lines.append(f"  {sym:<8}  {int(pct*100)}%" if pct is not None else f"  {sym}")
        lines.append("")

    if options_legs:
        lines += ["OPTIONS ORDER LEGS", "-" * 22]
        for leg in options_legs:
            act    = (leg.get("action") or "").upper()
            qty    = leg.get("qty") or leg.get("quantity") or 1
            parsed = parse_occ(leg.get("symbol") or "")
            lines.append(
                f"  {act:<18} {parsed['underlying']} {parsed['strike']} "
                f"{parsed['type']}  exp {parsed['expiry']}  ×{qty}"
            )
        if limit_price != 0:
            cd = "Credit" if limit_price > 0 else "Debit"
            lines.append(f"  Net {cd}: ${abs(limit_price):.2f}/contract")
        lines.append("")

    if rationale:
        lines += ["RATIONALE", "-" * 22, rationale, ""]

    lines += [
        f"Execute your signal: {APP_URL}/signals",
        f"Manage notifications: {APP_URL}/settings",
    ]
    return "\n".join(lines)
