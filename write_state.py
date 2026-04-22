#!/usr/bin/env python3
"""Write today's date to both scheduler state files to prevent re-firing."""
import json
from datetime import date

today = date.today().isoformat()

paths = [
    '/home/ubuntu/tastywork-trading/data/last_scan_state.json',
    '/home/ubuntu/tastywork-trading/data/last_scan_state_pro.json',
]

for path in paths:
    with open(path, 'w') as f:
        json.dump({'last_scan_date': today}, f)
    content = open(path).read()
    print(f"Written to {path}: {content}")

print("Done — both schedulers will see today's date and not re-fire.")
