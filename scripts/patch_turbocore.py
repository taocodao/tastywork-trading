#!/usr/bin/env python3
"""Patch turbocore.py to add the Vercel bridge call."""
import re

fp = 'd:/Projects/tastywork-trading-1/signal_publisher/turbocore.py'
content = open(fp, encoding='utf-8').read()

# Find the block to replace
old_marker = '# \u2500\u2500 Post to Whop Signal Alerts channel (non-fatal)'
if old_marker not in content:
    print(f'ERROR: marker not found. First 20 chars of file: {repr(content[:50])}')
    exit(1)

# Find position and replace the entire whop block
idx = content.index(old_marker)
# Find the end of the block (the empty line before 'finally:')
end_idx = content.index('\n        finally:', idx)

old_block = content[idx:end_idx]
print('Old block:')
print(old_block[:200])
print('---')

new_block = '''# \u2500\u2500 Post to Whop Signal Alerts channel (non-fatal) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            try:
                _post_signal_to_whop(data)
            except Exception as whop_err:
                logger.warning(f"[Whop] Channel post failed (non-fatal): {whop_err}")

            # \u2500\u2500 Vercel bridge: push notifications + audit log \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            # Calls /api/internal/publish-to-whop to send push notifications
            # to all paid experience IDs and write to whop_posts audit table.
            if not data.get("iv_switching_pending"):
                try:
                    import requests as _rq, os as _os
                    from datetime import datetime as _dt, timezone as _tz
                    _base = "https://trademind.bot"
                    _sec  = _os.environ.get("INTERNAL_API_SECRET", "dev_secret_key")
                    _legs = {
                        leg.get("symbol", ""): leg.get("target_pct", 0)
                        for leg in data.get("legs", [])
                        if leg.get("target_pct") is not None
                    }
                    _payload = {
                        "regime":     data.get("regime", "SIDEWAYS"),
                        "confidence": int(float(data.get("confidence", 0.5)) * 100),
                        "allocation": {
                            "QQQ":  int(_legs.get("QQQ",  _legs.get("qqq",  0))),
                            "QLD":  int(_legs.get("QLD",  _legs.get("qld",  0))),
                            "TQQQ": int(_legs.get("TQQQ", _legs.get("tqqq", 0))),
                            "SGOV": int(_legs.get("SGOV", _legs.get("sgov", 0))),
                        },
                        "reasoning": data.get("rationale", "")[:500],
                        "date":      _dt.now(_tz.utc).strftime("%Y-%m-%d"),
                    }
                    _r = _rq.post(
                        f"{_base}/api/internal/publish-to-whop",
                        json=_payload,
                        headers={{"Authorization": f"Bearer {_sec}", "Content-Type": "application/json"}},
                        timeout=8,
                    )
                    if _r.ok:
                        logger.info(f"[Whop Bridge] Push + audit done ({_r.status_code})")
                    else:
                        logger.warning(f"[Whop Bridge] {_r.status_code}: {_r.text[:200]}")
                except Exception as _be:
                    logger.warning(f"[Whop Bridge] Non-fatal: {_be}")
            '''

new_content = content[:idx] + new_block + content[end_idx:]
open(fp, 'w', encoding='utf-8').write(new_content)
print('Patch applied successfully.')
print('New lines around insertion:')
lines = new_content.split('\n')
# Find the bridge line
for i, line in enumerate(lines):
    if 'Vercel bridge' in line:
        print(f'Line {i+1}: {line}')
        break
