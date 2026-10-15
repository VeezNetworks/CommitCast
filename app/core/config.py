import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class BotConfiguration(BaseSettings):
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    mongodb_connection_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name: str = os.getenv("DATABASE_NAME", "github_alerts_bot")
    github_personal_token: str = os.getenv("GITHUB_TOKEN", "")
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    polling_interval_seconds: float = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))
    developer_owner_id: int = int(os.getenv("DEVELOPER_OWNER_ID", "0"))

system_config = BotConfiguration()
