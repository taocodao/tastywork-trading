# Comprehensive diagnostic - writes to file on server
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Running comprehensive diagnostic..."

# Create diagnostic script on server
$DIAG_SCRIPT = @'
#!/bin/bash
OUTPUT="/tmp/scanner_diagnostic.txt"
cd ~/tastywork-trading

echo "=== TradeMind Scanner Diagnostic ===" > $OUTPUT
echo "Generated: $(date)" >> $OUTPUT
echo "" >> $OUTPUT

echo "=== 1. Check if patch was applied ===" >> $OUTPUT
grep "init_db" signal_publisher.py | head -5 >> $OUTPUT 2>&1
echo "" >> $OUTPUT

echo "=== 2. Scanner Service Status ===" >> $OUTPUT
systemctl is-active trademind-scanner.timer >> $OUTPUT 2>&1
systemctl is-active trademind-scanner.service >> $OUTPUT 2>&1
echo "" >> $OUTPUT

echo "=== 3. Last 30 Scanner Logs ===" >> $OUTPUT
journalctl -u trademind-scanner -n 30 --no-pager >> $OUTPUT 2>&1
echo "" >> $OUTPUT

echo "=== 4. Check Database ===" >> $OUTPUT
python3 << 'PYEOF' >> $OUTPUT 2>&1
try:
    from src.earnings_intelligence.database import SignalRepository
    repo = SignalRepository()
    signals = repo.get_pending_signals()
    print(f"Pending signals in DB: {len(signals)}")
    for s in signals[:3]:
        print(f"  {s.id[:8]}... {s.symbol} {s.status}")
except Exception as e:
    print(f"Database error: {e}")
    import traceback
    traceback.print_exc()
PYEOF
echo "" >> $OUTPUT

echo "=== 5. Run Scanner Manually (30 sec timeout) ===" >> $OUTPUT
timeout 30 python3 scheduled_scanner.py >> $OUTPUT 2>&1

echo "" >> $OUTPUT
echo "=== Diagnostic Complete ===" >> $OUTPUT
cat $OUTPUT
'@

$B64_SCRIPT = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($DIAG_SCRIPT.Replace("`r", "")))

# Run diagnostic
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64_SCRIPT | base64 -d | bash" | Out-File -FilePath ".\scanner_diagnostic.txt" -Encoding UTF8

Write-Host "`nDiagnostic output saved to: scanner_diagnostic.txt"
Write-Host "`nDisplaying output:"
Get-Content ".\scanner_diagnostic.txt"
