def dlog(msg):
    with open("debug.txt", "a") as f:
        f.write(msg + "\n")

# Clear previous log
with open("debug.txt", "w") as f:
    f.write("DEBUG START\n")

try:
    dlog("Importing os...")
    import os
    dlog("os imported")
    
    dlog("Importing dotenv...")
    from dotenv import load_dotenv
    dlog("dotenv imported")
    load_dotenv()
    dlog("load_dotenv run")
    
    dlog("Importing tastytrade...")
    from tastytrade import Session, Account
    dlog("tastytrade imported")
    
    dlog("Importing google_secrets...")
    from google_secrets import create_or_update_secret
    dlog("google_secrets imported")

    dlog("SUCCESS: All imports worked.")
except Exception as e:
    dlog(f"CRASH: {e}")
    import traceback
    dlog(traceback.format_exc())
