import os
import sys
from tastytrade import Session

# Known keys from user's save_oauth_keys.py
CLIENT_SECRET = "30550bb7ff47d0e9c76a9b8eb6a1ec1eac9940cd"

def setup_token():
    print("Setup Tastytrade Refresh Token")
    print("----------------------------")
    print("Ref: https://my.tastytrade.com/ -> API -> OAuth Applications -> Manage -> Create Grant")
    print("NOTE: You CANNOT generate this token via username/password in this script.")
    print("You MUST visit the website to generate a new long-lived Refresh Token.")
    print("-" * 60)
    
    token = input("Paste your new Refresh Token here: ").strip()
    
    if not token:
        print("Token is required.")
        return

    print("\nValidating token...")
    
    # Force clear env var to ensure we test the NEW token
    if 'TASTYTRADE_REFRESH_TOKEN' in os.environ:
        del os.environ['TASTYTRADE_REFRESH_TOKEN']

    try:
        # Try to connect using the hardcoded secret or env secret
        secret = os.getenv('TASTYTRADE_CLIENT_SECRET', CLIENT_SECRET)
        
        # Initialize session with (secret, token)
        session = Session(secret, token)
        
        print("\n✅ Token is VALID!")
        user = session.get_customer()
        print(f"Authenticated as: {user.first_name} {user.last_name}")
        
        save = input("\nDo you want to save this to .env locally? (y/n): ")
        if save.lower() == 'y':
            update_env(token)
            
    except Exception as e:
        print(f"\n❌ Validation Failed: {e}")
        print("Please check that you copied the token correctly.")

def update_env(token):
    env_path = ".env"
    lines = []
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    # Filter out existing token
    new_lines = [line for line in lines if not line.startswith("TASTYTRADE_REFRESH_TOKEN=")]
    
    # Append new token
    new_lines.append(f"TASTYTRADE_REFRESH_TOKEN={token}\n")
    
    with open(env_path, "w") as f:
        f.writelines(new_lines)
    
    print(f"✅ Updated local {env_path}")
    print("\nNEXT STEPS:")
    print("1. Copy the .env to the server:")
    print("   scp -i \"D:\\Projects\\IB-program-trading\\tradecoin-bot-key.pem\" .env ubuntu@34.203.194.137:/home/ubuntu/.env")
    print("2. Restart the API server:")
    print("   ssh -i \"D:\\Projects\\IB-program-trading\\tradecoin-bot-key.pem\" ubuntu@34.203.194.137 \"sudo systemctl restart api-server\"")

if __name__ == "__main__":
    setup_token()
