# Deploy using SCP - bypass GitHub entirely  
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Deploying fixed signal_publisher.py to EC2..."

# Upload the fixed file
scp -i $PEM -o StrictHostKeyChecking=no `
    "signal_publisher.py" `
    "ubuntu@${HOST}:~/tastywork-trading/" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ File uploaded"
    
    # Restart scanner
    $CMD = @'
sudo systemctl restart trademind-scanner
sleep 5
echo "=== Scanner Status ==="
systemctl status trademind-scanner --no-pager -n 0
echo ""
echo "=== Recent Logs (looking for signal saves) ==="
journalctl -u trademind-scanner -n 30 --no-pager | grep -E "(Signal|saved|Failed|Error)"
'@
    
    $B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
    Write-Host "`nRestarting scanner and checking logs..."
    ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash" 2>&1 | Out-Host
    
} else {
    Write-Host "`n❌ Upload failed with exit code: $LASTEXITCODE"
}
