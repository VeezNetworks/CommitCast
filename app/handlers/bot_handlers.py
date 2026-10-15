import httpx
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from app.core.config import system_config
from app.database.database import database_service
from app.handlers.keyboards import markup_builder
from app.services.github_api import github_api_service

MONTH_NAMES_LIST = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

def register_bot_handlers(application: Client):

    async def process_trigger_github_oauth(client: Client, chat_id: int, user_id: int):
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.post(
                "https://github.com/login/device/code",
                data={"client_id": system_config.github_client_id, "scope": "repo,read:org"},
                headers={"Accept": "application/json"}
            )
        if resp.status_code != 200:
            return await client.send_message(chat_id, "❌ Unable to initiate GitHub authorization. Please try again.")
        auth_data = resp.json()
        device_code = auth_data.get("device_code")
        user_code = auth_data.get("user_code")
        verification_uri = auth_data.get("verification_uri", "https://github.com/login/device")
        auth_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🔗 Open GitHub to Authorize", url=verification_uri)],
            [InlineKeyboardButton(text="✅ I Have Authorized", callback_data=f"poll_oauth_token:{device_code}")]
        ])
        oauth_message = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">🔐</tg-emoji> <b>Authorize CommitCastBot with GitHub</b>\n\n"
            f"1. Tap <b>Open GitHub to Authorize</b> below.\n"
            f"2. Enter your single-use code: <code>{user_code}</code>\n"
            f"3. Click <b>Authorize</b> on GitHub.\n"
            f"4. Come back and tap <b>✅ I Have Authorized</b>!\n\n"
            f"<i>Your public & private repositories and commenting access will connect automatically.</i>"
        )
        return await client.send_message(chat_id, oauth_message, parse_mode=ParseMode.HTML, reply_markup=auth_keyboard)

    @application.on_message(filters.command("reauth") & filters.private)
    async def process_reauth_command(client: Client, message: Message):
        return await process_trigger_github_oauth(client, message.chat.id, message.from_user.id)

    @application.on_message(filters.command("start") & filters.private)
    async def process_start_command(client: Client, message: Message):
        if len(message.command) > 1 and message.command[1] in ["connect_github", "auth", "login", "reauth"]:
            return await process_trigger_github_oauth(client, message.chat.id, message.from_user.id)

        user_name = message.from_user.first_name or "Developer"
        start_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">🚀</tg-emoji> <b>Welcome to CommitCastBot, {user_name}!</b>\n\n"
            f"<tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Your Ultimate GitHub & Community Broadcast Assistant</b>\n\n"
            f"• <tg-emoji emoji-id=\"5368324170671202288\">⚡</tg-emoji> <b>Real-time Commit & Issue Tracking</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202286\">📅</tg-emoji> <b>Monthly Banner Management</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202288\">📢</tg-emoji> <b>Automated 15-Day & Month-End Changelogs</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202286\">🔘</tg-emoji> <b>Custom Buttons & URL Alerts</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202287\">🛠️</tg-emoji> <b>Full Repository Control Panel</b>\n\n"
            f"<i>Tap the buttons below to explore features or get started!</i>"
        )
        start_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text="👤 Connected GitHub Account", callback_data="show_connected_github_account")
            ],
            [
                InlineKeyboardButton(text="📖 Help Guide", callback_data="show_help_menu"),
                InlineKeyboardButton(text="📦 My Repos", callback_data="back_to_repo_list")
            ],
            [
                InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/CommitCastBot?startgroup=true")
            ]
        ])
        return await message.reply(start_text, parse_mode=ParseMode.HTML, reply_markup=start_markup)

    @application.on_message(filters.command("help") & filters.private)
    async def process_help_command(client: Client, message: Message):
        help_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">📚</tg-emoji> <b>CommitCastBot Command Center</b>\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202286\">🔗</tg-emoji> Connection Commands:</b>\n"
            f"• <code>/connect_grp &lt;id&gt;</code> - Connect group in DM (Owner only)\n"
            f"• <code>/disconnect_grp</code> - Disconnect connected group\n"
            f"• <code>/set_channel &lt;id&gt;</code> - Link dedicated commit log channel\n"
            f"• <code>/disconnect_channel</code> - Disconnect log channel\n"
            f"• <code>/set_repo &lt;owner/repo&gt;</code> - Link GitHub repo\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">🛠️</tg-emoji> Issue & PR Commands:</b>\n"
            f"• <code>/close &lt;#number&gt; [comment]</code> - Close issue or PR\n"
            f"• <code>/reopen &lt;#number&gt; [comment]</code> - Reopen issue or PR\n"
            f"• <code>/label &lt;#number&gt; &lt;label1, label2&gt;</code> - Add labels\n"
            f"• <i>Reply directly to any alert message with text to post a GitHub comment!</i>\n"
            f"• <i>Reply with <code>/close</code>, <code>/reopen</code>, or <code>/label</code> to act instantly!</i>\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">📦</tg-emoji> Repository Dashboard & Toggles:</b>\n"
            f"• <code>/repos</code> - Interactive control panel with buttons:\n"
            f"  - Commits ON/OFF\n"
            f"  - Issues & PRs ON/OFF\n"
            f"  - Releases & Tags ON/OFF\n"
            f"  - CI/CD Workflows ON/OFF (🟢 Success, 🔴 Fail, 🟡 Approval)\n"
            f"  - Stars & Forks Alerts ON/OFF\n"
            f"  - View active issues & Close all PRs\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202286\">🖼️</tg-emoji> Monthly Banners:</b>\n"
            f"• <code>/add_banner</code> - Upload month banner in DM\n"
            f"• <code>/get_banner</code> - View banner photos with delete button\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">🚀</tg-emoji> Release Notes:</b>\n"
            f"• <code>/preview_update</code> - Draft 15-day updates\n"
            f"• <code>/preview_update 30</code> - Draft month-end updates\n"
            f"• <code>/custom_btn</code> - Add custom buttons (URL/Alert)\n"
            f"• <code>/custom_links</code> - Add rich footer links"
        )
        help_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📦 Open Repos Dashboard", callback_data="back_to_repo_list")],
            [InlineKeyboardButton(text="🔙 Back to Start", callback_data="back_to_start_menu")]
        ])
        return await message.reply(help_text, parse_mode=ParseMode.HTML, reply_markup=help_markup)

    @application.on_callback_query(filters.regex(r"^show_help_menu$"))
    async def process_show_help_callback(client: Client, query: CallbackQuery):
        help_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">📚</tg-emoji> <b>CommitCastBot Command Center</b>\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202286\">🔗</tg-emoji> Connection & Setup:</b>\n"
            f"• <code>/connect_grp &lt;id&gt;</code> - Connect group in DM (Owner only)\n"
            f"• <code>/disconnect_grp</code> - Disconnect connected group\n"
            f"• <code>/set_channel &lt;id&gt;</code> - Link dedicated commit log channel\n"
            f"• <code>/disconnect_channel</code> - Disconnect log channel\n"
            f"• <code>/set_repo &lt;owner/repo&gt;</code> - Link GitHub repo\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">🛠️</tg-emoji> Issue & PR Commands:</b>\n"
            f"• <code>/close &lt;#number&gt; [comment]</code> - Close issue or PR\n"
            f"• <code>/reopen &lt;#number&gt; [comment]</code> - Reopen issue or PR\n"
            f"• <code>/label &lt;#number&gt; &lt;label1, label2&gt;</code> - Add labels\n"
            f"• <i>Reply directly to any alert message with text to post a GitHub comment!</i>\n"
            f"• <i>Reply with <code>/close</code>, <code>/reopen</code>, or <code>/label</code> to act instantly!</i>\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">📦</tg-emoji> Repository Management:</b>\n"
            f"• <code>/repos</code> - Interactive control panel with buttons:\n"
            f"  - Commits ON/OFF\n"
            f"  - Issues & PRs ON/OFF\n"
            f"  - Releases & Tags ON/OFF\n"
            f"  - CI/CD Workflows ON/OFF (🟢 Success, 🔴 Fail, 🟡 Approval)\n"
            f"  - Stars & Forks Alerts ON/OFF\n"
            f"  - View active issues & Close all PRs\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202286\">🖼️</tg-emoji> Monthly Banners:</b>\n"
            f"• <code>/add_banner</code> - Upload month banner in DM\n"
            f"• <code>/get_banner</code> - View banner photos with delete button\n\n"
            f"<b><tg-emoji emoji-id=\"5368324170671202288\">🚀</tg-emoji> Release Notes:</b>\n"
            f"• <code>/preview_update</code> - Draft 15-day updates\n"
            f"• <code>/preview_update 30</code> - Draft month-end updates\n"
            f"• <code>/custom_btn</code> - Add custom buttons (URL/Alert)\n"
            f"• <code>/custom_links</code> - Add rich footer links"
        )
        help_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📦 Open Repos Dashboard", callback_data="back_to_repo_list")],
            [InlineKeyboardButton(text="🔙 Back to Start", callback_data="back_to_start_menu")]
        ])
        await query.message.edit_text(help_text, parse_mode=ParseMode.HTML, reply_markup=help_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^back_to_start_menu$"))
    async def process_back_to_start_callback(client: Client, query: CallbackQuery):
        user_name = query.from_user.first_name or "Developer"
        start_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">🚀</tg-emoji> <b>Welcome to CommitCastBot, {user_name}!</b>\n\n"
            f"<tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Your Ultimate GitHub & Community Broadcast Assistant</b>\n\n"
            f"• <tg-emoji emoji-id=\"5368324170671202288\">⚡</tg-emoji> <b>Real-time Commit & Issue Tracking</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202286\">📅</tg-emoji> <b>Monthly Banner Management</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202288\">📢</tg-emoji> <b>Automated 15-Day & Month-End Changelogs</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202286\">🔘</tg-emoji> <b>Custom Buttons & URL Alerts</b>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202287\">🛠️</tg-emoji> <b>Full Repository Control Panel</b>\n\n"
            f"<i>Tap the buttons below to explore features or get started!</i>"
        )
        start_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text="👤 Connected GitHub Account", callback_data="show_connected_github_account")
            ],
            [
                InlineKeyboardButton(text="📖 Help Guide", callback_data="show_help_menu"),
                InlineKeyboardButton(text="📦 My Repos", callback_data="back_to_repo_list")
            ],
            [
                InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/CommitCastBot?startgroup=true")
            ]
        ])
        await query.message.edit_text(start_text, parse_mode=ParseMode.HTML, reply_markup=start_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^show_connected_github_account$"))
    async def process_show_connected_github_account(client: Client, query: CallbackQuery):
        user_info = await database_service.retrieve_user_github_account_info(query.from_user.id)
        if not user_info:
            not_connected_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔑 Add Private Token (Full Access)", callback_data="prompt_private_token_input")],
                [InlineKeyboardButton(text="🔗 Connect via GitHub OAuth", callback_data="reauth_github_account")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_start_menu")]
            ])
            return await query.message.edit_text(
                f"<tg-emoji emoji-id=\"5368324170671202288\">ℹ️</tg-emoji> <b>No GitHub Account Connected</b>\n\n"
                f"Connect your account below to access your public and private repositories:",
                parse_mode=ParseMode.HTML,
                reply_markup=not_connected_markup
            )
        gh_username = user_info.get("username", "Unknown")
        gh_token = user_info.get("token")
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            repos_list = await github_api_service.fetch_user_repositories(http_client, token=gh_token)
        repo_count = len(repos_list)
        private_count = sum(1 for r in repos_list if r.get("private"))
        public_count = repo_count - private_count
        account_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🔑 Add Private Token (Unlock Private Repos)", callback_data="prompt_private_token_input")],
            [InlineKeyboardButton(text="📦 View All Repositories", callback_data="back_to_repo_list")],
            [InlineKeyboardButton(text="🔄 Re-Authorize Account", callback_data="reauth_github_account")],
            [InlineKeyboardButton(text="❌ Disconnect Account", callback_data="unlink_github_account_confirm")],
            [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_start_menu")]
        ])
        account_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">👤</tg-emoji> <b>Connected GitHub Profile</b>\n\n"
            f"• <b>Username:</b> <a href=\"https://github.com/{gh_username}\">@{gh_username}</a>\n"
            f"• <b>Status:</b> 🟢 Active & Authorized\n"
            f"• <b>Total Repositories:</b> <b>{repo_count}</b>\n"
            f"  - 🔒 Private: <b>{private_count}</b>\n"
            f"  - 🌐 Public: <b>{public_count}</b>\n\n"
            f"<i>You can manage repo alert streams or disconnect this profile below:</i>"
        )
        await query.message.edit_text(account_text, parse_mode=ParseMode.HTML, reply_markup=account_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^unlink_github_account_confirm$"))
    async def process_unlink_confirm(client: Client, query: CallbackQuery):
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🚨 YES, Disconnect GitHub", callback_data="do_unlink_github_account")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="show_connected_github_account")]
        ])
        await query.message.edit_text(
            "⚠️ <b>Are you sure you want to disconnect your GitHub account?</b>\n\n"
            "You will need to re-authorize again to manage repositories.",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_markup
        )
        await query.answer()

    @application.on_callback_query(filters.regex(r"^do_unlink_github_account$"))
    async def process_do_unlink(client: Client, query: CallbackQuery):
        await database_service.unlink_user_github_account(query.from_user.id)
        await query.answer("GitHub account disconnected!", show_alert=True)
        return await process_show_connected_github_account(client, query)

    @application.on_callback_query(filters.regex(r"^prompt_private_token_input$"))
    async def process_prompt_private_token_input(client: Client, query: CallbackQuery):
        await database_service.set_user_interaction_state(query.from_user.id, "awaiting_private_github_token")
        token_guide_text = (
            f"<tg-emoji emoji-id=\"5368324170671202288\">🔑</tg-emoji> <b>Connect GitHub via Private Token</b>\n\n"
            f"A Personal Access Token (classic) with <code>repo</code> scope gives access to all your <b>Private</b> and Organization repositories.\n\n"
            f"1. Open <a href=\"https://github.com/settings/tokens/new?scopes=repo,read:org&description=CommitCastBot\">GitHub Token Generator</a>\n"
            f"2. Check the <b>repo</b> scope and click <b>Generate token</b>\n"
            f"3. Send your token (starting with <code>ghp_...</code>) right here in this chat:\n\n"
            f"<i>Your token is stored securely and never shared.</i>"
        )
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Cancel", callback_data="show_connected_github_account")]])
        await query.message.edit_text(token_guide_text, parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
        await query.answer()

    @application.on_message(filters.regex(r"^gh[pousr]_[A-Za-z0-9_]+") & filters.private)
    async def process_private_token_message(client: Client, message: Message):
        token_str = message.text.strip()
        loading = await message.reply("🔄 Verifying GitHub token and fetching repository access...")
        async with httpx.AsyncClient(timeout=12.0) as http_client:
            headers = {"Authorization": f"token {token_str}", "Accept": "application/vnd.github.v3+json"}
            u_resp = await http_client.get("https://api.github.com/user", headers=headers)
            if u_resp.status_code != 200:
                return await loading.edit_text("❌ Invalid token or unauthorized. Please verify the token has `repo` scope.")
            user_data = u_resp.json()
            username = user_data.get("login", "GitHub User")
            user_repos = await github_api_service.fetch_user_repositories(http_client, token=token_str)
        private_count = sum(1 for r in user_repos if r.get("private"))
        public_count = len(user_repos) - private_count
        await database_service.store_user_github_token(message.from_user.id, token_str, username)
        await database_service.reset_user_interaction_state(message.from_user.id)
        success_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📦 View All Repositories", callback_data="back_to_repo_list")],
            [InlineKeyboardButton(text="👤 GitHub Profile", callback_data="show_connected_github_account")]
        ])
        success_text = (
            f"✅ <b>Private GitHub Access Connected!</b>\n\n"
            f"• <b>Account:</b> <a href=\"https://github.com/{username}\">@{username}</a>\n"
            f"• <b>Total Repositories Found:</b> <b>{len(user_repos)}</b>\n"
            f"  - 🔒 Private: <b>{private_count}</b>\n"
            f"  - 🌐 Public: <b>{public_count}</b>\n\n"
            f"All your private repositories are unlocked! You can now link them using /set_repo or the buttons below:"
        )
        await loading.edit_text(success_text, parse_mode=ParseMode.HTML, reply_markup=success_markup)

    @application.on_callback_query(filters.regex(r"^get_banner_shortcut$"))
    async def process_banner_shortcut(client: Client, query: CallbackQuery):
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group yet. Use /connect_grp first.", show_alert=True)
        distinct_months = await database_service.retrieve_distinct_banner_months(connected_group["group_id"])
        if not distinct_months:
            return await query.message.edit_text(
                "No banners uploaded yet. Use /add_banner to upload one.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_start_menu")]])
            )
        markup = markup_builder.construct_month_selection_markup(distinct_months, "fetch_banner_month")
        await query.message.edit_text("Select the month to view banners:", reply_markup=markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^preview_update_shortcut$"))
    async def process_preview_shortcut(client: Client, query: CallbackQuery):
        await query.answer()
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.message.edit_text(
                "❌ No group connected yet. Use /connect_grp first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_start_menu")]])
            )
        await query.message.reply("Use `/preview_update` (15 days) or `/preview_update 30` (month-end) to generate release drafts!")

    @application.on_message(filters.command("connect_grp") & filters.private)
    async def process_connect_group_command(client: Client, message: Message):
        tokens = message.text.split(maxsplit=1)
        if len(tokens) < 2:
            return await message.reply("Usage: `/connect_grp <group_id>`\nExample: `/connect_grp -1001234567890`")
        try:
            target_group_id = int(tokens[1].strip())
        except ValueError:
            return await message.reply("❌ Group ID must be an integer (e.g. -1001234567890).")
        try:
            target_chat = await client.get_chat(target_group_id)
            chat_member = await client.get_chat_member(target_group_id, message.from_user.id)
        except Exception:
            return await message.reply("❌ Unable to access that group. Make sure the bot is added to the group as an Administrator.")
        is_dev_admin = (message.from_user.id == system_config.developer_owner_id)
        if not is_dev_admin and chat_member.status != ChatMemberStatus.OWNER:
            return await message.reply("❌ Access Denied: You must be the group creator/owner to connect this group.")
        await database_service.connect_group_for_owner(target_group_id, message.from_user.id, target_chat.title)
        return await message.reply(f"✅ Successfully connected to **{target_chat.title}** (`{target_group_id}`)!\n\nYou can now manage banners, custom buttons, and release notes in this chat.")

    @application.on_message(filters.command("set_channel") & filters.private)
    async def process_set_channel_command(client: Client, message: Message):
        tokens = message.text.split(maxsplit=1)
        if len(tokens) < 2:
            return await message.reply("Usage: `/set_channel <channel_id>`\nExample: `/set_channel -1009876543210`")
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ You have not connected any group yet. Use `/connect_grp <group_id>` first.")
        try:
            target_channel_id = int(tokens[1].strip())
            channel_chat = await client.get_chat(target_channel_id)
        except Exception:
            return await message.reply("❌ Invalid Channel ID or bot is not an administrator in that channel.")
        await database_service.set_connected_channel(connected_group["group_id"], target_channel_id, owner_id=message.from_user.id)
        return await message.reply(
            f"✅ Channel **{channel_chat.title}** (`{target_channel_id}`) linked as dedicated log channel for your account and **{connected_group['group_title']}**.\n\n"
            f"All commit alerts will route here automatically. You will not need to set this again for new repositories.\n"
            f"You can disconnect this channel anytime using `/disconnect_channel`."
        )

    @application.on_message(filters.command(["disconnect_channel", "unlink_channel"]))
    async def process_disconnect_channel_command(client: Client, message: Message):
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            grp = await database_service.retrieve_group_by_id(message.chat.id)
            if grp and (grp.get("owner_id") == message.from_user.id or message.from_user.id == system_config.developer_owner_id):
                connected_group = grp
        if not connected_group:
            return await message.reply("❌ No connected group or log channel found for your account.")
        await database_service.disconnect_connected_channel(connected_group["group_id"], owner_id=message.from_user.id)
        return await message.reply(
            f"✅ <b>Log Channel Disconnected!</b>\n\n"
            f"Alerts for <b>{connected_group.get('group_title', 'your group')}</b> will now route directly to the group chat.\n"
            f"You can link a new channel anytime with <code>/set_channel &lt;channel_id&gt;</code>.",
            parse_mode=ParseMode.HTML
        )

    @application.on_message(filters.command(["disconnect_grp", "disconnect_group"]))
    async def process_disconnect_group_command(client: Client, message: Message):
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            grp = await database_service.retrieve_group_by_id(message.chat.id)
            if grp and (grp.get("owner_id") == message.from_user.id or message.from_user.id == system_config.developer_owner_id):
                connected_group = grp
        if not connected_group:
            return await message.reply("❌ You do not have any connected group currently.")
        group_title = connected_group.get("group_title", "Group")
        group_id = connected_group.get("group_id")
        await database_service.disconnect_group(group_id, owner_id=message.from_user.id)
        return await message.reply(
            f"✅ <b>Group Disconnected!</b>\n\n"
            f"<b>{group_title}</b> (<code>{group_id}</code>) has been successfully disconnected from your GitHub account.\n"
            f"You can connect a new group anytime using <code>/connect_grp &lt;group_id&gt;</code>.",
            parse_mode=ParseMode.HTML
        )

    @application.on_message(filters.command("set_repo") & filters.private)
    async def process_set_repo_command(client: Client, message: Message):
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ You have not connected any group yet. Use `/connect_grp <group_id>` first.")
        user_token = await database_service.retrieve_user_github_token(message.from_user.id)
        if not user_token:
            return await process_trigger_github_oauth(client, message.chat.id, message.from_user.id)
        loading_msg = await message.reply("🔄 Fetching your GitHub repositories (Public & Private)...")
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            user_repos = await github_api_service.fetch_user_repositories(http_client, token=user_token)
        if not user_repos:
            return await process_trigger_github_oauth(client, message.chat.id, message.from_user.id)
        repo_buttons = []
        for r in user_repos[:25]:
            lock_icon = "🔒" if r.get("private") else "🌐"
            repo_full = r.get("full_name")
            repo_buttons.append([InlineKeyboardButton(text=f"{lock_icon} {repo_full}", callback_data=f"select_repo_connect:{repo_full}")])
        repo_buttons.append([InlineKeyboardButton(text="🔄 Re-Authorize GitHub", callback_data="reauth_github_account")])
        repo_buttons.append([InlineKeyboardButton(text="🔙 Cancel", callback_data="back_to_start_menu")])
        await loading_msg.delete()
        return await message.reply(
            f"📦 <b>Select a Repository to Connect</b>\n\nGroup: <b>{connected_group['group_title']}</b>\nTap any repository to start instant tracking:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(repo_buttons)
        )


    @application.on_callback_query(filters.regex(r"^reauth_github_account$"))
    async def process_reauth_github_account(client: Client, query: CallbackQuery):
        await query.answer()
        return await process_trigger_github_oauth(client, query.message.chat.id, query.from_user.id)

    @application.on_callback_query(filters.regex(r"^poll_oauth_token:(.+)"))
    async def process_poll_oauth_token(client: Client, query: CallbackQuery):
        device_code = query.matches[0].group(1)
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            token_resp = await http_client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": system_config.github_client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                headers={"Accept": "application/json"}
            )
        data = token_resp.json()
        if "access_token" in data:
            access_token = data["access_token"]
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                u_res = await http_client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {access_token}", "Accept": "application/vnd.github.v3+json"}
                )
            username = u_res.json().get("login", "GitHub User") if u_res.status_code == 200 else "User"
            await database_service.store_user_github_token(query.from_user.id, access_token, username)
            await query.answer("Account authorized successfully!", show_alert=True)
            connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
            if not connected_group:
                return await query.message.edit_text(f"✅ Connected as <b>@{username}</b>! Now use /connect_grp <group_id> to link a group.")
            async with httpx.AsyncClient(timeout=15.0) as http_client:
                repos = await github_api_service.fetch_user_repositories(http_client, token=access_token)
            repo_buttons = []
            for r in repos[:25]:
                lock_icon = "🔒" if r.get("private") else "🌐"
                repo_full = r.get("full_name")
                repo_buttons.append([InlineKeyboardButton(text=f"{lock_icon} {repo_full}", callback_data=f"select_repo_connect:{repo_full}")])
            repo_buttons.append([InlineKeyboardButton(text="🔙 Cancel", callback_data="back_to_start_menu")])
            return await query.message.edit_text(
                f"✅ <b>Connected as @{username}!</b>\n\n"
                f"• Commenting write access is now <b>Active</b>!\n"
                f"• Telegram replies will post directly as <b>@{username}</b> on GitHub.\n\n"
                f"Select a repository to link to <b>{connected_group['group_title']}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(repo_buttons)
            )
        error_msg = data.get("error_description") or data.get("error") or "Please finish authorization on GitHub first."
        await query.answer(f"⏳ {error_msg}", show_alert=True)

    @application.on_callback_query(filters.regex(r"^select_repo_connect:(.+)"))
    async def process_select_repo_connect(client: Client, query: CallbackQuery):
        selected_repo = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("⚠️ No connected group found! Use /connect_grp first.", show_alert=True)
        is_added = await database_service.link_github_repository(connected_group["group_id"], selected_repo)
        if not is_added:
            return await query.answer(f"⚠️ '{selected_repo}' is already connected to this group!", show_alert=True)
        channel_id = connected_group.get("channel_id")
        if not channel_id:
            account = await database_service.user_accounts_collection.find_one({"user_id": query.from_user.id})
            if account:
                channel_id = account.get("log_channel_id") or account.get("channel_id")
        channel_info = f"<code>{channel_id}</code> <i>(Auto-inherited)</i>" if channel_id else f"<i>(Alerts will route to {connected_group['group_title']})</i>"
        confirm_text = (
            f"✅ <b>Repository Connected!</b>\n\n"
            f"📦 <b>Repository:</b> <code>{selected_repo}</code>\n"
            f"👥 <b>Target Group:</b> <b>{connected_group['group_title']}</b>\n"
            f"📢 <b>Log Channel:</b> {channel_info}\n\n"
            f"⚡ <i>Immediate commit alerts are now active! Use /repos to manage settings.</i>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="⚙️ Manage in Repos Dashboard", callback_data=f"manage_repo:{selected_repo}")],
            [InlineKeyboardButton(text="➕ Connect Another Repo", callback_data="reauth_github_account")],
            [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_start_menu")]
        ])
        await query.message.edit_text(confirm_text, parse_mode=ParseMode.HTML, reply_markup=markup)
        await query.answer("Repository connected!", show_alert=False)

    @application.on_callback_query(filters.regex(r"^ask_repo_channel:(.+)"))
    async def process_ask_repo_channel(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        repo_name = repo_ref
        if connected_group:
            repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
            from app.handlers.repo_manager_handlers import resolve_repo_by_ref
            resolved, _, _ = resolve_repo_by_ref(repos_list, repo_ref)
            if resolved:
                repo_name = resolved
        await database_service.set_user_interaction_state(
            query.from_user.id,
            "awaiting_repo_channel",
            {"repository": repo_name}
        )
        await query.message.edit_text(
            f"📢 <b>Set Dedicated Log Channel for {repo_name}</b>\n\n"
            f"Please send the Channel ID (e.g. <code>-1001234567890</code>) here in DM.\n"
            f"<i>Make sure @CommitCastBot is an Administrator in that channel!</i>",
            parse_mode=ParseMode.HTML
        )
        await query.answer()

    @application.on_message(filters.regex(r"^-100\d+$") & filters.private)
    async def process_channel_id_message(client: Client, message: Message):
        user_state = await database_service.retrieve_user_interaction_state(message.from_user.id)
        if not user_state or user_state.get("state") != "awaiting_repo_channel":
            return
        repo_name = user_state.get("metadata", {}).get("repository")
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group or not repo_name:
            return
        channel_id = int(message.text.strip())
        try:
            channel_chat = await client.get_chat(channel_id)
        except Exception:
            return await message.reply("❌ Invalid Channel ID or bot is not an admin in that channel.")
        await database_service.set_connected_channel(connected_group["group_id"], channel_id, owner_id=message.from_user.id)
        await database_service.reset_user_interaction_state(message.from_user.id)
        return await message.reply(
            f"✅ Channel <b>{channel_chat.title}</b> (<code>{channel_id}</code>) successfully saved as your dedicated Log Channel for all repositories!\n\n"
            f"This channel is now saved for your account. You will not need to set it again when adding new repositories.\n"
            f"You can disconnect it anytime using `/disconnect_channel`.",
            parse_mode=ParseMode.HTML
        )

    @application.on_message(filters.command("add_banner"))
    async def process_add_banner_command(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            try:
                chat_member = await client.get_chat_member(message.chat.id, message.from_user.id)
            except Exception:
                return await message.reply("❌ Bot needs administrator permissions to verify membership.")
            if chat_member.status != ChatMemberStatus.OWNER:
                return await message.reply("❌ Only the group owner can add banners.")
            bot_self = await client.get_me()
            deep_link = f"https://t.me/{bot_self.username}?start=banner_{message.chat.id}"
            inline_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text="➕ Add Banner in Private Chat", url=deep_link)]])
            return await message.reply("Click the button below to upload banners securely in private chat:", reply_markup=inline_keyboard)
        elif message.chat.type == ChatType.PRIVATE:
            connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
            if not connected_group:
                return await message.reply("❌ No group connected to your account. Use `/connect_grp <group_id>` first.")
            markup = markup_builder.construct_month_selection_markup(MONTH_NAMES_LIST, "select_add_month")
            return await message.reply("Select which month you want to add this banner for:", reply_markup=markup)

    @application.on_callback_query(filters.regex(r"^select_add_month:(.+)"))
    async def process_month_selection_callback(client: Client, query: CallbackQuery):
        selected_month = query.matches[0].group(1).capitalize()
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group found.", show_alert=True)
        await database_service.set_user_interaction_state(
            query.from_user.id,
            "awaiting_banner_photo",
            {"group_id": connected_group["group_id"], "month": selected_month}
        )
        await query.message.edit_text(f"Selected Month: **{selected_month}**\n\nPlease send the banner photo now as a photo attachment.")
        await query.answer()

    @application.on_message(filters.photo & filters.private)
    async def process_banner_photo_upload(client: Client, message: Message):
        current_state = await database_service.retrieve_user_interaction_state(message.from_user.id)
        if not current_state or current_state.get("state") != "awaiting_banner_photo":
            return
        state_metadata = current_state.get("metadata", {})
        group_id = state_metadata.get("group_id")
        selected_month = state_metadata.get("month")
        highest_res_photo = message.photo
        stored_id = await database_service.store_monthly_banner(group_id, selected_month, highest_res_photo.file_id)
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🗑 Delete This Banner", callback_data=f"delete_banner:{stored_id}")],
            [InlineKeyboardButton(text="➕ Add Another Banner", callback_data=f"select_add_month:{selected_month.lower()}")]
        ])
        await message.reply(f"✅ Banner for **{selected_month}** saved successfully!\nYou can upload another photo for this month or finish.", reply_markup=inline_keyboard)

    @application.on_message(filters.command("get_banner") & filters.private)
    async def process_get_banner_command(client: Client, message: Message):
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ No group connected. Use `/connect_grp <group_id>` first.")
        distinct_months = await database_service.retrieve_distinct_banner_months(connected_group["group_id"])
        if not distinct_months:
            return await message.reply("No banners uploaded yet. Use `/add_banner` to upload one.")
        markup = markup_builder.construct_month_selection_markup(distinct_months, "fetch_banner_month")
        return await message.reply("Select the month to view banners:", reply_markup=markup)

    @application.on_callback_query(filters.regex(r"^fetch_banner_month:(.+)"))
    async def process_fetch_banner_callback(client: Client, query: CallbackQuery):
        selected_month = query.matches[0].group(1).capitalize()
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        banners_list = await database_service.retrieve_banners_by_month(connected_group["group_id"], selected_month)
        if not banners_list:
            return await query.message.edit_text(f"No banners found for **{selected_month}**.")
        await query.message.delete()
        for banner in banners_list:
            deletion_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🗑 Delete Banner", callback_data=f"delete_banner:{str(banner['_id'])}")]])
            await client.send_photo(chat_id=query.from_user.id, photo=banner["telegram_file_id"], caption=f"📅 Banner for **{selected_month}**", reply_markup=deletion_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^delete_banner:(.+)"))
    async def process_delete_banner_callback(client: Client, query: CallbackQuery):
        banner_db_id = query.matches[0].group(1)
        await database_service.delete_banner_by_id(banner_db_id)
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("Banner deleted from database.", show_alert=True)

    @application.on_message(filters.command("custom_btn") & filters.private)
    async def process_custom_buttons_command(client: Client, message: Message):
        tokens = message.text.split(maxsplit=1)
        if len(tokens) < 2:
            instructions = (
                "To add custom buttons for your updates, send lines formatted like:\n\n"
                "`/custom_btn`\n"
                "`btn - View Website - https://example.com`\n"
                "`btn - Rules - alert:Be respectful to community members`"
            )
            return await message.reply(instructions)
        parsed_buttons = markup_builder.parse_custom_markup_definitions(tokens[1], entities=message.entities)
        if not parsed_buttons:
            return await message.reply("❌ No valid buttons parsed. Follow the format: `btn - Title - URL/alert:text`")
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ No group connected. Use `/connect_grp <group_id>` first.")
        await database_service.update_custom_buttons(connected_group["group_id"], parsed_buttons)
        preview_markup = markup_builder.build_inline_keyboard_from_definitions(parsed_buttons, enable_rich_styles=True)
        return await message.reply("✅ Custom buttons saved with rich styles & premium emojis! Here is a preview:", reply_markup=preview_markup)

    @application.on_message(filters.command("custom_links") & filters.private)
    async def process_custom_links_command(client: Client, message: Message):
        tokens = message.text.split(maxsplit=1)
        if len(tokens) < 2:
            instructions = (
                "To add custom rich-text links to your monthly update message, send lines like:\n\n"
                "`/custom_links`\n"
                "`link - Documentation - https://example.com/docs`\n"
                "`link - Support Group - @YourSupportChat`\n"
                "`link - Changelogs - https://example.com/changelogs`"
            )
            return await message.reply(instructions)
        from pyrogram.parser import Parser
        if message.entities:
            rich_full = Parser.unparse(message.text, message.entities, is_html=True)
            rich_tokens = rich_full.split(maxsplit=1)
            raw_input = rich_tokens[1] if len(rich_tokens) >= 2 else tokens[1]
        else:
            raw_input = tokens[1]
        parsed_links = markup_builder.parse_custom_links_definitions(raw_input)
        if not parsed_links:
            return await message.reply("❌ No valid links parsed. Follow format: `link - Title - URL`")
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ No group connected. Use `/connect_grp <group_id>` first.")
        await database_service.update_custom_links(connected_group["group_id"], parsed_links)
        overview = "\n".join([f"• <b>{l['title']}</b> → {l['target']}" for l in parsed_links])
        return await message.reply(
            f"✅ <b>Custom links saved!</b>\n\n{overview}\n\n<i>These links will appear at the bottom of your update broadcasts!</i>",
            parse_mode=ParseMode.HTML
        )

    @application.on_callback_query(filters.regex(r"^notify_alert:(.+)"))
    async def process_notify_alert_callback(client: Client, query: CallbackQuery):
        alert_text = query.matches[0].group(1)
        await query.answer(alert_text, show_alert=True)
