import urllib.request
import json
import os

API_URL = 'http://34.235.119.67:8002/api'

print(f"Fetching signals from {API_URL}/signals...")
req = urllib.request.Request(f'{API_URL}/signals')
res = urllib.request.urlopen(req)
data = json.loads(res.read().decode('utf-8'))

nugt_signals = [s for s in data.get('signals', []) if 'nugt' in s['id'].lower()]
if not nugt_signals:
    print('NUGT test signal not found in DB! Make sure you ran submit_test_turbobounce_signal.py')
    exit()

signal = nugt_signals[0]
signal_id = signal['id']
print(f'Found test signal: {signal_id}')
print(json.dumps(signal, indent=2))

# Mock frontend payload to trigger auto-approve
payload = {
    'execute': True,
    'signal': signal,
    'source': 'auto_approve',
    # Tastytrade session credentials are required for actual execution
    # If invalid, the backend will catch and report the error, which still proves the routing works
    'refreshToken': 'backend-test-token',
    'accountNumber': 'test-account',
    'userId': 'backend-test-user'
}

print('\nSending execution approval request...')
try:
    req = urllib.request.Request(
        f'{API_URL}/signals/{signal_id}/approve',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    res = urllib.request.urlopen(req)
    response_data = json.loads(res.read().decode('utf-8'))
    print('\n✅ Response from Server:')
    print(json.dumps(response_data, indent=2))
except urllib.error.HTTPError as e:
    print(f'\n❌ Error {e.code}:')
    try:
        err_data = json.loads(e.read().decode('utf-8'))
        print(json.dumps(err_data, indent=2))
    except (json.JSONDecodeError, AttributeError):
        print(e.read().decode("utf-8") if hasattr(e, 'read') else str(e))
except Exception as e:
    print(f'\n❌ Unexpected Error: {type(e).__name__} - {e}')
