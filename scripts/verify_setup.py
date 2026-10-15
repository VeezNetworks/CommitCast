import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import system_config
from app.database.database import database_service

async def verify_environment():
    print("=" * 50)
    print("CommitCastBot - System Verification")
    print("=" * 50)

    print(f"Telegram Bot Token: {'[Configured]' if system_config.telegram_bot_token else '[MISSING]'}")
    print(f"Telegram API ID:    {'[Configured]' if system_config.telegram_api_id else '[MISSING]'}")
    print(f"Telegram API Hash:  {'[Configured]' if system_config.telegram_api_hash else '[MISSING]'}")
    print(f"MongoDB URI:        {system_config.mongodb_connection_uri}")
    print(f"Database Name:      {system_config.database_name}")
    print(f"Poll Interval:      {system_config.polling_interval_seconds}s")
    print(f"Developer Owner ID: {system_config.developer_owner_id}")

    try:
        await database_service.initialize_indexes()
        groups = await database_service.retrieve_all_tracked_groups()
        print(f"MongoDB Connection: [SUCCESS] - {len(groups)} tracked group(s) found.")
    except Exception as exc:
        print(f"MongoDB Connection: [FAILED] - {exc}")

    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(verify_environment())
