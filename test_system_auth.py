import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth_test")

try:
    from tastytrade_utils import create_user_session
except ImportError:
    logger.error("Could not import tastytrade_utils. Make sure you are in the project directory.")
    sys.exit(1)

def test_auth():
    print("🧪 Testing System Authentication...")
    
    # 1. Check Environment Variables
    client_id = os.getenv("TASTYTRADE_CLIENT_ID")
    client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    
    print(f"Client ID: {client_id[:4]}...{client_id[-4:] if client_id else 'None'}")
    print(f"Client Secret: {client_secret[:4]}...{client_secret[-4:] if client_secret else 'None'}")
    print(f"Refresh Token: {refresh_token[:10]}...{refresh_token[-10:] if refresh_token else 'None'}")
    
    if not client_secret or not refresh_token:
        print("❌ Missing credentials in .env")
        return

    # 2. Attempt Session Creation
    print("\nAttempting to create session...")
    try:
        session = create_user_session(refresh_token)
        print("✅ Session created successfully!")
        print(f"Token: {session.session_token[:10]}...")
        print(f"Expires: {getattr(session, 'session_expiration', 'unknown')}")
    except Exception as e:
        print(f"❌ Session creation failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_auth()
