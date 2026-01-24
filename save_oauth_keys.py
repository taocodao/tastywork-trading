from google_secrets import create_or_update_secret
import os

# CREDENTIALS FROM USER
CLIENT_ID = "340d790d-f45b-4165-b2b4-d8faf7d655a5"
CLIENT_SECRET = "30550bb7ff47d0e9c76a9b8eb6a1ec1eac9940cd"
REFRESH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6InJ0K2p3dCIsImtpZCI6ImJXb1pyRnBRUkFQWUFrcFdCTmxuUUZLQ1dUdnZNMkZXb0owcm5INnp2MDQiLCJqa3UiOiJodHRwczovL2ludGVyaW9yLWFwaS5hcjIudGFzdHl0cmFkZS5zeXN0ZW1zL29hdXRoL2p3a3MifQ.eyJpc3MiOiJodHRwczovL2FwaS50YXN0eXRyYWRlLmNvbSIsInN1YiI6IlU1YjU2ODVmYi0zYWFjLTRlNGYtOTAyOS0xMWQ5ZjQwYTk3MGQiLCJpYXQiOjE3Njg3ODMzOTgsImF1ZCI6IjM0MGQ3OTBkLWY0NWItNDE2NS1iMmI0LWQ4ZmFmN2Q2NTVhNSIsImdyYW50X2lkIjoiR2RlZjM1OTg2LTI1OWYtNGM0NS1iMGM4LTIxNmNhODQ2N2U2YyIsInNjb3BlIjoicmVhZCB0cmFkZSBvcGVuaWQifQ.SCQbMhgyXA-1e9clxUy3iSnvYDgJh-sr7QMban44Jh7Wu4zcHsqOFY7Vxh-l4zLxzmX7Hm0KBuhTJ5Izh66dCQ"

def save_to_env():
    """Update .env file strictly."""
    env_path = ".env"
    
    # Read existing
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    # Remove old TASTYTRADE lines and prepare new content
    new_lines = [line for line in lines if not line.startswith("TASTYTRADE_")]
    
    # Append new OAuth keys
    new_lines.append(f"TASTYTRADE_CLIENT_ID={CLIENT_ID}\n")
    new_lines.append(f"TASTYTRADE_CLIENT_SECRET={CLIENT_SECRET}\n")
    new_lines.append(f"TASTYTRADE_REFRESH_TOKEN={REFRESH_TOKEN}\n")
    
    with open(env_path, "w") as f:
        f.writelines(new_lines)
    print("✅ Updated .env file.")

def save_to_cloud():
    """Update Google Secret Manager."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "named-dialect-481218-e7")
    
    print(f"Saving to Google Project: {project_id}")
    
    create_or_update_secret("tastytrade_client_id", CLIENT_ID, project_id)
    create_or_update_secret("tastytrade_client_secret", CLIENT_SECRET, project_id)
    create_or_update_secret("tastytrade_refresh_token", REFRESH_TOKEN, project_id)
    
    print("✅ Saved to Google Secret Manager.")

if __name__ == "__main__":
    save_to_env()
    save_to_cloud()
