import asyncio
from pyrogram import Client, idle
from app.core.config import system_config
from app.core.logging_config import setup_application_logging
from app.database.database import database_service
from app.handlers.bot_handlers import register_bot_handlers
from app.handlers.release_handlers import register_release_handlers
from app.handlers.repo_manager_handlers import register_repo_manager_handlers
from app.handlers.reply_handlers import register_reply_handlers
from app.handlers.issue_cmd_handlers import register_issue_cmd_handlers
from app.services.github_poller import github_poller_service

logger = setup_application_logging()

async def main_application_runner():
    current_loop = asyncio.get_running_loop()
    telegram_bot_client = Client(
        name="CommitCastBot_session",
        api_id=system_config.telegram_api_id,
        api_hash=system_config.telegram_api_hash,
        bot_token=system_config.telegram_bot_token,
        loop=current_loop
    )
    register_bot_handlers(telegram_bot_client)
    register_release_handlers(telegram_bot_client)
    register_repo_manager_handlers(telegram_bot_client)
    register_reply_handlers(telegram_bot_client)
    register_issue_cmd_handlers(telegram_bot_client)
    await database_service.initialize_indexes()
    async with telegram_bot_client:
        bot_account = await telegram_bot_client.get_me()
        print(f"CommitCastBot (@{bot_account.username}) is LIVE and listening for commands!")
        polling_task = asyncio.create_task(github_poller_service.start_polling_loop(telegram_bot_client))
        try:
            await idle()
        finally:
            polling_task.cancel()

if __name__ == "__main__":
    asyncio.run(main_application_runner())
