# Upload the fixed signal_publisher.py file
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Uploading fixed signal_publisher.py..."

# Use SCP to copy the local fixed file
scp -i $PEM -o StrictHostKeyChecking=no `
    "signal_publisher.py" `
    "ubuntu@${HOST}:~/tastywork-trading/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ File uploaded successfully"
    
    # Restart scanner
    Write-Host "Restarting scanner..."
    ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "sudo systemctl restart trademind-scanner"
    
    Write-Host "✅ Scanner restarted"
    Write-Host ""
    Write-Host "Please wait 30 seconds, then refresh the frontend and try approving a signal."
} else {
    Write-Host "❌ Upload failed"
}
