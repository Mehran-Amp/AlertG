import os
import json
import firebase_admin
from firebase_admin import credentials
from app.config import SERVICE_ACCOUNT_FILE

firebase_initialized = False

def init_firebase():
    global firebase_initialized
    if firebase_admin._apps:
        firebase_initialized = True
        return

    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred)
            firebase_initialized = True
            print("✅ [Firebase] Connected successfully from local serviceAccountKey.json.")
        except Exception as e:
            print(f"⚠️ [Firebase] Local key init note: {e}")
    elif os.getenv("FIREBASE_SERVICE_ACCOUNT"):
        try:
            cred_dict = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT"))
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            firebase_initialized = True
            print("✅ [Firebase] Connected successfully from environment variable.")
        except Exception as e:
            print(f"⚠️ [Firebase] Env key init note: {e}")
    else:
        print(f"ℹ️ [Firebase] '{SERVICE_ACCOUNT_FILE}' not found (git-ignored). Place key file for mobile push.")

init_firebase()
