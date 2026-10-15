import asyncio
import re
import httpx
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from pyrogram.enums import ParseMode, ChatType
from app.database.database import database_service
from app.services.github_api import github_api_service
from app.core.config import system_config
from app.utils.formatters import markdown_to_telegram_html

def extract_github_target_from_message(message: Message):
    if not message:
        return None
    candidates = []
    entities = (message.entities or []) + (message.caption_entities or [])
    text_content = (message.text or "") + "\n" + (message.caption or "")

    for ent in entities:
        if getattr(ent, "url", None):
            candidates.append(ent.url)
        elif getattr(ent.type, "name", "") == "URL" and message.text:
            url_sub = message.text[ent.offset : ent.offset + ent.length]
            candidates.append(url_sub)

    found_urls = re.findall(r"https?://github\.com/[^\s\"'>]+", text_content)
    candidates.extend(found_urls)

    for url in candidates:
        m_commit = re.search(r"github\.com/([^/]+/[^/]+)/commit/([0-9a-fA-F]+)", url)
        if m_commit:
            return {
                "type": "commit",
                "repository": m_commit.group(1),
                "sha": m_commit.group(2),
                "url": url
            }
        m_pr = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
        if m_pr:
            return {
                "type": "pull_request",
                "repository": m_pr.group(1),
                "number": int(m_pr.group(2)),
                "url": url
            }
        m_issue = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", url)
        if m_issue:
            return {
                "type": "issue",
                "repository": m_issue.group(1),
                "number": int(m_issue.group(2)),
                "url": url
            }
    return None

def register_reply_handlers(application: Client):

    @application.on_message(filters.reply & ~filters.bot)
    async def process_alert_reply_message(client: Client, message: Message):
        if not message.reply_to_message:
            return
        if message.text and message.text.startswith("/"):
            return

        bot_self = await client.get_me()
        reply_msg = message.reply_to_message
        if not reply_msg.from_user or reply_msg.from_user.id != bot_self.id:
            return

        target_info = extract_github_target_from_message(reply_msg)
        if not target_info:
            return

        user_id = message.from_user.id
        account_info = await database_service.retrieve_user_github_account_info(user_id)

        if not account_info or not account_info.get("token"):
            connect_url = f"https://t.me/{bot_self.username}?start=connect_github"
            connect_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔗 Connect GitHub Account", url=connect_url)]
            ])
            return await message.reply(
                f"⚠️ <b>GitHub Account Not Connected!</b>\n\n"
                f"You replied to an alert for <b>{target_info['repository']}</b>, but your GitHub account is not connected with the bot yet.\n\n"
                f"👉 <i>Click the button below to connect your GitHub account in private chat so your replies are automatically posted to GitHub!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=connect_markup
            )

        user_comment = (message.text or message.caption or "").strip()
        if not user_comment:
            return await message.reply("⚠️ Please provide a text message to comment on GitHub.")

        user_token = account_info.get("token")
        github_username = account_info.get("username", "User")
        repo_name = target_info["repository"]
        item_type = target_info["type"]

        sender_name = message.from_user.username or message.from_user.first_name or "Telegram User"
        tg_handle = f"@{sender_name}" if message.from_user.username else sender_name
        comment_body = f"{user_comment}\n\n> 💬 *Posted via Telegram (@{bot_self.username}) by @{github_username} ({tg_handle})*"

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            if item_type == "commit":
                success, result = await github_api_service.post_commit_comment(
                    http_client,
                    repo_name,
                    target_info["sha"],
                    comment_body,
                    user_token
                )
            else:
                success, result = await github_api_service.post_issue_or_pr_comment(
                    http_client,
                    repo_name,
                    target_info["number"],
                    comment_body,
                    user_token
                )

        if success:
            comment_url = result.get("html_url", target_info["url"])
            type_label = "Commit" if item_type == "commit" else ("Pull Request" if item_type == "pull_request" else "Issue")
            formatted_comment = markdown_to_telegram_html(user_comment)
            success_text = (
                f"✅ <b>Comment posted to {type_label} on GitHub!</b>\n\n"
                f"💬 <b>Comment:</b>\n"
                f"{formatted_comment}\n\n"
                f"👤 <b>Author:</b> <a href=\"https://github.com/{github_username}\">@{github_username}</a>\n"
                f"🔗 <a href=\"{comment_url}\">View Comment on GitHub</a>"
            )
            await message.reply(
                success_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

            log_channel_id = None
            if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                grp = await database_service.retrieve_group_by_id(message.chat.id)
                if grp:
                    log_channel_id = grp.get("channel_id")
            if not log_channel_id:
                account = await database_service.retrieve_user_github_account_info(user_id)
                if account:
                    log_channel_id = account.get("log_channel_id") or account.get("channel_id")
            if not log_channel_id:
                grp = await database_service.retrieve_connected_group_by_owner(user_id)
                if grp:
                    log_channel_id = grp.get("channel_id")
            if log_channel_id and log_channel_id != message.chat.id:
                try:
                    await client.send_message(
                        chat_id=log_channel_id,
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                except Exception:
                    pass
        else:
            reauth_url = f"https://t.me/{bot_self.username}?start=connect_github"
            reauth_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔄 Re-Authorize GitHub Account", url=reauth_url)]
            ])
            fail_text = (
                f"❌ <b>Failed to post comment as @{github_username}</b>\n\n"
                f"<b>Error:</b> <code>{result}</code>\n\n"
                f"<i>Your connected GitHub account (@{github_username}) requires commenting permissions. Tap the button below to re-authorize!</i>"
            )
            await message.reply(fail_text, parse_mode=ParseMode.HTML, reply_markup=reauth_markup)
