import sys
sys.path.append(r'd:\Projects\tastywork-trading-1')

from signal_publisher.turbocore import publish_turbocore_rebalance_signal
from datetime import datetime

now = datetime.utcnow().strftime('%H:%M UTC')

print(f"Publishing TQQQ_TURBOCORE signal at {now}...")
publish_turbocore_rebalance_signal(
    regime='BULL',
    confidence=0.87,
    alloc_dict={'QQQ': 0.50, 'QLD': 0.20, 'SGOV': 0.30},
    rationale=f'Manual re-generate {now}',
    ema_signal=1,
    sma200_gate=True,
    strategy='TQQQ_TURBOCORE'
)
print("CORE done.")

print(f"Publishing TQQQ_TURBOCORE_PRO signal at {now}...")
publish_turbocore_rebalance_signal(
    regime='BULL',
    confidence=0.95,
    alloc_dict={'QQQ': 0.50, 'QLD': 0.20, 'QQQ_LEAPS': 0.25, 'SGOV': 0.05},
    rationale=f'Manual re-generate PRO {now}',
    ema_signal=1,
    sma200_gate=True,
    strategy='TQQQ_TURBOCORE_PRO'
)
print("PRO done.")
