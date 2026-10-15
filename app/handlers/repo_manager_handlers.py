import httpx
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus
from app.database.database import database_service
from app.services.github_api import github_api_service

def resolve_repo_by_ref(repos_list: list, repo_ref: str):
    if not repos_list:
        return None, -1, {}
    repo_ref_str = str(repo_ref).strip()
    if repo_ref_str.isdigit():
        idx = int(repo_ref_str)
        if 0 <= idx < len(repos_list):
            item = repos_list[idx]
            name = item.get("name") if isinstance(item, dict) else item
            item_dict = item if isinstance(item, dict) else {"name": name}
            return name, idx, item_dict
    for idx, item in enumerate(repos_list):
        name = item.get("name") if isinstance(item, dict) else item
        if name.lower() == repo_ref_str.lower():
            item_dict = item if isinstance(item, dict) else {"name": name}
            return name, idx, item_dict
    first = repos_list[0]
    first_name = first.get("name") if isinstance(first, dict) else first
    first_dict = first if isinstance(first, dict) else {"name": first_name}
    return first_name, 0, first_dict

def construct_repo_control_keyboard(
    repo_ref: str,
    commits_state: bool,
    issues_state: bool,
    private_alerts: bool = False,
    auto_delete_24h: bool = False,
    has_channel: bool = False,
    releases_state: bool = True,
    workflows_state: bool = True,
    stars_state: bool = True
):
    commits_btn_text = "🟢 Commits: ON" if commits_state else "🔴 Commits: OFF"
    issues_btn_text = "🟢 Issues & PRs: ON" if issues_state else "🔴 Issues & PRs: OFF"
    releases_btn_text = "🟢 Releases: ON" if releases_state else "🔴 Releases: OFF"
    workflows_btn_text = "🟢 CI/CD Workflows: ON" if workflows_state else "🔴 CI/CD Workflows: OFF"
    stars_btn_text = "🟢 Stars & Forks: ON" if stars_state else "🔴 Stars & Forks: OFF"
    dest_btn_text = "🔒 Destination: Private DM 👤" if private_alerts else "📢 Destination: Group/Channel 👥"
    auto_del_btn_text = "⏳ Group Auto-Delete (24h): ON 🟢" if auto_delete_24h else "⏳ Group Auto-Delete (24h): OFF 🔴"
    chan_button = (
        InlineKeyboardButton(text="❌ Disconnect Log Channel", callback_data=f"unlink_ch:{repo_ref}")
        if has_channel else
        InlineKeyboardButton(text="📢 Set Dedicated Log Channel", callback_data=f"ask_repo_channel:{repo_ref}")
    )
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text=commits_btn_text, callback_data=f"toggle_repo:{repo_ref}:cmt"),
            InlineKeyboardButton(text=issues_btn_text, callback_data=f"toggle_repo:{repo_ref}:iss")
        ],
        [
            InlineKeyboardButton(text=releases_btn_text, callback_data=f"toggle_repo:{repo_ref}:rel"),
            InlineKeyboardButton(text=workflows_btn_text, callback_data=f"toggle_repo:{repo_ref}:wf")
        ],
        [
            InlineKeyboardButton(text=stars_btn_text, callback_data=f"toggle_repo:{repo_ref}:str")
        ],
        [InlineKeyboardButton(text=dest_btn_text, callback_data=f"toggle_repo:{repo_ref}:pvt")],
        [InlineKeyboardButton(text=auto_del_btn_text, callback_data=f"toggle_repo:{repo_ref}:del24")],
        [
            InlineKeyboardButton(text="🖼️ Manage Banners", callback_data=f"repo_banners:{repo_ref}"),
            InlineKeyboardButton(text="🚀 Preview Updates", callback_data=f"repo_preview:{repo_ref}")
        ],
        [chan_button],
        [InlineKeyboardButton(text="📋 View Active Issues", callback_data=f"view_issues:{repo_ref}")],
        [InlineKeyboardButton(text="⚠️ Close All PRs", callback_data=f"ask_close_prs:{repo_ref}")],
        [InlineKeyboardButton(text="🗑 Delete Repository", callback_data=f"ask_delete_repo:{repo_ref}")],
        [InlineKeyboardButton(text="🔌 Disconnect Group", callback_data="ask_disconnect_group")],
        [InlineKeyboardButton(text="🔙 Back to Repos", callback_data="back_to_repo_list")]
    ])

def register_repo_manager_handlers(application: Client):

    @application.on_message(filters.command("repos") & filters.private)
    async def process_list_repos_command(client: Client, message: Message):
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group:
            return await message.reply("❌ No group connected yet. Use `/connect_grp <group_id>` first.")
        group_id = connected_group["group_id"]
        repos_list = await database_service.retrieve_connected_repositories(group_id)
        if not repos_list:
            return await message.reply("No repositories added yet. Link one using `/set_repo owner/repository`.")
        keyboard_buttons = []
        for idx, repo in enumerate(repos_list):
            repo_name = repo.get("name") if isinstance(repo, dict) else repo
            keyboard_buttons.append([InlineKeyboardButton(text=f"📦 {repo_name}", callback_data=f"manage_repo:{idx}")])
        return await message.reply(
            f"📂 <b>Connected Repositories for {connected_group['group_title']}</b>\n\nClick a repository to manage its settings:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )

    @application.on_callback_query(filters.regex(r"^manage_repo:(.+)"))
    async def process_manage_repo_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, target_repo_info = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)

        commits_state = target_repo_info.get("commits_enabled", True)
        issues_state = target_repo_info.get("issues_enabled", True)
        releases_state = target_repo_info.get("releases_enabled", True)
        workflows_state = target_repo_info.get("workflows_enabled", True)
        stars_state = target_repo_info.get("stars_enabled", True)
        private_alerts = target_repo_info.get("private_alerts", False)
        auto_delete_24h = target_repo_info.get("auto_delete_24h", False)
        channel_val = (target_repo_info.get("channel_id") if isinstance(target_repo_info, dict) else None) or connected_group.get("channel_id")
        has_channel = bool(channel_val)
        control_keyboard = construct_repo_control_keyboard(
            str(repo_idx),
            commits_state,
            issues_state,
            private_alerts,
            auto_delete_24h,
            has_channel=has_channel,
            releases_state=releases_state,
            workflows_state=workflows_state,
            stars_state=stars_state
        )
        dest_label = "🔒 Private DM (Bot Chat)" if private_alerts else "📢 Public (Group & Channel)"
        auto_del_label = "🟢 Enabled (Purged after 24h)" if auto_delete_24h else "🔴 Disabled"
        channel_info = f"<code>{channel_val}</code>" if channel_val else "<i>Not Set (Alerts sent to group)</i>"
        panel_text = (
            f"⚙️ <b>Repository Control Panel</b>\n\n"
            f"Repository: <b>{repo_name}</b>\n"
            f"• Commits: <b>{'🟢 Enabled' if commits_state else '🔴 Disabled'}</b>\n"
            f"• Issues & PRs: <b>{'🟢 Enabled' if issues_state else '🔴 Disabled'}</b>\n"
            f"• Releases: <b>{'🟢 Enabled' if releases_state else '🔴 Disabled'}</b>\n"
            f"• CI/CD Workflows: <b>{'🟢 Enabled' if workflows_state else '🔴 Disabled'}</b>\n"
            f"• Stars & Forks: <b>{'🟢 Enabled' if stars_state else '🔴 Disabled'}</b>\n"
            f"• Dedicated Log Channel: {channel_info}\n"
            f"• Alert Destination: <b>{dest_label}</b>\n"
            f"• Group Auto-Delete (24h): <b>{auto_del_label}</b>\n\n"
            f"ℹ️ <i>Routing: When Log Channel is set, commits route to Log Channel. Issues, Releases, CI/CD, and Stars route to Log Channel & Connected Group.</i>\n\n"
            f"Select an action below to configure:"
        )
        await query.message.edit_text(panel_text, parse_mode=ParseMode.HTML, reply_markup=control_keyboard)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^repo_preview:(.+)"))
    async def process_repo_preview_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        await query.answer("Generating preview...", show_alert=False)
        from app.handlers.release_handlers import build_and_deliver_preview
        await build_and_deliver_preview(client, query.from_user.id, connected_group, specific_repo=repo_name)

    @application.on_callback_query(filters.regex(r"^repo_banners:(.+)"))
    async def process_repo_banners_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        group_id = connected_group["group_id"]
        distinct_months = await database_service.retrieve_distinct_banner_months(group_id)
        keyboard = []
        if distinct_months:
            keyboard.append([InlineKeyboardButton(text="📂 View Uploaded Banners", callback_data="get_banner_shortcut")])
        keyboard.append([InlineKeyboardButton(text="➕ Upload New Banner", callback_data="select_add_month:october")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Repo Settings", callback_data=f"manage_repo:{repo_idx}")])
        banners_status = f"{len(distinct_months)} month(s) with banners" if distinct_months else "No banners uploaded yet"
        text = (
            f"🖼️ <b>Banner Management for {repo_name}</b>\n\n"
            f"Current Status: <b>{banners_status}</b>\n\n"
            f"Monthly banners appear as header photos in release broadcasts.\n"
            f"Use the buttons below or /add_banner to manage photos:"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()

    @application.on_callback_query(filters.regex(r"^ask_delete_repo:(.+)"))
    async def process_ask_delete_repo(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🗑 YES, Delete Repository", callback_data=f"confirm_delete_repo:{repo_idx}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"manage_repo:{repo_idx}")]
        ])
        await query.message.edit_text(
            f"⚠️ <b>Delete Connected Repository</b>\n\n"
            f"Are you sure you want to disconnect and delete <b>{repo_name}</b>?\n"
            f"<i>The bot will stop tracking commits and issues for this repository.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_markup
        )
        await query.answer()

    @application.on_callback_query(filters.regex(r"^confirm_delete_repo:(.+)"))
    async def process_confirm_delete_repo(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        await database_service.delete_connected_repository(connected_group["group_id"], repo_name)
        await query.answer(f"Deleted {repo_name} successfully!", show_alert=True)
        updated_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        keyboard_buttons = []
        for idx, repo in enumerate(updated_list):
            r_name = repo.get("name") if isinstance(repo, dict) else repo
            keyboard_buttons.append([InlineKeyboardButton(text=f"📦 {r_name}", callback_data=f"manage_repo:{idx}")])
        if not keyboard_buttons:
            return await query.message.edit_text(
                f"✅ <b>Repository {repo_name} disconnected!</b>\n\nNo other repositories connected. Send /set_repo to add one.",
                parse_mode=ParseMode.HTML
            )
        await query.message.edit_text(
            f"✅ <b>Repository {repo_name} deleted!</b>\n\nRemaining connected repositories:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )

    @application.on_callback_query(filters.regex(r"^toggle_repo:(.+):(.+)"))
    async def process_toggle_repo_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        setting_code = query.matches[0].group(2)
        setting_map = {
            "cmt": "commits_enabled",
            "commits_enabled": "commits_enabled",
            "iss": "issues_enabled",
            "issues_enabled": "issues_enabled",
            "rel": "releases_enabled",
            "releases_enabled": "releases_enabled",
            "wf": "workflows_enabled",
            "workflows_enabled": "workflows_enabled",
            "str": "stars_enabled",
            "stars_enabled": "stars_enabled",
            "pvt": "private_alerts",
            "private_alerts": "private_alerts",
            "del24": "auto_delete_24h",
            "auto_delete_24h": "auto_delete_24h"
        }
        setting_key = setting_map.get(setting_code, setting_code)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, target_repo_info = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)

        new_val = await database_service.toggle_repository_setting(connected_group["group_id"], repo_name, setting_key)
        if setting_key == "private_alerts":
            state_label = "PRIVATE DM (BOT CHAT)" if new_val else "PUBLIC (GROUP / CHANNEL)"
            await query.answer(f"Commit alerts set to: {state_label}!", show_alert=True)
        elif setting_key == "auto_delete_24h":
            state_label = "ENABLED (PR & Issue alerts in group will auto-delete in 24h)" if new_val else "DISABLED"
            await query.answer(f"Group Auto-Delete (24h): {state_label}!", show_alert=True)
        else:
            state_label = "ENABLED" if new_val else "DISABLED"
            await query.answer(f"{setting_key.replace('_', ' ').title()} {state_label}!", show_alert=True)

        refreshed_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        _, _, refreshed_info = resolve_repo_by_ref(refreshed_list, str(repo_idx))
        commits_state = refreshed_info.get("commits_enabled", True)
        issues_state = refreshed_info.get("issues_enabled", True)
        releases_state = refreshed_info.get("releases_enabled", True)
        workflows_state = refreshed_info.get("workflows_enabled", True)
        stars_state = refreshed_info.get("stars_enabled", True)
        private_alerts = refreshed_info.get("private_alerts", False)
        auto_delete_24h = refreshed_info.get("auto_delete_24h", False)
        channel_val = (refreshed_info.get("channel_id") if isinstance(refreshed_info, dict) else None) or connected_group.get("channel_id")
        has_channel = bool(channel_val)
        control_keyboard = construct_repo_control_keyboard(
            str(repo_idx),
            commits_state,
            issues_state,
            private_alerts,
            auto_delete_24h,
            has_channel=has_channel,
            releases_state=releases_state,
            workflows_state=workflows_state,
            stars_state=stars_state
        )
        dest_label = "🔒 Private DM (Bot Chat)" if private_alerts else "📢 Public (Group & Channel)"
        auto_del_label = "🟢 Enabled (Purged after 24h)" if auto_delete_24h else "🔴 Disabled"
        channel_info = f"<code>{channel_val}</code>" if channel_val else "<i>Not Set (Alerts sent to group)</i>"
        panel_text = (
            f"⚙️ <b>Repository Control Panel</b>\n\n"
            f"Repository: <b>{repo_name}</b>\n"
            f"• Commits: <b>{'🟢 Enabled' if commits_state else '🔴 Disabled'}</b>\n"
            f"• Issues & PRs: <b>{'🟢 Enabled' if issues_state else '🔴 Disabled'}</b>\n"
            f"• Releases: <b>{'🟢 Enabled' if releases_state else '🔴 Disabled'}</b>\n"
            f"• CI/CD Workflows: <b>{'🟢 Enabled' if workflows_state else '🔴 Disabled'}</b>\n"
            f"• Stars & Forks: <b>{'🟢 Enabled' if stars_state else '🔴 Disabled'}</b>\n"
            f"• Dedicated Log Channel: {channel_info}\n"
            f"• Alert Destination: <b>{dest_label}</b>\n"
            f"• Group Auto-Delete (24h): <b>{auto_del_label}</b>\n\n"
            f"ℹ️ <i>Routing: When Log Channel is set, commits route to Log Channel. Issues, Releases, CI/CD, and Stars route to Log Channel & Connected Group.</i>\n\n"
            f"Select an action below to configure:"
        )
        await query.message.edit_text(panel_text, parse_mode=ParseMode.HTML, reply_markup=control_keyboard)

    @application.on_callback_query(filters.regex(r"^unlink_ch:(.+)"))
    async def process_unlink_channel_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        await database_service.disconnect_connected_channel(connected_group["group_id"], owner_id=query.from_user.id)
        await query.answer("Log channel disconnected! Alerts will now route to your group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, target_repo_info = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.message.edit_text("Repository settings updated.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_repo_list")]]))
        commits_state = target_repo_info.get("commits_enabled", True)
        issues_state = target_repo_info.get("issues_enabled", True)
        releases_state = target_repo_info.get("releases_enabled", True)
        workflows_state = target_repo_info.get("workflows_enabled", True)
        stars_state = target_repo_info.get("stars_enabled", True)
        private_alerts = target_repo_info.get("private_alerts", False)
        auto_delete_24h = target_repo_info.get("auto_delete_24h", False)
        control_keyboard = construct_repo_control_keyboard(
            str(repo_idx),
            commits_state,
            issues_state,
            private_alerts,
            auto_delete_24h,
            has_channel=False,
            releases_state=releases_state,
            workflows_state=workflows_state,
            stars_state=stars_state
        )
        dest_label = "🔒 Private DM (Bot Chat)" if private_alerts else "📢 Public (Group)"
        auto_del_label = "🟢 Enabled (Purged after 24h)" if auto_delete_24h else "🔴 Disabled"
        panel_text = (
            f"⚙️ <b>Repository Control Panel</b>\n\n"
            f"Repository: <b>{repo_name}</b>\n"
            f"• Commits: <b>{'🟢 Enabled' if commits_state else '🔴 Disabled'}</b>\n"
            f"• Issues & PRs: <b>{'🟢 Enabled' if issues_state else '🔴 Disabled'}</b>\n"
            f"• Releases: <b>{'🟢 Enabled' if releases_state else '🔴 Disabled'}</b>\n"
            f"• CI/CD Workflows: <b>{'🟢 Enabled' if workflows_state else '🔴 Disabled'}</b>\n"
            f"• Stars & Forks: <b>{'🟢 Enabled' if stars_state else '🔴 Disabled'}</b>\n"
            f"• Dedicated Log Channel: <i>Not Set (Alerts sent to group)</i>\n"
            f"• Alert Destination: <b>{dest_label}</b>\n"
            f"• Group Auto-Delete (24h): <b>{auto_del_label}</b>\n\n"
            f"Select an action below to configure:"
        )
        await query.message.edit_text(panel_text, parse_mode=ParseMode.HTML, reply_markup=control_keyboard)

    @application.on_callback_query(filters.regex(r"^ask_disconnect_group$"))
    async def process_ask_disconnect_group_callback(client: Client, query: CallbackQuery):
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🔌 YES, Disconnect Group", callback_data="confirm_disconnect_group")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_repo_list")]
        ])
        await query.message.edit_text(
            f"⚠️ <b>Disconnect Group: {connected_group['group_title']}?</b>\n\n"
            f"This will unlink the group and stop broadcast tracking for all its repositories.\n"
            f"You can reconnect anytime using <code>/connect_grp &lt;group_id&gt;</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_markup
        )
        await query.answer()

    @application.on_callback_query(filters.regex(r"^confirm_disconnect_group$"))
    async def process_confirm_disconnect_group_callback(client: Client, query: CallbackQuery):
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        group_title = connected_group["group_title"]
        await database_service.disconnect_group(connected_group["group_id"], owner_id=query.from_user.id)
        await query.answer("Group disconnected successfully!", show_alert=True)
        return await query.message.edit_text(
            f"✅ <b>Group Disconnected</b>\n\n"
            f"<b>{group_title}</b> has been disconnected from your account.\n"
            f"Use <code>/connect_grp &lt;group_id&gt;</code> to connect another group at any time.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_start_menu")]])
        )

    @application.on_callback_query(filters.regex(r"^back_to_repo_list$"))
    async def process_back_to_repos(client: Client, query: CallbackQuery):
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("⚠️ No group connected yet! Use /connect_grp first.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        if not repos_list:
            return await query.answer("⚠️ No repositories connected yet! Use /set_repo to add one.", show_alert=True)
        keyboard_buttons = []
        for idx, repo in enumerate(repos_list):
            repo_name = repo.get("name") if isinstance(repo, dict) else repo
            keyboard_buttons.append([InlineKeyboardButton(text=f"📦 {repo_name}", callback_data=f"manage_repo:{idx}")])
        keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_start_menu")])
        await query.message.edit_text(
            f"📂 <b>Connected Repositories for {connected_group['group_title']}</b>\n\nClick a repository to manage its settings:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )
        await query.answer()

    @application.on_callback_query(filters.regex(r"^ask_close_prs:(.+)"))
    async def process_ask_close_prs(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🚨 YES, Close All Open PRs", callback_data=f"confirm_close_prs:{repo_idx}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"manage_repo:{repo_idx}")]
        ])
        prompt_text = (
            f"⚠️ <b>CONFIRM ACTION</b> ⚠️\n\n"
            f"Are you sure you want to close <b>ALL open Pull Requests</b> in <code>{repo_name}</code>?\n\n"
            f"<i>This will close all open PRs immediately without notice!</i>"
        )
        await query.message.edit_text(prompt_text, parse_mode=ParseMode.HTML, reply_markup=confirm_keyboard)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^confirm_close_prs:(.+)"))
    async def process_confirm_close_prs(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        await query.answer("Closing PRs in progress...", show_alert=False)
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            open_prs = await github_api_service.fetch_open_pull_requests(http_client, repo_name)
            if not open_prs:
                return await query.message.edit_text(
                    f"ℹ️ No open Pull Requests found in <b>{repo_name}</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data=f"manage_repo:{repo_idx}")]])
                )
            closed_count = 0
            pr_summaries = []
            for pr in open_prs:
                pr_num = pr.get("number")
                pr_title = pr.get("title", "")
                success = await github_api_service.close_single_pull_request(http_client, repo_name, pr_num)
                if success:
                    closed_count += 1
                    pr_summaries.append(f"• #{pr_num}: <s>{pr_title}</s>")
        summary_text = (
            f"🔒 <b>Closed Pull Requests Summary</b>\n\n"
            f"Repository: <b>{repo_name}</b>\n"
            f"Total Closed: <b>{closed_count}</b>\n\n"
            f"<b>Details:</b>\n" + "\n".join(pr_summaries[:20]) +
            f"\n\n<i>All open PRs have been closed without notice.</i>"
        )
        await query.message.edit_text(
            summary_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back to Settings", callback_data=f"manage_repo:{repo_idx}")]])
        )

    @application.on_callback_query(filters.regex(r"^view_issues:(.+)"))
    async def process_view_issues_callback(client: Client, query: CallbackQuery):
        repo_ref = query.matches[0].group(1)
        connected_group = await database_service.retrieve_connected_group_by_owner(query.from_user.id)
        if not connected_group:
            return await query.answer("No connected group.", show_alert=True)
        repos_list = await database_service.retrieve_connected_repositories(connected_group["group_id"])
        repo_name, repo_idx, _ = resolve_repo_by_ref(repos_list, repo_ref)
        if not repo_name:
            return await query.answer("Repository not found.", show_alert=True)
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            active_issues = await github_api_service.fetch_active_issues(http_client, repo_name)
        if not active_issues:
            return await query.message.edit_text(
                f"🎉 No active open issues in <b>{repo_name}</b>!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data=f"manage_repo:{repo_idx}")]])
            )
        cards = [f"📋 <b>Active Issues in {repo_name}</b>\n"]
        for issue in active_issues[:10]:
            num = issue.get("number")
            title = issue.get("title", "")
            author = issue.get("user", {}).get("login", "")
            url = issue.get("html_url", "")
            labels = ", ".join([f"<code>{l['name']}</code>" for l in issue.get("labels", [])])
            labels_str = f" | {labels}" if labels else ""
            cards.append(
                f"🔹 <b>#{num} <a href=\"{url}\">{title}</a></b>\n"
                f"   👤 Opened by: @{author}{labels_str}\n"
            )
        message_text = "\n".join(cards)
        await query.message.edit_text(
            message_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back to Settings", callback_data=f"manage_repo:{repo_idx}")]])
        )
        await query.answer()

    @application.on_message(filters.command(["autodelete", "autoclean"]))
    async def process_autodelete_command(client: Client, message: Message):
        user_id = message.from_user.id
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            try:
                member = await client.get_chat_member(message.chat.id, user_id)
                if member.status != ChatMemberStatus.OWNER:
                    return await message.reply("❌ Only the group owner can change alert auto-delete settings.")
            except Exception:
                return await message.reply("❌ Bot requires administrator rights to verify group owner status.")
            group_id = message.chat.id
        else:
            connected_group = await database_service.retrieve_connected_group_by_owner(user_id)
            if not connected_group:
                return await message.reply("❌ No connected group found. Use /connect_grp first.")
            group_id = connected_group["group_id"]

        new_val = await database_service.toggle_all_repositories_setting(group_id, "auto_delete_24h")
        if new_val:
            await message.reply(
                "⏳ <b>Auto-Delete Group Alerts (24 Hours) ENABLED! 🟢</b>\n\n"
                "All Pull Request and Issue alerts posted to this group will automatically be deleted after 24 hours.\n\n"
                "<i>Ensure @CommitCastBot has 'Delete Messages' permission in this group.</i>",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply(
                "⏳ <b>Auto-Delete Group Alerts (24 Hours) DISABLED! 🔴</b>\n\n"
                "Alerts posted to this group will now remain permanently in chat history.",
                parse_mode=ParseMode.HTML
            )
