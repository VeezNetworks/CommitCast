import hmac
import hashlib
from fastapi import FastAPI, Request, Header, HTTPException
from app.database.database import database_service
from app.core.config import system_config
from app.utils.formatters import markdown_to_telegram_html, escape_html_text
from pyrogram import Client
from pyrogram.types import LinkPreviewOptions
from pyrogram.enums import ParseMode

fastapi_application = FastAPI(title="GitHub Telegram Webhook Listener")
telegram_client_instance: Client = None

def attach_telegram_client_instance(client: Client):
    global telegram_client_instance
    telegram_client_instance = client

def verify_github_signature(request_payload: bytes, signature_header: str):
    webhook_secret = getattr(system_config, "github_webhook_secret", None)
    if not webhook_secret:
        return True
    if not signature_header:
        raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")
    expected_hmac = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=request_payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    calculated_signature = f"sha256={expected_hmac}"
    if not hmac.compare_digest(calculated_signature, signature_header):
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")
    return True

def find_repo_config(group_record: dict, repo_name: str) -> dict:
    repos = group_record.get("repositories", [])
    for r in repos:
        name = r.get("name") if isinstance(r, dict) else r
        if name and name.lower() == repo_name.lower():
            return r if isinstance(r, dict) else {"name": name}
    return {}

def resolve_dispatch_targets(group_record: dict, repo_cfg: dict, for_commits_only: bool = False) -> list[int]:
    group_id = group_record["group_id"]
    owner_id = group_record.get("owner_id")
    private_alerts = repo_cfg.get("private_alerts", False)
    if private_alerts and owner_id:
        return [owner_id]

    repo_channel = repo_cfg.get("channel_id")
    channel_id = repo_channel or group_record.get("channel_id")

    if for_commits_only:
        return [channel_id] if channel_id else [group_id]

    targets = []
    if channel_id:
        targets.append(channel_id)
    if group_id not in targets:
        targets.append(group_id)
    return targets

@fastapi_application.post("/webhook/github/{group_id}")
async def handle_github_webhook_event(
    group_id: int,
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None)
):
    request_body_bytes = await request.body()
    verify_github_signature(request_body_bytes, x_hub_signature_256)
    json_payload = await request.json()
    group_record = await database_service.retrieve_group_by_id(group_id)
    if not group_record:
        raise HTTPException(status_code=404, detail="Target group not found in database")

    repository_name = json_payload.get("repository", {}).get("full_name", "")
    repo_cfg = find_repo_config(group_record, repository_name)
    auto_delete_24h = repo_cfg.get("auto_delete_24h", False)

    if x_github_event == "push":
        if not repo_cfg.get("commits_enabled", True):
            return {"status": "skipped_disabled"}
        ref_branch = json_payload.get("ref", "").replace("refs/heads/", "")
        commits_array = json_payload.get("commits", [])
        for commit in commits_array:
            commit_id = commit.get("id", "")
            commit_msg = commit.get("message", "")
            commit_author = commit.get("author", {}).get("name", "Unknown")
            commit_timestamp = commit.get("timestamp", "")
            await database_service.record_github_commit(
                group_id=group_id,
                commit_identifier=commit_id,
                commit_message=commit_msg,
                author_name=commit_author,
                repository_name=repository_name,
                timestamp_iso=commit_timestamp
            )
        if commits_array and telegram_client_instance:
            commit_count = len(commits_array)
            head_commit = commits_array[-1]
            short_sha = head_commit.get("id", "")[:7]
            head_msg = head_commit.get("message", "").splitlines()[0]
            compare_url = json_payload.get("compare", "")
            broadcast_text = (
                f"🔨 <b>New Push to {repository_name}</b> (<code>{ref_branch}</code>)\n"
                f"Commits: <b>{commit_count}</b>\n"
                f"Latest: <a href=\"{compare_url}\"><code>{short_sha}</code></a> - {escape_html_text(head_msg)}"
            )
            targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=True)
            for t_id in targets:
                try:
                    await telegram_client_instance.send_message(
                        chat_id=t_id,
                        text=broadcast_text,
                        parse_mode=ParseMode.HTML,
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                except Exception:
                    pass

    elif x_github_event == "issues" and telegram_client_instance:
        if not repo_cfg.get("issues_enabled", True):
            return {"status": "skipped_disabled"}
        action_type = json_payload.get("action", "")
        issue_data = json_payload.get("issue", {})
        issue_title = issue_data.get("title", "")
        issue_url = issue_data.get("html_url", "")
        issue_author = issue_data.get("user", {}).get("login", "")
        issue_num = issue_data.get("number", "")
        issue_body = issue_data.get("body", "")
        formatted_desc = markdown_to_telegram_html(issue_body) if issue_body else ""
        if formatted_desc:
            if "<pre>" in formatted_desc or "<blockquote>" in formatted_desc:
                desc_block = f"\n\n<b>Description:</b>\n{formatted_desc}"
            else:
                desc_block = f"\n\n<b>Description:</b>\n<blockquote>{formatted_desc}</blockquote>"
        else:
            desc_block = ""
        broadcast_text = (
            f"🐛 <b>Issue {action_type.capitalize()} <a href=\"{issue_url}\">#{issue_num}</a> in {repository_name}</b>\n\n"
            f"<b>Title:</b> {escape_html_text(issue_title)}\n"
            f"<b>By:</b> @{issue_author}"
            f"{desc_block}"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                sent = await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
                if auto_delete_24h and t_id == group_id:
                    await database_service.schedule_message_deletion(t_id, sent.id, 86400)
            except Exception:
                pass

    elif x_github_event == "pull_request" and telegram_client_instance:
        if not repo_cfg.get("issues_enabled", True):
            return {"status": "skipped_disabled"}
        action_type = json_payload.get("action", "")
        if action_type not in ["opened", "closed", "reopened"]:
            return {"status": "ignored_pr_action"}
        pr_data = json_payload.get("pull_request", {})
        pr_title = pr_data.get("title", "")
        pr_url = pr_data.get("html_url", "")
        pr_author = pr_data.get("user", {}).get("login", "")
        pr_num = pr_data.get("number", "")
        is_merged = pr_data.get("merged", False)
        display_action = "Merged" if (action_type == "closed" and is_merged) else action_type.capitalize()
        icon = "🟣" if is_merged else ("🟢" if action_type == "opened" else "🔴")

        broadcast_text = (
            f"{icon} <b>Pull Request {display_action} <a href=\"{pr_url}\">#{pr_num}</a> in {repository_name}</b>\n\n"
            f"<b>Title:</b> {escape_html_text(pr_title)}\n"
            f"<b>By:</b> @{pr_author}"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                sent = await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
                if auto_delete_24h and t_id == group_id:
                    await database_service.schedule_message_deletion(t_id, sent.id, 86400)
            except Exception:
                pass

    elif x_github_event == "workflow_run" and telegram_client_instance:
        if not repo_cfg.get("workflows_enabled", True):
            return {"status": "skipped_disabled"}
        run_data = json_payload.get("workflow_run", {})
        conclusion = (run_data.get("conclusion") or "").lower()
        status = (run_data.get("status") or "").lower()
        action = (json_payload.get("action") or "").lower()

        if conclusion == "success":
            icon = "🟢"
            state_title = "Workflow Succeeded"
        elif conclusion in ["failure", "timed_out"]:
            icon = "🔴"
            state_title = "Workflow Failed"
        elif action == "action_required" or conclusion == "action_required" or status == "waiting":
            icon = "🟡"
            state_title = "Workflow Approval Required"
        else:
            return {"status": "ignored_workflow_state"}

        run_name = run_data.get("name", "CI/CD")
        head_branch = run_data.get("head_branch", "main")
        head_sha = (run_data.get("head_sha") or "")[:7]
        run_url = run_data.get("html_url", "")
        actor_login = run_data.get("actor", {}).get("login", "GitHub")
        commit_msg = (run_data.get("head_commit", {}).get("message", "") or "").splitlines()
        first_line = escape_html_text(commit_msg[0]) if commit_msg else ""
        commit_url = f"https://github.com/{repository_name}/commit/{run_data.get('head_sha', '')}"

        broadcast_text = (
            f"{icon} <b>{state_title} in {repository_name}</b> (<code>{head_branch}</code>)\n\n"
            f"⚙️ <b>Workflow:</b> {escape_html_text(run_name)}\n"
            f"🔨 <b>Commit:</b> <a href=\"{commit_url}\"><code>{head_sha}</code></a> - {first_line}\n"
            f"👤 <b>Triggered by:</b> @{actor_login}\n"
            f"🔗 <a href=\"{run_url}\">View Workflow Run</a>"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception:
                pass

    elif x_github_event == "release" and telegram_client_instance:
        if not repo_cfg.get("releases_enabled", True):
            return {"status": "skipped_disabled"}
        action = json_payload.get("action", "")
        release_data = json_payload.get("release", {})
        if action not in ["published", "released", "created"] or release_data.get("draft"):
            return {"status": "ignored_draft_release"}

        tag_name = release_data.get("tag_name", "")
        release_name = release_data.get("name") or tag_name
        release_url = release_data.get("html_url", "")
        author_login = release_data.get("author", {}).get("login", "GitHub")
        raw_body = release_data.get("body", "")
        formatted_body = markdown_to_telegram_html(raw_body) if raw_body else ""
        notes_block = f"\n\n📝 <b>Release Notes:</b>\n{formatted_body}" if formatted_body else ""

        broadcast_text = (
            f"🎉 <b>New Release in {repository_name}</b>: <b>{escape_html_text(release_name)}</b> (<code>{tag_name}</code>)\n\n"
            f"👤 <b>Published by:</b> @{author_login}\n"
            f"🔗 <a href=\"{release_url}\">View Release on GitHub</a>"
            f"{notes_block}"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception:
                pass

    elif x_github_event in ["star", "watch"] and telegram_client_instance:
        if not repo_cfg.get("stars_enabled", True):
            return {"status": "skipped_disabled"}
        action = json_payload.get("action", "")
        if action not in ["created", "started"]:
            return {"status": "ignored_star_action"}

        sender = json_payload.get("sender", {})
        sender_login = sender.get("login", "Someone")
        sender_url = sender.get("html_url", f"https://github.com/{sender_login}")
        repo_info = json_payload.get("repository", {})
        stars_count = repo_info.get("stargazers_count", 0)

        broadcast_text = (
            f"⭐ <b>New Star on {repository_name}!</b>\n\n"
            f"👤 <b>Starred by:</b> <a href=\"{sender_url}\">@{sender_login}</a>\n"
            f"🌟 <b>Total Stars:</b> <b>{stars_count}</b> ⭐"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception:
                pass

    elif x_github_event == "fork" and telegram_client_instance:
        if not repo_cfg.get("stars_enabled", True):
            return {"status": "skipped_disabled"}
        forkee = json_payload.get("forkee", {})
        fork_owner = forkee.get("owner", {}).get("login", "Someone")
        fork_url = forkee.get("html_url", "")
        fork_full_name = forkee.get("full_name", fork_url)
        repo_info = json_payload.get("repository", {})
        forks_count = repo_info.get("forks_count", 0)

        broadcast_text = (
            f"🍴 <b>New Fork of {repository_name}!</b>\n\n"
            f"👤 <b>Forked by:</b> <a href=\"https://github.com/{fork_owner}\">@{fork_owner}</a>\n"
            f"📦 <b>Repo:</b> <a href=\"{fork_url}\">{fork_full_name}</a>\n"
            f"✨ <b>Total Forks:</b> <b>{forks_count}</b> 🍴"
        )
        targets = resolve_dispatch_targets(group_record, repo_cfg, for_commits_only=False)
        for t_id in targets:
            try:
                await telegram_client_instance.send_message(
                    chat_id=t_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception:
                pass

    return {"status": "event_processed", "event": x_github_event}
