import re
import httpx
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from pyrogram.enums import ParseMode, ChatType
from app.database.database import database_service
from app.services.github_api import github_api_service
from app.handlers.reply_handlers import extract_github_target_from_message
from app.utils.formatters import markdown_to_telegram_html, escape_html_text

CMD_TARGET_PATTERN = re.compile(
    r"^(?:([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)(?:\s+|#))?#?(\d+)(?:\s+(.*))?$",
    re.DOTALL
)

def parse_labels_text(text: str) -> list[str]:
    if not text:
        return []
    cleaned = text.strip()
    if "," in cleaned or ";" in cleaned:
        return [lbl.strip() for lbl in re.split(r"[,;]+", cleaned) if lbl.strip()]
    return [lbl.strip() for lbl in cleaned.split() if lbl.strip()]

async def resolve_repository_for_chat(message: Message) -> str | None:
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        repos = await database_service.retrieve_connected_repositories(message.chat.id)
        if repos:
            first = repos[0]
            return first.get("name") if isinstance(first, dict) else first
    elif message.chat.type == ChatType.PRIVATE:
        grp = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if grp:
            repos = await database_service.retrieve_connected_repositories(grp["group_id"])
            if repos:
                first = repos[0]
                return first.get("name") if isinstance(first, dict) else first
    return None

async def dispatch_to_connected_log_channel(client: Client, message: Message, user_id: int, text: str):
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
                text=text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception:
            pass

def register_issue_cmd_handlers(application: Client):

    @application.on_message(filters.command("close"))
    async def process_close_issue_command(client: Client, message: Message):
        user_id = message.from_user.id
        account_info = await database_service.retrieve_user_github_account_info(user_id)
        bot_self = await client.get_me()

        if not account_info or not account_info.get("token"):
            connect_url = f"https://t.me/{bot_self.username}?start=connect_github"
            connect_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔐 Connect GitHub Account", url=connect_url)]
            ])
            return await message.reply(
                "⚠️ <b>GitHub Account Not Connected!</b>\n\n"
                "To manage issues and pull requests, please connect your GitHub account with the bot.\n\n"
                "👉 <i>Click the button below to authorize with GitHub in private chat!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=connect_markup
            )

        user_token = account_info["token"]
        github_username = account_info.get("username", "User")

        parts = (message.text or "").strip().split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        repo_name = None
        issue_number = None
        comment_text = None
        item_kind = "issue"

        if message.reply_to_message:
            target_info = extract_github_target_from_message(message.reply_to_message)
            if target_info and target_info.get("type") in ["issue", "pull_request"]:
                repo_name = target_info["repository"]
                issue_number = target_info["number"]
                item_kind = target_info["type"]
                if args:
                    m = CMD_TARGET_PATTERN.match(args)
                    if m and m.group(2) and int(m.group(2)) == issue_number:
                        comment_text = m.group(3)
                    else:
                        comment_text = args

        if not issue_number:
            if not args:
                return await message.reply(
                    "<b>Usage:</b>\n"
                    "• <code>/close #4</code> or <code>/close 4 [comment]</code>\n"
                    "• <code>/close owner/repo #4 [comment]</code>\n"
                    "• Or reply directly to any Issue / PR alert with <code>/close [comment]</code>",
                    parse_mode=ParseMode.HTML
                )
            m = CMD_TARGET_PATTERN.match(args)
            if not m:
                return await message.reply(
                    "❌ <b>Invalid Command Format</b>\n\n"
                    "Please provide an issue or PR number, e.g. <code>/close #4</code> or reply to an alert.",
                    parse_mode=ParseMode.HTML
                )
            specified_repo = m.group(1)
            issue_number = int(m.group(2))
            comment_text = m.group(3)
            repo_name = specified_repo or await resolve_repository_for_chat(message)

        if not repo_name:
            return await message.reply(
                "❌ <b>Repository Not Found</b>\n\n"
                "Please specify the repository name: <code>/close owner/repo #4</code> or link a repository to this group.",
                parse_mode=ParseMode.HTML
            )

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            if comment_text:
                sender_name = message.from_user.username or message.from_user.first_name or "Telegram User"
                tg_handle = f"@{sender_name}" if message.from_user.username else sender_name
                full_comment = f"{comment_text.strip()}\n\n> 💬 *Closed via Telegram (@{bot_self.username}) by @{github_username} ({tg_handle})*"
                await github_api_service.post_issue_or_pr_comment(
                    http_client, repo_name, issue_number, full_comment, user_token
                )

            success, result = await github_api_service.close_issue_or_pr(
                http_client, repo_name, issue_number, user_token
            )

        if success:
            issue_url = result.get("html_url", f"https://github.com/{repo_name}/issues/{issue_number}")
            title = result.get("title", f"#{issue_number}")
            is_pr = "pull_request" in result or item_kind == "pull_request"
            kind_label = "Pull Request" if is_pr else "Issue"

            comment_section = ""
            if comment_text:
                formatted_comment = markdown_to_telegram_html(comment_text.strip())
                comment_section = f"\n\n💬 <b>Comment:</b>\n{formatted_comment}"

            success_text = (
                f"🔒 <b>{kind_label} #{issue_number} Closed!</b>\n\n"
                f"<b>Title:</b> {escape_html_text(title)}\n"
                f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
                f"👤 <b>Closed by:</b> <a href=\"https://github.com/{github_username}\">@{github_username}</a>\n"
                f"🔗 <a href=\"{issue_url}\">View on GitHub</a>"
                f"{comment_section}"
            )
            await dispatch_to_connected_log_channel(client, message, user_id, success_text)
            return await message.reply(
                success_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        else:
            return await message.reply(
                f"❌ <b>Failed to close #{issue_number} in {repo_name}</b>\n\n"
                f"<b>Error:</b> <code>{escape_html_text(str(result))}</code>\n\n"
                f"<i>Make sure @{github_username} has write access to this repository.</i>",
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

    @application.on_message(filters.command("reopen"))
    async def process_reopen_issue_command(client: Client, message: Message):
        user_id = message.from_user.id
        account_info = await database_service.retrieve_user_github_account_info(user_id)
        bot_self = await client.get_me()

        if not account_info or not account_info.get("token"):
            connect_url = f"https://t.me/{bot_self.username}?start=connect_github"
            connect_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔐 Connect GitHub Account", url=connect_url)]
            ])
            return await message.reply(
                "⚠️ <b>GitHub Account Not Connected!</b>\n\n"
                "To manage issues and pull requests, please connect your GitHub account with the bot.\n\n"
                "👉 <i>Click the button below to authorize with GitHub in private chat!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=connect_markup
            )

        user_token = account_info["token"]
        github_username = account_info.get("username", "User")

        parts = (message.text or "").strip().split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        repo_name = None
        issue_number = None
        comment_text = None
        item_kind = "issue"

        if message.reply_to_message:
            target_info = extract_github_target_from_message(message.reply_to_message)
            if target_info and target_info.get("type") in ["issue", "pull_request"]:
                repo_name = target_info["repository"]
                issue_number = target_info["number"]
                item_kind = target_info["type"]
                if args:
                    m = CMD_TARGET_PATTERN.match(args)
                    if m and m.group(2) and int(m.group(2)) == issue_number:
                        comment_text = m.group(3)
                    else:
                        comment_text = args

        if not issue_number:
            if not args:
                return await message.reply(
                    "<b>Usage:</b>\n"
                    "• <code>/reopen #4</code> or <code>/reopen 4 [comment]</code>\n"
                    "• <code>/reopen owner/repo #4 [comment]</code>\n"
                    "• Or reply directly to any Issue / PR alert with <code>/reopen [comment]</code>",
                    parse_mode=ParseMode.HTML
                )
            m = CMD_TARGET_PATTERN.match(args)
            if not m:
                return await message.reply(
                    "❌ <b>Invalid Command Format</b>\n\n"
                    "Please provide an issue or PR number, e.g. <code>/reopen #4</code> or reply to an alert.",
                    parse_mode=ParseMode.HTML
                )
            specified_repo = m.group(1)
            issue_number = int(m.group(2))
            comment_text = m.group(3)
            repo_name = specified_repo or await resolve_repository_for_chat(message)

        if not repo_name:
            return await message.reply(
                "❌ <b>Repository Not Found</b>\n\n"
                "Please specify the repository name: <code>/reopen owner/repo #4</code> or link a repository to this group.",
                parse_mode=ParseMode.HTML
            )

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            if comment_text:
                sender_name = message.from_user.username or message.from_user.first_name or "Telegram User"
                tg_handle = f"@{sender_name}" if message.from_user.username else sender_name
                full_comment = f"{comment_text.strip()}\n\n> 💬 *Reopened via Telegram (@{bot_self.username}) by @{github_username} ({tg_handle})*"
                await github_api_service.post_issue_or_pr_comment(
                    http_client, repo_name, issue_number, full_comment, user_token
                )

            success, result = await github_api_service.reopen_issue_or_pr(
                http_client, repo_name, issue_number, user_token
            )

        if success:
            issue_url = result.get("html_url", f"https://github.com/{repo_name}/issues/{issue_number}")
            title = result.get("title", f"#{issue_number}")
            is_pr = "pull_request" in result or item_kind == "pull_request"
            kind_label = "Pull Request" if is_pr else "Issue"

            comment_section = ""
            if comment_text:
                formatted_comment = markdown_to_telegram_html(comment_text.strip())
                comment_section = f"\n\n💬 <b>Comment:</b>\n{formatted_comment}"

            success_text = (
                f"🔓 <b>{kind_label} #{issue_number} Reopened!</b>\n\n"
                f"<b>Title:</b> {escape_html_text(title)}\n"
                f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
                f"👤 <b>Reopened by:</b> <a href=\"https://github.com/{github_username}\">@{github_username}</a>\n"
                f"🔗 <a href=\"{issue_url}\">View on GitHub</a>"
                f"{comment_section}"
            )
            await dispatch_to_connected_log_channel(client, message, user_id, success_text)
            return await message.reply(
                success_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        else:
            return await message.reply(
                f"❌ <b>Failed to reopen #{issue_number} in {repo_name}</b>\n\n"
                f"<b>Error:</b> <code>{escape_html_text(str(result))}</code>\n\n"
                f"<i>Make sure @{github_username} has write access to this repository.</i>",
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

    @application.on_message(filters.command("label"))
    async def process_label_issue_command(client: Client, message: Message):
        user_id = message.from_user.id
        account_info = await database_service.retrieve_user_github_account_info(user_id)
        bot_self = await client.get_me()

        if not account_info or not account_info.get("token"):
            connect_url = f"https://t.me/{bot_self.username}?start=connect_github"
            connect_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔐 Connect GitHub Account", url=connect_url)]
            ])
            return await message.reply(
                "⚠️ <b>GitHub Account Not Connected!</b>\n\n"
                "To manage issues and pull requests, please connect your GitHub account with the bot.\n\n"
                "👉 <i>Click the button below to authorize with GitHub in private chat!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=connect_markup
            )

        user_token = account_info["token"]
        github_username = account_info.get("username", "User")

        parts = (message.text or "").strip().split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        repo_name = None
        issue_number = None
        raw_labels = ""
        item_kind = "issue"

        if message.reply_to_message:
            target_info = extract_github_target_from_message(message.reply_to_message)
            if target_info and target_info.get("type") in ["issue", "pull_request"]:
                repo_name = target_info["repository"]
                issue_number = target_info["number"]
                item_kind = target_info["type"]
                if args:
                    m = CMD_TARGET_PATTERN.match(args)
                    if m and m.group(2) and int(m.group(2)) == issue_number:
                        raw_labels = m.group(3) or ""
                    else:
                        raw_labels = args

        if not issue_number:
            if not args:
                return await message.reply(
                    "<b>Usage:</b>\n"
                    "• <code>/label #4 bug, enhancement</code>\n"
                    "• <code>/label owner/repo #4 bug, ui</code>\n"
                    "• Or reply directly to any Issue / PR alert with <code>/label bug, documentation</code>",
                    parse_mode=ParseMode.HTML
                )
            m = CMD_TARGET_PATTERN.match(args)
            if not m:
                return await message.reply(
                    "❌ <b>Invalid Command Format</b>\n\n"
                    "Please provide an issue number and labels, e.g. <code>/label #4 bug, enhancement</code>",
                    parse_mode=ParseMode.HTML
                )
            specified_repo = m.group(1)
            issue_number = int(m.group(2))
            raw_labels = m.group(3) or ""
            repo_name = specified_repo or await resolve_repository_for_chat(message)

        if not repo_name:
            return await message.reply(
                "❌ <b>Repository Not Found</b>\n\n"
                "Please specify the repository name: <code>/label owner/repo #4 bug</code> or link a repository to this group.",
                parse_mode=ParseMode.HTML
            )

        labels = parse_labels_text(raw_labels)
        if not labels:
            return await message.reply(
                "⚠️ <b>No Labels Specified</b>\n\n"
                "Please specify at least one label to add, e.g. <code>/label #4 bug, enhancement</code> or reply with <code>/label bug</code>.",
                parse_mode=ParseMode.HTML
            )

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            success, result = await github_api_service.add_issue_labels(
                http_client, repo_name, issue_number, labels, user_token
            )

        if success:
            labels_formatted = ", ".join([f"<code>{escape_html_text(lbl)}</code>" for lbl in labels])
            issue_url = f"https://github.com/{repo_name}/issues/{issue_number}"
            kind_label = "Pull Request" if item_kind == "pull_request" else "Issue"

            success_text = (
                f"🏷️ <b>Labels Added to {kind_label} #{issue_number}!</b>\n\n"
                f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
                f"🏷️ <b>Labels:</b> {labels_formatted}\n"
                f"👤 <b>Added by:</b> <a href=\"https://github.com/{github_username}\">@{github_username}</a>\n"
                f"🔗 <a href=\"{issue_url}\">View on GitHub</a>"
            )
            await dispatch_to_connected_log_channel(client, message, user_id, success_text)
            return await message.reply(
                success_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        else:
            return await message.reply(
                f"❌ <b>Failed to add labels to #{issue_number} in {repo_name}</b>\n\n"
                f"<b>Error:</b> <code>{escape_html_text(str(result))}</code>\n\n"
                f"<i>Make sure @{github_username} has write access to this repository.</i>",
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
