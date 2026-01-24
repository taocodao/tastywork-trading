# Upload src directory to EC2 using SCP
$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "ubuntu@34.235.119.67"
$LOCAL_SRC = "d:\Projects\tastywork-trading-1\src"
$REMOTE_PATH = "~/tastywork-trading/"

Write-Host "📤 Uploading src directory to EC2..."

# Use scp to upload the entire src directory
scp -i $PEM_FILE -r $LOCAL_SRC ${HOST}:${REMOTE_PATH}

Write-Host "✅ Upload complete! Now restart services on EC2:"
Write-Host ""
Write-Host "In your SSH terminal, run:"
Write-Host "  sudo systemctl restart trademind-api"
Write-Host "  ls -la ~/tastywork-trading/src/"
