import subprocess, os
KEY = os.path.join(os.path.dirname(os.path.abspath('ec2_investigate.py')), 'tradecoin-bot-key.pem')
HOST = 'ubuntu@34.235.119.67'
cmd = 'cd tastywork-trading && git pull origin main && sudo systemctl restart trademind-api trademind-ws && sudo cp systemd/trademind-unified-scanner.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable trademind-unified-scanner && sudo systemctl start trademind-unified-scanner'
r = subprocess.run(['ssh', '-o', 'StrictHostKeyChecking=no', '-i', KEY, HOST, cmd], capture_output=True, text=True)
print('STDOUT:', r.stdout)
print('STDERR:', r.stderr)
print('RC:', r.returncode)
