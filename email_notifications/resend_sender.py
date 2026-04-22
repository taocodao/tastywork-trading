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

import resend  # type: ignore

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_ADDRESS   = os.getenv("SIGNAL_EMAIL_FROM", "TradeMind Signals <signals@trademind.bot>")
APP_URL        = "https://trademind.bot"


# ── OCC Symbol Parser ─────────────────────────────────────────────────────────

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
    "BUY_TO_OPEN":   ("BTO", "buy"),
    "SELL_TO_OPEN":  ("STO", "sell"),
    "BUY_TO_CLOSE":  ("BTC", "buy"),
    "SELL_TO_CLOSE": ("STC", "sell"),
    "BUY":           ("BUY", "buy"),
    "SELL":          ("SELL","sell"),
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
    subject        = f"[TradeMind] {strategy_label} Signal — {regime} ({confidence}% Confidence)"

    sent = failed = 0
    for sub in subscribers:
        raw_email  = sub.get("email")
        first_name = sub.get("first_name") or "Trader"
        if not raw_email:
            continue
            
        emails = [e.strip() for e in raw_email.split(",") if '@' in e.strip()]
        for email in emails:
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


# ── HTML Builder — Clean Black & White ───────────────────────────────────────

ACTION_DISPLAY = {
    "REBALANCE":       "Portfolio Rebalance",
    "OPEN_CSP":        "Cash-Secured Put",
    "OPEN_ZEBRA":      "ZEBRA Spread",
    "OPEN_ZEBRA_D3":   "Crash Recovery ZEBRA",
    "OPEN_CCS":        "Bear Call Spread",
    "OPEN_SQQQ":       "Crash Hedge (SQQQ)",
    "CLOSE_POSITIONS": "Exit — Close Position",
    "NO_ACTION":       "Hold — No Action Required",
}

def _html(first_name, strategy_label, regime, confidence,
          action, legs, limit_price, capital_req, rationale) -> str:

    action_display  = ACTION_DISPLAY.get(action, action.replace("_", " ").title())
    equity_legs     = [l for l in legs if not _is_options_leg(l)]
    options_legs    = [l for l in legs if _is_options_leg(l)]

    # ── Equity allocation table ───────────────────────────────────────────────
    equity_block = ""
    if equity_legs:
        rows = ""
        for leg in equity_legs:
            sym = (leg.get("symbol") or "").replace("_", "").strip()
            pct = leg.get("target_pct")
            pct_str = f"{int(pct * 100)}%" if pct is not None else "—"
            rows += f"""
            <tr style="border-bottom:1px solid #e5e7eb">
              <td style="padding:10px 16px;color:#111827;font-size:14px;font-weight:600">{sym}</td>
              <td style="padding:10px 16px;color:#111827;font-weight:700;font-size:14px;text-align:right">{pct_str}</td>
            </tr>"""
        equity_block = f"""
        <p style="color:#374151;font-size:11px;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.07em;margin:0 0 8px">Target Allocation</p>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid #d1d5db;border-radius:8px;overflow:hidden;margin-bottom:24px;border-collapse:collapse">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:8px 16px;color:#6b7280;font-size:11px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;border-bottom:1px solid #d1d5db">Symbol</th>
              <th style="padding:8px 16px;color:#6b7280;font-size:11px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:right;border-bottom:1px solid #d1d5db">Target %</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    # ── Options legs table ────────────────────────────────────────────────────
    options_block = ""
    if options_legs:
        rows = ""
        for leg in options_legs:
            act          = (leg.get("action") or "").upper()
            badge, side  = ACTION_LABELS.get(act, (act[:3], "neutral"))
            badge_bg     = "#d1fae5" if side == "buy" else "#fee2e2"
            badge_color  = "#065f46" if side == "buy" else "#991b1b"
            qty          = leg.get("qty") or leg.get("quantity") or 1
            parsed       = parse_occ(leg.get("symbol") or "")
            rows += f"""
            <tr style="border-bottom:1px solid #e5e7eb">
              <td style="padding:10px 16px">
                <span style="background:{badge_bg};color:{badge_color};
                             font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;
                             font-family:monospace">{badge}</span>
              </td>
              <td style="padding:10px 8px">
                <p style="margin:0;color:#111827;font-weight:600;font-size:14px">
                  {parsed['underlying']} {parsed['strike']} {parsed['type']}
                </p>
                <p style="margin:3px 0 0;color:#6b7280;font-family:monospace;font-size:11px">
                  Exp {parsed['expiry']}
                </p>
              </td>
              <td style="padding:10px 16px;text-align:right;white-space:nowrap">
                <p style="margin:0;color:#111827;font-weight:600;font-size:13px">{qty} contracts</p>
                <p style="margin:3px 0 0;color:#9ca3af;font-family:monospace;font-size:10px">{parsed['raw']}</p>
              </td>
            </tr>"""

        spread_row = ""
        if limit_price != 0:
            cd       = "Credit" if limit_price > 0 else "Debit"
            cd_color = "#065f46" if limit_price > 0 else "#991b1b"
            spread_row = f"""
            <tr style="background:#f9fafb;border-top:1px solid #d1d5db">
              <td colspan="3" style="padding:10px 16px">
                <span style="color:#374151;font-size:12px">
                  Net {cd}: <strong style="color:{cd_color}">${abs(limit_price):.2f}/contract</strong>
                  &nbsp;&middot;&nbsp;Capital Required: <strong style="color:#111827">${capital_req:,.0f}</strong>
                </span>
              </td>
            </tr>"""

        options_block = f"""
        <p style="color:#374151;font-size:11px;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.07em;margin:0 0 8px">Options Overlay — Order Legs</p>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid #d1d5db;border-radius:8px;overflow:hidden;margin-bottom:24px;border-collapse:collapse">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:8px 16px;color:#6b7280;font-size:11px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;border-bottom:1px solid #d1d5db">Action</th>
              <th style="padding:8px 8px;color:#6b7280;font-size:11px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:left;border-bottom:1px solid #d1d5db">Contract</th>
              <th style="padding:8px 16px;color:#6b7280;font-size:11px;text-transform:uppercase;
                         letter-spacing:0.06em;text-align:right;border-bottom:1px solid #d1d5db">Qty</th>
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
        <p style="border-left:3px solid #d1d5db;padding:8px 14px;font-size:13px;
                  color:#6b7280;margin:0 0 24px;line-height:1.6;font-style:italic">{rationale}</p>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>TradeMind Signal Alert</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f3f4f6;padding:32px 16px">
  <tr><td>
  <table width="600" cellpadding="0" cellspacing="0" border="0" align="center"
         style="max-width:600px;background:#ffffff;border:1px solid #e5e7eb;
                border-radius:8px;overflow:hidden">

    <!-- Header -->
    <tr>
      <td style="background:#111827;padding:24px 32px">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td>
            <span style="font-size:20px;font-weight:800;color:#ffffff;letter-spacing:-0.5px">TradeMind</span><br>
            <span style="font-size:12px;color:#9ca3af">{strategy_label} &middot; Daily Signal Alert</span>
          </td>
          <td align="right">
            <span style="background:#374151;color:#f9fafb;padding:5px 14px;
                         border-radius:20px;font-size:13px;font-weight:700;
                         letter-spacing:0.03em">{regime}</span>
          </td>
        </tr></table>
      </td>
    </tr>

    <!-- Body -->
    <tr><td style="padding:28px 32px">

      <p style="color:#374151;font-size:15px;margin:0 0 6px">Hi {first_name},</p>
      <p style="color:#111827;font-size:15px;margin:0 0 24px;font-weight:500">
        Your <strong>{strategy_label}</strong> signal is ready: {action_display}
      </p>

      <!-- Summary Stats -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #e5e7eb;border-radius:8px;margin-bottom:28px;border-collapse:collapse">
        <tr>
          <td style="padding:14px 18px;border-right:1px solid #e5e7eb;text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.07em">Regime</p>
            <p style="margin:6px 0 0;color:#111827;font-weight:800;font-size:20px">{regime}</p>
          </td>
          <td style="padding:14px 18px;border-right:1px solid #e5e7eb;text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.07em">ML Confidence</p>
            <p style="margin:6px 0 0;color:#111827;font-weight:800;font-size:20px">{confidence}%</p>
          </td>
          <td style="padding:14px 18px;text-align:center">
            <p style="margin:0;color:#6b7280;font-size:10px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.07em">Capital Req.</p>
            <p style="margin:6px 0 0;color:#111827;font-weight:800;font-size:20px">
              ${capital_req:,.0f}
            </p>
          </td>
        </tr>
      </table>

      {equity_block}
      {options_block}
      {rationale_block}

      <!-- CTA -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding-top:8px">
          <a href="{APP_URL}/signals"
             style="display:inline-block;background:#111827;
                    color:#ffffff;padding:14px 40px;border-radius:6px;text-decoration:none;
                    font-weight:700;font-size:15px;letter-spacing:0.01em">
            View Your Dashboard &rarr;
          </a>
        </td></tr>
      </table>
    </td></tr>

    <!-- Footer -->
    <tr>
      <td style="padding:18px 32px;border-top:1px solid #e5e7eb;background:#f9fafb;text-align:center">
        <p style="color:#9ca3af;font-size:11px;margin:0 0 4px">TradeMind &middot; Automated Trade Signals</p>
        <p style="color:#9ca3af;font-size:11px;margin:0">
          <a href="{APP_URL}/settings" style="color:#6b7280;text-decoration:underline">
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
    action_display = ACTION_DISPLAY.get(action, action.replace("_", " ").title())

    lines = [
        f"TradeMind — {strategy_label} Signal Alert",
        "=" * 46,
        f"Regime:           {regime}",
        f"ML Confidence:    {confidence}%",
        f"Action:           {action_display}",
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
                f"{parsed['type']}  exp {parsed['expiry']}  x{qty}"
            )
        if limit_price != 0:
            cd = "Credit" if limit_price > 0 else "Debit"
            lines.append(f"  Net {cd}: ${abs(limit_price):.2f}/contract")
        lines.append("")

    if rationale:
        lines += ["RATIONALE", "-" * 22, rationale, ""]

    lines += [
        f"View your dashboard: {APP_URL}/signals",
        f"Manage notifications: {APP_URL}/settings",
    ]
    return "\n".join(lines)
