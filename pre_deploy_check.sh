#!/bin/bash
# Pre-deployment hook script
# Add this to your CI/CD pipeline or run manually before deploying

echo "🔍 Running pre-deployment checks..."
echo ""

# Check 1: Verify OAuth credentials match
echo "1. Verifying OAuth credentials..."
python3 verify_credentials.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ PRE-DEPLOYMENT CHECK FAILED!"
    echo "   Fix credential mismatch before deploying"
    exit 1
fi

echo ""
echo "2. Checking Python dependencies..."
python3 -m pip check
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Dependency issues detected"
fi

echo ""
echo "3. Running credential enforcement test..."
python3 credential_enforcement.py
if [ $? -ne 0 ]; then
    echo "❌ Credential enforcement validation failed"
    exit 1
fi

echo ""
echo "✅ All pre-deployment checks passed!"
echo "   Safe to deploy backend to EC2"
