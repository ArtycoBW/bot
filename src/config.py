import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

class Settings:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT", "")
    APPWRITE_PROJECT_ID = os.getenv("APPWRITE_PROJECT_ID", "")
    APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY", "")
    APPWRITE_DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID", "")
    APPWRITE_COLLECTION_SUBMISSIONS = os.getenv("APPWRITE_COLLECTION_SUBMISSIONS", "")
    APPWRITE_COLLECTION_ADMINS = os.getenv("APPWRITE_COLLECTION_ADMINS", "")

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
