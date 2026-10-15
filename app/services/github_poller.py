import asyncio
import httpx
import time
from datetime import datetime
from app.core.config import system_config
from app.database.database import database_service
from app.services.github_api import github_api_service
from app.utils.formatters import markdown_to_telegram_html, escape_html_text
from pyrogram import Client
from pyrogram.enums import ParseMode

class GitHubPollerService:
    def __init__(self):
        self.api_base_url = "https://api.github.com"
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if system_config.github_personal_token:
            self.headers["Authorization"] = f"token {system_config.github_personal_token}"

    async def fetch_recent_commits(self, client: httpx.AsyncClient, repository: str, token: str = None):
        request_headers = dict(self.headers)
        if token:
            request_headers["Authorization"] = f"token {token}"
        request_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        request_headers["Pragma"] = "no-cache"
        request_url = f"{self.api_base_url}/repos/{repository}/commits"
        params = {"per_page": 10, "_t": int(time.time() * 1000)}
        try:
            response = await client.get(request_url, headers=request_headers, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    async def fetch_recent_issues(self, client: httpx.AsyncClient, repository: str, token: str = None):
        request_headers = dict(self.headers)
        if token:
            request_headers["Authorization"] = f"token {token}"
        request_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        request_headers["Pragma"] = "no-cache"
        request_url = f"{self.api_base_url}/repos/{repository}/issues"
        params = {"state": "all", "per_page": 10, "_t": int(time.time() * 1000)}
        try:
            response = await client.get(request_url, headers=request_headers, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    async def check_and_dispatch_commits(self, bot_client: Client, http_client: httpx.AsyncClient, group_record: dict, repo_info: dict = None, token: str = None):
        group_id = group_record["group_id"]
        repository = group_record.get("repository")
        owner_id = group_record.get("owner_id")
        private_alerts = repo_info.get("private_alerts", False) if isinstance(repo_info, dict) else False

        targets = []
        if private_alerts:
            if owner_id:
                targets.append(owner_id)
        else:
            repo_channel_id = repo_info.get("channel_id") if isinstance(repo_info, dict) else None
            channel_id = repo_channel_id or group_record.get("channel_id")
            if channel_id:
                targets.append(channel_id)
            elif group_id:
                targets.append(group_id)

        commits_data = await self.fetch_recent_commits(http_client, repository, token=token)
        if not commits_data:
            return
        last_known_sha = repo_info.get("last_polled_sha") if isinstance(repo_info, dict) else group_record.get("last_polled_sha")
        latest_sha = commits_data[0].get("sha")
        if not last_known_sha:
            for item in commits_data:
                await database_service.record_github_commit(
                    group_id=group_id,
                    commit_identifier=item.get("sha"),
                    commit_message=item.get("commit", {}).get("message", ""),
                    author_name=item.get("commit", {}).get("author", {}).get("name", "Unknown"),
                    repository_name=repository,
                    timestamp_iso=item.get("commit", {}).get("author", {}).get("date", "")
                )
            await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_sha=latest_sha)
            return
        if latest_sha == last_known_sha:
            return
        new_commits_batch = []
        for item in commits_data:
            if item.get("sha") == last_known_sha:
                break
            new_commits_batch.append(item)
        if not new_commits_batch:
            return
        for item in reversed(new_commits_batch):
            commit_sha = item.get("sha")
            commit_msg = item.get("commit", {}).get("message", "")
            author_name = item.get("commit", {}).get("author", {}).get("name", "Unknown")
            commit_date = item.get("commit", {}).get("author", {}).get("date", "")
            commit_url = item.get("html_url", "")
            short_sha = commit_sha[:7]

            commit_lines = commit_msg.strip().splitlines()
            first_line = escape_html_text(commit_lines[0]) if commit_lines else "Commit"
            commit_body = "\n".join(commit_lines[1:]).strip() if len(commit_lines) > 1 else ""
            formatted_commit_body = markdown_to_telegram_html(commit_body) if commit_body else ""
            if formatted_commit_body:
                if "<pre>" in formatted_commit_body or "<blockquote>" in formatted_commit_body:
                    body_block = f"\n\n{formatted_commit_body}"
                else:
                    body_block = f"\n\n<blockquote>{formatted_commit_body}</blockquote>"
            else:
                body_block = ""

            await database_service.record_github_commit(
                group_id=group_id,
                commit_identifier=commit_sha,
                commit_message=commit_msg,
                author_name=author_name,
                repository_name=repository,
                timestamp_iso=commit_date
            )
            if private_alerts:
                broadcast_text = (
                    f"🔒 <b>Private Commit Alert</b> • <code>{repository}</code>\n\n"
                    f"<a href=\"{commit_url}\"><code>{short_sha}</code></a>: {first_line}\n"
                    f"By: <b>{escape_html_text(author_name)}</b>"
                    f"{body_block}\n\n"
                    f"<i>Sent privately to you via @CommitCastBot.</i>"
                )
            else:
                broadcast_text = (
                    f"🔨 <b>New Commit in {repository}</b>\n\n"
                    f"<a href=\"{commit_url}\"><code>{short_sha}</code></a>: {first_line}\n"
                    f"By: <b>{escape_html_text(author_name)}</b>"
                    f"{body_block}"
                )
            for target_chat_id in targets:
                try:
                    await bot_client.send_message(
                        chat_id=target_chat_id,
                        text=broadcast_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_sha=latest_sha)

    async def check_and_dispatch_issues(self, bot_client: Client, http_client: httpx.AsyncClient, group_record: dict, repo_info: dict = None, token: str = None):
        group_id = group_record["group_id"]
        repository = group_record.get("repository")
        owner_id = group_record.get("owner_id")
        private_alerts = repo_info.get("private_alerts", False) if isinstance(repo_info, dict) else False
        auto_delete_24h = repo_info.get("auto_delete_24h", False) if isinstance(repo_info, dict) else False

        targets = []
        if private_alerts:
            if owner_id:
                targets.append(owner_id)
        else:
            repo_channel_id = repo_info.get("channel_id") if isinstance(repo_info, dict) else None
            channel_id = repo_channel_id or group_record.get("channel_id")
            if channel_id:
                targets.append(channel_id)
            if group_id and group_id not in targets:
                targets.append(group_id)

        issues_data = await self.fetch_recent_issues(http_client, repository, token=token)
        if not issues_data:
            return
        last_known_issue_number = repo_info.get("last_issue_id") if isinstance(repo_info, dict) else None
        if last_known_issue_number is None:
            last_known_issue_number = group_record.get("last_issue_id")
        latest_issue_number = issues_data[0].get("number", 0)

        if last_known_issue_number is None:
            now_utc = datetime.utcnow()
            new_items = []
            for item in issues_data:
                created_at_str = item.get("created_at")
                if created_at_str:
                    try:
                        c_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if (now_utc - c_dt).total_seconds() < 7200:
                            new_items.append(item)
                    except Exception:
                        pass
            if not new_items:
                await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_issue_number=latest_issue_number)
                return
        else:
            if latest_issue_number <= last_known_issue_number:
                return
            new_items = [item for item in issues_data if item.get("number", 0) > last_known_issue_number]

        for item in reversed(new_items):
            is_pr = "pull_request" in item
            issue_title = item.get("title", "")
            issue_author = item.get("user", {}).get("login", "Unknown")
            issue_url = item.get("html_url", "")
            issue_num = item.get("number")
            issue_body = item.get("body", "")
            type_label = "Pull Request" if is_pr else "Issue"
            icon = "🔀" if is_pr else "🐛"
            formatted_desc = markdown_to_telegram_html(issue_body) if issue_body else ""
            if formatted_desc:
                if "<pre>" in formatted_desc or "<blockquote>" in formatted_desc:
                    desc_block = f"\n\n<b>Description:</b>\n{formatted_desc}"
                else:
                    desc_block = f"\n\n<b>Description:</b>\n<blockquote>{formatted_desc}</blockquote>"
            else:
                desc_block = ""

            if private_alerts:
                broadcast_text = (
                    f"🔒 <b>Private {type_label} Alert <a href=\"{issue_url}\">#{issue_num}</a></b> • <code>{repository}</code>\n\n"
                    f"<b>Title:</b> {escape_html_text(issue_title)}\n"
                    f"<b>By:</b> @{issue_author}"
                    f"{desc_block}\n\n"
                    f"<i>Sent privately to you via @CommitCastBot.</i>"
                )
            else:
                broadcast_text = (
                    f"{icon} <b>New {type_label} <a href=\"{issue_url}\">#{issue_num}</a> in {repository}</b>\n\n"
                    f"<b>Title:</b> {escape_html_text(issue_title)}\n"
                    f"<b>By:</b> @{issue_author}"
                    f"{desc_block}"
                )
            for target_chat_id in targets:
                try:
                    sent_msg = await bot_client.send_message(
                        chat_id=target_chat_id,
                        text=broadcast_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    if not private_alerts and target_chat_id == group_id and auto_delete_24h and sent_msg:
                        await database_service.schedule_message_deletion(
                            chat_id=group_id,
                            message_id=sent_msg.id,
                            repo_name=repository,
                            alert_type="pull_request" if is_pr else "issue",
                            delay_seconds=86400
                        )
                except Exception as ex:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to dispatch {type_label} to {target_chat_id}: {ex}")
        await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_issue_number=latest_issue_number)

    async def check_and_dispatch_releases(self, bot_client: Client, http_client: httpx.AsyncClient, group_record: dict, repo_info: dict = None, token: str = None):
        group_id = group_record["group_id"]
        repository = group_record.get("repository")
        owner_id = group_record.get("owner_id")
        private_alerts = repo_info.get("private_alerts", False) if isinstance(repo_info, dict) else False
        auto_delete_24h = repo_info.get("auto_delete_24h", False) if isinstance(repo_info, dict) else False

        targets = []
        if private_alerts:
            if owner_id:
                targets.append(owner_id)
        else:
            repo_channel_id = repo_info.get("channel_id") if isinstance(repo_info, dict) else None
            channel_id = repo_channel_id or group_record.get("channel_id")
            if channel_id:
                targets.append(channel_id)
            if group_id and group_id not in targets:
                targets.append(group_id)

        releases_data = await github_api_service.fetch_recent_releases(http_client, repository, token=token)
        if not releases_data:
            return
        last_known_release_id = repo_info.get("last_release_id") if isinstance(repo_info, dict) else None
        latest_release_id = releases_data[0].get("id")

        if last_known_release_id is None:
            await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_release_id=latest_release_id)
            return

        if latest_release_id == last_known_release_id:
            return

        new_releases = []
        for rel in releases_data:
            if rel.get("id") == last_known_release_id:
                break
            new_releases.append(rel)

        if not new_releases:
            return

        for rel in reversed(new_releases):
            tag_name = escape_html_text(rel.get("tag_name", "Release"))
            rel_name = escape_html_text(rel.get("name") or rel.get("tag_name", ""))
            rel_url = rel.get("html_url", "")
            rel_author = rel.get("author", {}).get("login", "Unknown")
            rel_body = rel.get("body", "")
            formatted_body = markdown_to_telegram_html(rel_body, max_length=1500) if rel_body else ""
            body_block = f"\n\n<b>Changelog:</b>\n{formatted_body}" if formatted_body else ""

            if private_alerts:
                broadcast_text = (
                    f"🔒 <b>Private Release Alert</b> • <code>{repository}</code>\n\n"
                    f"🚀 <b>New Release <a href=\"{rel_url}\">{tag_name}</a>: {rel_name}</b>\n"
                    f"<b>By:</b> @{rel_author}"
                    f"{body_block}\n\n"
                    f"<i>Sent privately to you via @CommitCastBot.</i>"
                )
            else:
                broadcast_text = (
                    f"🚀 <b>New Release <a href=\"{rel_url}\">{tag_name}</a> in {repository}</b>\n\n"
                    f"<b>Title:</b> {rel_name}\n"
                    f"<b>Author:</b> @{rel_author}"
                    f"{body_block}"
                )

            for target_chat_id in targets:
                try:
                    sent_msg = await bot_client.send_message(
                        chat_id=target_chat_id,
                        text=broadcast_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    if not private_alerts and target_chat_id == group_id and auto_delete_24h and sent_msg:
                        await database_service.schedule_message_deletion(
                            chat_id=group_id,
                            message_id=sent_msg.id,
                            repo_name=repository,
                            alert_type="release",
                            delay_seconds=86400
                        )
                except Exception:
                    pass
        await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_release_id=latest_release_id)

    async def check_and_dispatch_workflow_runs(self, bot_client: Client, http_client: httpx.AsyncClient, group_record: dict, repo_info: dict = None, token: str = None):
        group_id = group_record["group_id"]
        repository = group_record.get("repository")
        owner_id = group_record.get("owner_id")
        private_alerts = repo_info.get("private_alerts", False) if isinstance(repo_info, dict) else False
        auto_delete_24h = repo_info.get("auto_delete_24h", False) if isinstance(repo_info, dict) else False

        targets = []
        if private_alerts:
            if owner_id:
                targets.append(owner_id)
        else:
            repo_channel_id = repo_info.get("channel_id") if isinstance(repo_info, dict) else None
            channel_id = repo_channel_id or group_record.get("channel_id")
            if channel_id:
                targets.append(channel_id)
            if group_id and group_id not in targets:
                targets.append(group_id)

        runs_data = await github_api_service.fetch_recent_workflow_runs(http_client, repository, token=token)
        if not runs_data:
            return

        last_known_run_id = repo_info.get("last_workflow_run_id") if isinstance(repo_info, dict) else None
        latest_run_id = runs_data[0].get("id")

        if last_known_run_id is None:
            await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_workflow_run_id=latest_run_id)
            return

        if latest_run_id == last_known_run_id:
            return

        new_runs = []
        for run in runs_data:
            if run.get("id") == last_known_run_id:
                break
            if run.get("status") in ["completed", "waiting"]:
                new_runs.append(run)

        for run in reversed(new_runs):
            run_name = escape_html_text(run.get("name", "Workflow"))
            run_url = run.get("html_url", "")
            run_conclusion = run.get("conclusion")
            run_status = run.get("status")
            branch_name = escape_html_text(run.get("head_branch", "main"))
            commit_sha = run.get("head_sha", "")[:7]
            commit_msg = escape_html_text(run.get("display_title", "Run"))
            actor = run.get("actor", {}).get("login", "Unknown")

            if run_status == "waiting":
                status_icon = "🟡"
                status_text = "Approval Required"
            elif run_conclusion == "success":
                status_icon = "🟢"
                status_text = "Succeeded"
            elif run_conclusion == "failure":
                status_icon = "🔴"
                status_text = "Failed"
            elif run_conclusion == "cancelled":
                status_icon = "⚪"
                status_text = "Cancelled"
            else:
                status_icon = "⚡"
                status_text = (run_conclusion or run_status).capitalize()

            if private_alerts:
                broadcast_text = (
                    f"🔒 <b>Private CI/CD Alert</b> • <code>{repository}</code>\n\n"
                    f"{status_icon} <b>CI/CD {status_text}: <a href=\"{run_url}\">{run_name}</a></b>\n"
                    f"• <b>Branch:</b> <code>{branch_name}</code>\n"
                    f"• <b>Commit:</b> <code>{commit_sha}</code> - {commit_msg}\n"
                    f"• <b>Triggered By:</b> @{actor}\n\n"
                    f"<i>Sent privately to you via @CommitCastBot.</i>"
                )
            else:
                broadcast_text = (
                    f"{status_icon} <b>CI/CD {status_text} in {repository}</b>\n\n"
                    f"⚙️ <b>Workflow:</b> <a href=\"{run_url}\">{run_name}</a>\n"
                    f"• <b>Branch:</b> <code>{branch_name}</code>\n"
                    f"• <b>Commit:</b> <code>{commit_sha}</code> - {commit_msg}\n"
                    f"• <b>Triggered By:</b> @{actor}"
                )

            for target_chat_id in targets:
                try:
                    sent_msg = await bot_client.send_message(
                        chat_id=target_chat_id,
                        text=broadcast_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    if not private_alerts and target_chat_id == group_id and auto_delete_24h and sent_msg:
                        await database_service.schedule_message_deletion(
                            chat_id=group_id,
                            message_id=sent_msg.id,
                            repo_name=repository,
                            alert_type="workflow",
                            delay_seconds=86400
                        )
                except Exception:
                    pass

        await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_workflow_run_id=latest_run_id)

    async def check_and_dispatch_stars_and_forks(self, bot_client: Client, http_client: httpx.AsyncClient, group_record: dict, repo_info: dict = None, token: str = None):
        group_id = group_record["group_id"]
        repository = group_record.get("repository")
        owner_id = group_record.get("owner_id")
        private_alerts = repo_info.get("private_alerts", False) if isinstance(repo_info, dict) else False

        targets = []
        if private_alerts:
            if owner_id:
                targets.append(owner_id)
        else:
            repo_channel_id = repo_info.get("channel_id") if isinstance(repo_info, dict) else None
            channel_id = repo_channel_id or group_record.get("channel_id")
            if channel_id:
                targets.append(channel_id)
            if group_id and group_id not in targets:
                targets.append(group_id)

        repo_details = await github_api_service.fetch_repository_details(http_client, repository, token=token)
        if not repo_details:
            return

        current_stars = repo_details.get("stargazers_count", 0)
        current_forks = repo_details.get("forks_count", 0)

        last_known_stars = repo_info.get("last_stars_count") if isinstance(repo_info, dict) else None
        last_known_forks = repo_info.get("last_forks_count") if isinstance(repo_info, dict) else None

        if last_known_stars is None or last_known_forks is None:
            await database_service.update_repository_polling_markers(
                group_id,
                repository_name=repository,
                last_stars_count=current_stars,
                last_forks_count=current_forks
            )
            return

        if current_stars > last_known_stars:
            stargazers = await github_api_service.fetch_recent_stargazers(http_client, repository, token=token)
            stargazer_user = "Someone"
            if stargazers:
                latest_star = stargazers[-1] if isinstance(stargazers, list) else {}
                stargazer_user = latest_star.get("user", {}).get("login", "Someone")
            star_text = (
                f"⭐ <b>New Star for {repository}!</b>\n\n"
                f"👤 <b>Starred by:</b> <a href=\"https://github.com/{stargazer_user}\">@{stargazer_user}</a>\n"
                f"✨ <b>Total Stars:</b> <b>{current_stars}</b> ⭐"
            )
            for target_chat_id in targets:
                try:
                    await bot_client.send_message(chat_id=target_chat_id, text=star_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
            await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_stars_count=current_stars)

        if current_forks > last_known_forks:
            forks = await github_api_service.fetch_recent_forks(http_client, repository, token=token)
            fork_user = "Someone"
            fork_url = f"https://github.com/{repository}/network/members"
            if forks:
                latest_fork = forks[0]
                fork_user = latest_fork.get("owner", {}).get("login", "Someone")
                fork_url = latest_fork.get("html_url", fork_url)
            fork_text = (
                f"🍴 <b>New Fork of {repository}!</b>\n\n"
                f"👤 <b>Forked by:</b> <a href=\"https://github.com/{fork_user}\">@{fork_user}</a>\n"
                f"📦 <b>Repo:</b> <a href=\"{fork_url}\">{fork_url}</a>\n"
                f"✨ <b>Total Forks:</b> <b>{current_forks}</b> 🍴"
            )
            for target_chat_id in targets:
                try:
                    await bot_client.send_message(chat_id=target_chat_id, text=fork_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
            await database_service.update_repository_polling_markers(group_id, repository_name=repository, last_forks_count=current_forks)

    async def start_polling_loop(self, bot_client: Client):
        async with httpx.AsyncClient(
            timeout=8.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
        ) as http_client:
            while True:
                try:
                    await database_service.process_due_message_deletions(bot_client)
                    tracked_groups = await database_service.retrieve_all_tracked_groups()
                    commit_tasks = []
                    issue_tasks = []
                    release_tasks = []
                    workflow_tasks = []
                    star_tasks = []

                    for group_record in tracked_groups:
                        group_id = group_record["group_id"]
                        owner_id = group_record.get("owner_id")
                        user_token = await database_service.retrieve_user_github_token(owner_id) if owner_id else None
                        repos = await database_service.retrieve_connected_repositories(group_id)
                        for repo in repos:
                            repo_name = repo.get("name") if isinstance(repo, dict) else repo
                            commits_enabled = repo.get("commits_enabled", True) if isinstance(repo, dict) else True
                            issues_enabled = repo.get("issues_enabled", True) if isinstance(repo, dict) else True
                            releases_enabled = repo.get("releases_enabled", True) if isinstance(repo, dict) else True
                            workflows_enabled = repo.get("workflows_enabled", True) if isinstance(repo, dict) else True
                            stars_enabled = repo.get("stars_enabled", True) if isinstance(repo, dict) else True
                            custom_record = dict(group_record)
                            custom_record["repository"] = repo_name
                            repo_dict = repo if isinstance(repo, dict) else {}
                            if commits_enabled:
                                commit_tasks.append(
                                    self.check_and_dispatch_commits(
                                        bot_client,
                                        http_client,
                                        custom_record,
                                        repo_info=repo_dict,
                                        token=user_token
                                    )
                                )
                            if issues_enabled:
                                issue_tasks.append(
                                    self.check_and_dispatch_issues(
                                        bot_client,
                                        http_client,
                                        custom_record,
                                        repo_info=repo_dict,
                                        token=user_token
                                    )
                                )
                            if releases_enabled:
                                release_tasks.append(
                                    self.check_and_dispatch_releases(
                                        bot_client,
                                        http_client,
                                        custom_record,
                                        repo_info=repo_dict,
                                        token=user_token
                                    )
                                )
                            if workflows_enabled:
                                workflow_tasks.append(
                                    self.check_and_dispatch_workflow_runs(
                                        bot_client,
                                        http_client,
                                        custom_record,
                                        repo_info=repo_dict,
                                        token=user_token
                                    )
                                )
                            if stars_enabled:
                                star_tasks.append(
                                    self.check_and_dispatch_stars_and_forks(
                                        bot_client,
                                        http_client,
                                        custom_record,
                                        repo_info=repo_dict,
                                        token=user_token
                                    )
                                )

                    # Run all checks concurrently
                    all_tasks = commit_tasks + issue_tasks + release_tasks + workflow_tasks + star_tasks
                    if all_tasks:
                        await asyncio.gather(*all_tasks, return_exceptions=True)
                except Exception:
                    pass
                await asyncio.sleep(system_config.polling_interval_seconds)

github_poller_service = GitHubPollerService()
