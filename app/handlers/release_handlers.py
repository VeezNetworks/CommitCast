import httpx
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.parser import Parser
from app.core.config import system_config
from app.database.database import database_service
from app.utils.changelog import changelog_service
from app.handlers.keyboards import markup_builder
from app.services.github_api import github_api_service

EXAMPLE_TEMPLATES = {
    1: (
        "<tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Conference Calls, Bindings and Core Updates!</b>\n\n"
        "<tg-emoji emoji-id=\"5368324170671202288\">🎉</tg-emoji> <b>What's New?</b>\n"
        "• <b>End-to-End Encrypted Calls</b> – Added full support for Telegram conference calls, invite joins, and screen sharing.\n"
        "• <b>Node.js & Rust Bindings</b> – Published on npm and crates.io with a unified schema across all languages.\n"
        "• <b>macOS Media Capturing</b> – Camera and microphone enumeration with AVFoundation capturer.\n\n"
        "<tg-emoji emoji-id=\"5368324170671202287\">‼️</tg-emoji> <b>Breaking Changes</b>\n"
        "• Support for <b>Hydrogram</b> has been deprecated. Pyrogram & Telethon remain supported.\n"
        "• Renamed internal symbols for cross-platform consistency.\n\n"
        "<blockquote>\n"
        "<tg-emoji emoji-id=\"5368324170671202286\">💡</tg-emoji> <b>Testing Note:</b>\n"
        "Check out our latest builds and report any issues in our community chat!\n"
        "</blockquote>"
    ),
    2: (
        "<tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Major Release v2.0 Is Here!</b>\n\n"
        "<tg-emoji emoji-id=\"5368324170671202288\">🎉</tg-emoji> <b>Key Highlights:</b>\n"
        "• <b>Next-Gen Core Architecture</b> – Rebuilt from the ground up for maximum throughput and minimal resource usage.\n"
        "• <b>Cross-Platform Engine</b> – Full compatibility across Linux, macOS, and Windows environments.\n"
        "• <b>Security Hardening</b> – Upgraded all internal dependencies to the latest stable versions.\n\n"
        "<blockquote expandable>\n"
        "<tg-emoji emoji-id=\"5368324170671202288\">🚀</tg-emoji> <b>Changelog Details:</b>\n"
        "Tap to expand for full technical migration steps and detailed commit references.\n"
        "</blockquote>"
    ),
    3: (
        "<tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Monthly Maintenance & Stability Updates</b>\n\n"
        "<tg-emoji emoji-id=\"5368324170671202288\">🎉</tg-emoji> <b>Summary of Changes:</b>\n"
        "• <b>Bug Fixes & Patching</b> – Addressed edge-case issues reported by community developers.\n"
        "• <b>Performance Optimizations</b> – Refined internal routines and eliminated latency bottlenecks.\n\n"
        "<blockquote>\n"
        "<tg-emoji emoji-id=\"5368324170671202286\">💡</tg-emoji> <b>Release Status:</b>\n"
        "All builds are verified and passing automated continuous integration suites.\n"
        "</blockquote>"
    )
}

async def build_and_deliver_preview(client: Client, user_id: int, group_record: dict, target_message: Message = None, specific_repo: str = None):
    group_id = group_record["group_id"]
    is_dev_admin = (user_id == system_config.developer_owner_id)
    repos_list = await database_service.retrieve_connected_repositories(group_id)
    repo_name = specific_repo
    if not repo_name and repos_list:
        first_repo = repos_list[0]
        repo_name = first_repo.get("name") if isinstance(first_repo, dict) else first_repo
    if not repo_name:
        repo_name = group_record.get("repository") or "Repository"
    now_utc = datetime.utcnow()
    current_month_str = now_utc.strftime("%B")
    month_start = datetime(now_utc.year, now_utc.month, 1, 0, 0, 0)
    commits_records = await database_service.fetch_commits_in_timespan(group_id, month_start, now_utc, repository_name=repo_name)
    if not commits_records and repo_name and repo_name != "Repository":
        user_token = await database_service.retrieve_user_github_token(user_id)
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            gh_commits = await github_api_service.fetch_repository_commits_since(
                http_client, repo_name, month_start.isoformat() + "Z", token=user_token
            )
        if gh_commits:
            for item in gh_commits:
                commit_sha = item.get("sha")
                commit_msg = item.get("commit", {}).get("message", "")
                author_name = item.get("commit", {}).get("author", {}).get("name", "Unknown")
                commit_date = item.get("commit", {}).get("author", {}).get("date", "")
                await database_service.record_github_commit(
                    group_id=group_id,
                    commit_identifier=commit_sha,
                    commit_message=commit_msg,
                    author_name=author_name,
                    repository_name=repo_name,
                    timestamp_iso=commit_date
                )
            commits_records = await database_service.fetch_commits_in_timespan(group_id, month_start, now_utc, repository_name=repo_name)
    custom_template = group_record.get("custom_template")
    custom_links = group_record.get("custom_links", [])
    is_premium = group_record.get("is_premium", True) if is_dev_admin else group_record.get("is_premium", False)
    if custom_template:
        release_text = custom_template
    else:
        release_text = changelog_service.generate_release_notes_text(
            month_title=current_month_str,
            commits_list=commits_records,
            repository_name=repo_name,
            custom_links=custom_links,
            is_premium=is_premium
        )
    action_buttons = [
        [InlineKeyboardButton(text="🚀 Send Update to Group/Channel", callback_data=f"broadcast_update:{group_id}:{current_month_str}")],
        [InlineKeyboardButton(text="✏️ Customize Message", callback_data=f"edit_template:{group_id}")],
        [
            InlineKeyboardButton(text="🔘 Manage Buttons", callback_data=f"manage_buttons:{group_id}"),
            InlineKeyboardButton(text="🔗 Customize Links", callback_data=f"manage_links:{group_id}")
        ]
    ]
    preview_keyboard = []
    custom_buttons = group_record.get("custom_buttons", [])
    if custom_buttons:
        user_button_rows = markup_builder.build_inline_keyboard_from_definitions(custom_buttons, enable_rich_styles=True)
        if user_button_rows and user_button_rows.inline_keyboard:
            preview_keyboard.extend(user_button_rows.inline_keyboard)
    preview_keyboard.extend(action_buttons)
    inline_controls = InlineKeyboardMarkup(preview_keyboard)
    banners_list = await database_service.retrieve_banners_by_month(group_id, current_month_str)
    if banners_list:
        selected_banner = banners_list[0]
        if len(release_text) <= 1024:
            return await client.send_photo(
                chat_id=user_id,
                photo=selected_banner["telegram_file_id"],
                caption=release_text,
                parse_mode=ParseMode.HTML,
                reply_markup=inline_controls
            )
        else:
            await client.send_photo(
                chat_id=user_id,
                photo=selected_banner["telegram_file_id"],
                caption=f"✨ <b>{current_month_str} Release Preview</b>",
                parse_mode=ParseMode.HTML
            )
            return await client.send_message(
                chat_id=user_id,
                text=release_text,
                parse_mode=ParseMode.HTML,
                reply_markup=inline_controls
            )
    else:
        full_text = f"{release_text}\n\n<i>⚠️ Note: No banner found for {current_month_str}. Upload one with /add_banner!</i>"
        return await client.send_message(
            chat_id=user_id,
            text=full_text,
            parse_mode=ParseMode.HTML,
            reply_markup=inline_controls
        )

def register_release_handlers(application: Client):

    @application.on_message(filters.command("preview_update") & filters.private)
    async def process_preview_update_command(client: Client, message: Message):
        is_dev_admin = (message.from_user.id == system_config.developer_owner_id)
        connected_group = await database_service.retrieve_connected_group_by_owner(message.from_user.id)
        if not connected_group and is_dev_admin:
            all_groups = await database_service.retrieve_all_tracked_groups()
            if all_groups:
                connected_group = all_groups[0]
        if not connected_group:
            return await message.reply("❌ No group connected. Use `/connect_grp <group_id>` first.")
        await build_and_deliver_preview(client, message.from_user.id, connected_group, target_message=message)

    @application.on_callback_query(filters.regex(r"^back_to_preview:(-?\d+)"))
    async def process_back_to_preview(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        group_record = await database_service.retrieve_group_by_id(group_id)
        if not group_record:
            return await query.answer("Group not found.", show_alert=True)
        await query.answer()
        await build_and_deliver_preview(client, query.from_user.id, group_record)

    @application.on_callback_query(filters.regex(r"^edit_template:(-?\d+)"))
    async def process_edit_template_callback(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        group_record = await database_service.retrieve_group_by_id(group_id)
        if not group_record:
            return await query.answer("Group not found.", show_alert=True)
        await database_service.set_user_interaction_state(
            query.from_user.id,
            "awaiting_custom_template",
            {"group_id": group_id}
        )
        has_custom = bool(group_record.get("custom_template"))
        template_status = "Customized template active" if has_custom else "Auto-generated from commits"
        prompt_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📝 Load Example 1: Features & Updates", callback_data=f"apply_template_example:{group_id}:1")],
            [InlineKeyboardButton(text="📝 Load Example 2: Major Release Notes", callback_data=f"apply_template_example:{group_id}:2")],
            [InlineKeyboardButton(text="📝 Load Example 3: Maintenance & Patches", callback_data=f"apply_template_example:{group_id}:3")],
            [InlineKeyboardButton(text="💡 Formatting Tags Guide", callback_data=f"show_template_guide:{group_id}")],
            [InlineKeyboardButton(text="🔄 Reset to Auto-Generated", callback_data=f"reset_template:{group_id}")],
            [InlineKeyboardButton(text="🔙 Back to Preview", callback_data=f"back_to_preview:{group_id}")]
        ])
        prompt_text = (
            f"✏️ <b>Customize Release Update Message</b>\n\n"
            f"Current Status: <b>{template_status}</b>\n\n"
            f"• Tap any of the <b>Load Example</b> buttons below to instantly fill a rich pre-formatted template.\n"
            f"• Or send your own text right here in chat (supports custom premium emojis, <b>bold</b>, <i>italic</i>, <code>code</code>, <blockquote>quotes</blockquote>).\n\n"
            f"<i>Tap an option below:</i>"
        )
        await query.message.edit_text(prompt_text, parse_mode=ParseMode.HTML, reply_markup=prompt_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^apply_template_example:(-?\d+):(\d+)"))
    async def process_apply_template_example(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        template_idx = int(query.matches[0].group(2))
        selected_text = EXAMPLE_TEMPLATES.get(template_idx, EXAMPLE_TEMPLATES[1])
        await database_service.update_custom_template(group_id, selected_text)
        await database_service.reset_user_interaction_state(query.from_user.id)
        await query.answer(f"Example {template_idx} loaded successfully!", show_alert=True)
        group_record = await database_service.retrieve_group_by_id(group_id)
        await build_and_deliver_preview(client, query.from_user.id, group_record)

    @application.on_callback_query(filters.regex(r"^show_template_guide:(-?\d+)"))
    async def process_show_template_guide(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        guide_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📝 Load Example 1", callback_data=f"apply_template_example:{group_id}:1")],
            [InlineKeyboardButton(text="📝 Load Example 2", callback_data=f"apply_template_example:{group_id}:2")],
            [InlineKeyboardButton(text="🔙 Back to Customizer", callback_data=f"edit_template:{group_id}")]
        ])
        guide_text = (
            f"💡 <b>Rich Formatting Tags & Fillings Guide</b>\n\n"
            f"You can use these tags in your custom release messages:\n\n"
            f"• <b>Bold:</b> <code>&lt;b&gt;text&lt;/b&gt;</code>\n"
            f"• <i>Italic:</i> <code>&lt;i&gt;text&lt;/i&gt;</code>\n"
            f"• <code>Code:</code> <code>&lt;code&gt;text&lt;/code&gt;</code>\n"
            f"• <blockquote>Quotes:</blockquote> <code>&lt;blockquote&gt;text&lt;/blockquote&gt;</code>\n"
            f"• <a href=\"https://example.com\">Links:</a> <code>&lt;a href=\"url\"&gt;label&lt;/a&gt;</code>\n"
            f"• <tg-emoji emoji-id=\"5368324170671202286\">✨</tg-emoji> <b>Custom Emojis:</b>\n"
            f"  Insert from your Telegram Premium keyboard or use:\n"
            f"  <code>&lt;tg-emoji emoji-id=\"...\"&gt;✨&lt;/tg-emoji&gt;</code>\n\n"
            f"<i>Tap below to load a pre-filled example or return to edit:</i>"
        )
        await query.message.edit_text(guide_text, parse_mode=ParseMode.HTML, reply_markup=guide_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^reset_template:(-?\d+)"))
    async def process_reset_template_callback(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        await database_service.reset_custom_template(group_id)
        await database_service.reset_user_interaction_state(query.from_user.id)
        await query.answer("Template reset to auto-generated!", show_alert=True)
        group_record = await database_service.retrieve_group_by_id(group_id)
        await build_and_deliver_preview(client, query.from_user.id, group_record)

    @application.on_message(filters.private & ~filters.command(["start", "help", "repos", "preview_update", "connect_grp", "set_channel", "set_repo", "add_banner", "get_banner", "custom_btn", "custom_links"]))
    async def process_text_state_inputs(client: Client, message: Message):
        user_state = await database_service.retrieve_user_interaction_state(message.from_user.id)
        if not user_state:
            return
        state_name = user_state.get("state")
        metadata = user_state.get("metadata", {})
        group_id = metadata.get("group_id")
        if state_name == "awaiting_custom_template" and group_id:
            if message.entities:
                extracted_html = Parser.unparse(message.text, message.entities, is_html=True)
            elif message.caption_entities:
                extracted_html = Parser.unparse(message.caption, message.caption_entities, is_html=True)
            else:
                extracted_html = message.text or message.caption or ""
            await database_service.update_custom_template(group_id, extracted_html)
            await database_service.reset_user_interaction_state(message.from_user.id)
            group_record = await database_service.retrieve_group_by_id(group_id)
            await message.reply(
                "✅ <b>Custom release message saved with premium emojis & rich formatting!</b>\n\nGenerating new preview below:",
                parse_mode=ParseMode.HTML
            )
            return await build_and_deliver_preview(client, message.from_user.id, group_record)
        elif state_name == "awaiting_custom_button" and group_id:
            raw_text = message.text or ""
            parsed = markup_builder.parse_custom_markup_definitions(raw_text, entities=message.entities)
            if not parsed:
                return await message.reply("❌ Invalid format. Please use:\n`btn - Button Title - https://link.com`\nor\n`btn - Button Title - alert:Alert text`\nor\n`btn - Button Title - https://link.com - primary`")
            group_record = await database_service.retrieve_group_by_id(group_id)
            existing_buttons = group_record.get("custom_buttons", [])
            existing_buttons.extend(parsed)
            await database_service.update_custom_buttons(group_id, existing_buttons)
            await database_service.reset_user_interaction_state(message.from_user.id)
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back to Preview", callback_data=f"back_to_preview:{group_id}")]])
            return await message.reply(f"✅ Added {len(parsed)} button(s) with rich styles & premium emojis!", reply_markup=markup)
        elif state_name == "awaiting_custom_link" and group_id:
            if message.entities:
                raw_links_html = Parser.unparse(message.text, message.entities, is_html=True)
            else:
                raw_links_html = message.text or ""
            parsed_links = markup_builder.parse_custom_links_definitions(raw_links_html)
            if not parsed_links:
                return await message.reply("❌ Invalid format. Please use:\n`link - Title - URL` (e.g. `link - Documentation - https://docs.example.com`)")
            group_record = await database_service.retrieve_group_by_id(group_id)
            existing_links = group_record.get("custom_links", [])
            existing_links.extend(parsed_links)
            await database_service.update_custom_links(group_id, existing_links)
            await database_service.reset_user_interaction_state(message.from_user.id)
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back to Preview", callback_data=f"back_to_preview:{group_id}")]])
            return await message.reply(f"✅ Added {len(parsed_links)} link(s) with rich emojis!", reply_markup=markup)

    @application.on_callback_query(filters.regex(r"^manage_buttons:(-?\d+)"))
    async def process_manage_buttons_callback(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        group_record = await database_service.retrieve_group_by_id(group_id)
        if not group_record:
            return await query.answer("Group not found.", show_alert=True)
        buttons_list = group_record.get("custom_buttons", [])
        overview = []
        for idx, btn in enumerate(buttons_list, start=1):
            extra = f" (style: {btn.get('style')})" if btn.get("style") and btn.get("style") != "default" else ""
            overview.append(f"{idx}. <b>{btn.get('caption')}</b> → <code>{btn.get('target')}</code>{extra}")
        buttons_text = "\n".join(overview) if overview else "<i>No custom buttons configured yet.</i>"
        panel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="➕ Add Custom Button", callback_data=f"add_custom_btn:{group_id}")],
            [InlineKeyboardButton(text="🗑 Clear All Buttons", callback_data=f"clear_custom_btns:{group_id}")],
            [InlineKeyboardButton(text="🔙 Back to Preview", callback_data=f"back_to_preview:{group_id}")]
        ])
        msg_text = (
            f"🔘 <b>Manage Custom Buttons</b>\n\n"
            f"<b>Active Buttons:</b>\n{buttons_text}\n\n"
            f"Tap an option below:"
        )
        await query.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=panel_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^add_custom_btn:(-?\d+)"))
    async def process_add_custom_btn(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        await database_service.set_user_interaction_state(
            query.from_user.id,
            "awaiting_custom_button",
            {"group_id": group_id}
        )
        guide_text = (
            f"➕ <b>Add Custom Button</b>\n\n"
            f"Send your button definition now in this format (Premium custom emojis & styles supported!):\n\n"
            f"• <b>URL Button:</b>\n<code>btn - Button Title - https://yourlink.com</code>\n\n"
            f"• <b>Rich Styled Button:</b>\n<code>btn - Button Title - https://yourlink.com - primary</code>\n"
            f"<i>(Styles: primary, danger, success, default)</i>\n\n"
            f"• <b>Alert Popup Button:</b>\n<code>btn - Button Title - alert:Your alert text here</code>\n\n"
            f"<i>You can send multiple lines to add multiple buttons at once.</i>"
        )
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Cancel", callback_data=f"manage_buttons:{group_id}")]])
        await query.message.edit_text(guide_text, parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^clear_custom_btns:(-?\d+)"))
    async def process_clear_custom_btns(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        await database_service.update_custom_buttons(group_id, [])
        await query.answer("All custom buttons cleared!", show_alert=True)
        return await process_manage_buttons_callback(client, query)

    @application.on_callback_query(filters.regex(r"^manage_links:(-?\d+)"))
    async def process_manage_links_callback(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        group_record = await database_service.retrieve_group_by_id(group_id)
        if not group_record:
            return await query.answer("Group not found.", show_alert=True)
        links_list = group_record.get("custom_links", [])
        overview = []
        for idx, lnk in enumerate(links_list, start=1):
            overview.append(f"{idx}. <b>{lnk.get('title')}</b> → <code>{lnk.get('target')}</code>")
        links_text = "\n".join(overview) if overview else "<i>No custom links added yet (default repository link is shown).</i>"
        panel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="➕ Add Custom Link", callback_data=f"add_custom_link:{group_id}")],
            [InlineKeyboardButton(text="🗑 Clear Custom Links", callback_data=f"clear_custom_links:{group_id}")],
            [InlineKeyboardButton(text="🔙 Back to Preview", callback_data=f"back_to_preview:{group_id}")]
        ])
        msg_text = (
            f"🔗 <b>Manage Customized Links</b>\n\n"
            f"These links appear at the bottom of your monthly updates in rich-text format.\n\n"
            f"<b>Active Custom Links:</b>\n{links_text}\n\n"
            f"Tap an option below:"
        )
        await query.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=panel_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^add_custom_link:(-?\d+)"))
    async def process_add_custom_link(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        await database_service.set_user_interaction_state(
            query.from_user.id,
            "awaiting_custom_link",
            {"group_id": group_id}
        )
        guide_text = (
            f"➕ <b>Add Custom Release Link</b>\n\n"
            f"Send your link in one of the following formats (Premium custom emojis supported!):\n\n"
            f"<code>link - Documentation - https://example.com/docs</code>\n"
            f"<code>link - Support Group - @YourSupportChat</code>\n"
            f"<code>link - Changelogs - https://example.com/changelogs</code>\n\n"
            f"<i>Send one or more lines in your message.</i>"
        )
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Cancel", callback_data=f"manage_links:{group_id}")]])
        await query.message.edit_text(guide_text, parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
        await query.answer()

    @application.on_callback_query(filters.regex(r"^clear_custom_links:(-?\d+)"))
    async def process_clear_custom_links(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        await database_service.update_custom_links(group_id, [])
        await query.answer("All custom links cleared!", show_alert=True)
        return await process_manage_links_callback(client, query)

    @application.on_callback_query(filters.regex(r"^broadcast_update:(-?\d+):(.+)"))
    async def process_broadcast_update_callback(client: Client, query: CallbackQuery):
        group_id = int(query.matches[0].group(1))
        month_str = query.matches[0].group(2)
        group_record = await database_service.retrieve_group_by_id(group_id)
        if not group_record:
            return await query.answer("Group not found.", show_alert=True)
        is_dev_admin = (query.from_user.id == system_config.developer_owner_id)
        if not is_dev_admin and group_record.get("owner_id") != query.from_user.id:
            return await query.answer("Unauthorized.", show_alert=True)
        now_utc = datetime.utcnow()
        month_start = datetime(now_utc.year, now_utc.month, 1, 0, 0, 0)
        repos_list = await database_service.retrieve_connected_repositories(group_id)
        repo_name = repos_list[0].get("name") if repos_list and isinstance(repos_list[0], dict) else group_record.get("repository") or "Repository"
        commits_records = await database_service.fetch_commits_in_timespan(group_id, month_start, now_utc, repository_name=repo_name)
        is_premium = group_record.get("is_premium", True) if is_dev_admin else group_record.get("is_premium", False)
        custom_links = group_record.get("custom_links", [])
        caption_text = group_record.get("custom_template") or changelog_service.generate_release_notes_text(
            month_title=month_str,
            commits_list=commits_records,
            repository_name=repo_name,
            custom_links=custom_links,
            is_premium=is_premium
        )
        custom_buttons = group_record.get("custom_buttons", [])
        attached_markup = markup_builder.build_inline_keyboard_from_definitions(custom_buttons, enable_rich_styles=True)
        fallback_markup = markup_builder.build_fallback_inline_keyboard(custom_buttons)
        banners_list = await database_service.retrieve_banners_by_month(group_id, month_str)
        targets_list = [group_id]
        if group_record.get("channel_id"):
            targets_list.append(group_record["channel_id"])
        dispatch_count = 0
        for destination_chat_id in targets_list:
            dispatched = False
            for markup_choice in [attached_markup, fallback_markup, None]:
                if dispatched:
                    break
                try:
                    if banners_list:
                        selected_banner = banners_list[0]
                        if len(caption_text) <= 1024:
                            await client.send_photo(
                                chat_id=destination_chat_id,
                                photo=selected_banner["telegram_file_id"],
                                caption=caption_text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=markup_choice
                            )
                        else:
                            await client.send_photo(
                                chat_id=destination_chat_id,
                                photo=selected_banner["telegram_file_id"],
                                caption=f"✨ <b>{month_str} Release Updates</b>",
                                parse_mode=ParseMode.HTML
                            )
                            await client.send_message(
                                chat_id=destination_chat_id,
                                text=caption_text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=markup_choice
                            )
                    else:
                        await client.send_message(
                            chat_id=destination_chat_id,
                            text=caption_text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup_choice
                        )
                    dispatched = True
                    dispatch_count += 1
                except Exception:
                    pass
        await query.answer(f"Sent update successfully to {dispatch_count} chat(s)!", show_alert=True)
