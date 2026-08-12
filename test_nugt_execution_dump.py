import urllib.request
import json

API_URL = 'http://34.203.194.137:8002/api'

req = urllib.request.Request(f'{API_URL}/signals')
res = urllib.request.urlopen(req)
data = json.loads(res.read().decode('utf-8'))

nugt_signals = [s for s in data.get('signals', []) if 'nugt' in s['id'].lower()]
if not nugt_signals:
    with open('test_result.json', 'w') as f:
        json.dump({'error': 'NUGT signal not found'}, f)
    exit()

signal = nugt_signals[0]
signal_id = signal['id']

payload = {
    'execute': True,
    'signal': signal,
    'source': 'auto_approve',
    'refreshToken': 'backend-test-token',
    'accountNumber': 'test-account',
    'userId': 'backend-test-user'
}

try:
    req = urllib.request.Request(
        f'{API_URL}/signals/{signal_id}/approve',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    res = urllib.request.urlopen(req)
    response_data = json.loads(res.read().decode('utf-8'))
    with open('test_result.json', 'w') as f:
        json.dump(response_data, f, indent=2)
except urllib.error.HTTPError as e:
    try:
        err_data = json.loads(e.read().decode('utf-8'))
        with open('test_result.json', 'w') as f:
            json.dump({'http_error': e.code, 'data': err_data}, f, indent=2)
    except Exception:
        with open('test_result.json', 'w') as f:
            json.dump({'http_error': e.code}, f)
except Exception as e:
    with open('test_result.json', 'w') as f:
        json.dump({'error': str(e)}, f)
