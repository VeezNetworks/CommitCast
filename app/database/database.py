from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import system_config

class DatabaseManager:
    def __init__(self):
        self.mongo_client = AsyncIOMotorClient(system_config.mongodb_connection_uri)
        self.database = self.mongo_client[system_config.database_name]
        self.groups_collection = self.database["connected_groups"]
        self.banners_collection = self.database["monthly_banners"]
        self.commits_collection = self.database["github_commits"]
        self.user_states_collection = self.database["user_interaction_states"]
        self.user_accounts_collection = self.database["user_github_accounts"]
        self.scheduled_deletions = self.database["scheduled_deletions"]

    async def initialize_indexes(self):
        await self.groups_collection.create_index("group_id", unique=True)
        await self.groups_collection.create_index("owner_id")
        await self.banners_collection.create_index([("group_id", 1), ("month_identifier", 1)])
        await self.commits_collection.create_index([("group_id", 1), ("commit_identifier", 1)], unique=True)
        await self.commits_collection.create_index("committed_timestamp")
        await self.user_states_collection.create_index("user_id", unique=True)
        await self.user_accounts_collection.create_index("user_id", unique=True)
        await self.scheduled_deletions.create_index("delete_at")
        if system_config.developer_owner_id and system_config.github_personal_token:
            dev_doc = await self.user_accounts_collection.find_one({"user_id": system_config.developer_owner_id})
            if not dev_doc:
                await self.store_user_github_token(
                    system_config.developer_owner_id,
                    system_config.github_personal_token,
                    "Veez-Mega"
                )

    async def connect_group_for_owner(self, group_id: int, owner_id: int, group_title: str):
        account = await self.user_accounts_collection.find_one({"user_id": owner_id})
        default_channel = account.get("log_channel_id") or account.get("channel_id") if account else None
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {
                "$set": {
                    "owner_id": owner_id,
                    "group_title": group_title,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "channel_id": default_channel,
                    "is_premium": False,
                    "custom_buttons": [],
                    "custom_template": "",
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )

    async def set_connected_channel(self, group_id: int, channel_id: int, owner_id: int = None):
        group = await self.retrieve_group_by_id(group_id)
        if group and not owner_id:
            owner_id = group.get("owner_id")
        repos = group.get("repositories", []) if group else []
        for r in repos:
            if isinstance(r, dict):
                r["channel_id"] = channel_id
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"channel_id": channel_id, "repositories": repos, "updated_at": datetime.utcnow()}}
        )
        if owner_id:
            await self.user_accounts_collection.update_one(
                {"user_id": owner_id},
                {"$set": {"log_channel_id": channel_id, "channel_id": channel_id}}
            )

    async def disconnect_connected_channel(self, group_id: int, owner_id: int = None):
        group = await self.retrieve_group_by_id(group_id)
        if group and not owner_id:
            owner_id = group.get("owner_id")
        repos = group.get("repositories", []) if group else []
        for r in repos:
            if isinstance(r, dict):
                r["channel_id"] = None
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"channel_id": None, "repositories": repos, "updated_at": datetime.utcnow()}}
        )
        if owner_id:
            await self.user_accounts_collection.update_one(
                {"user_id": owner_id},
                {"$set": {"log_channel_id": None, "channel_id": None}}
            )
        return True

    async def disconnect_group(self, group_id: int, owner_id: int = None):
        query = {"group_id": group_id}
        if owner_id:
            query["owner_id"] = owner_id
        result = await self.groups_collection.delete_one(query)
        return result.deleted_count > 0

    async def link_github_repository(self, group_id: int, repository_full_name: str):
        existing_repos = await self.retrieve_connected_repositories(group_id)
        for r in existing_repos:
            r_name = r.get("name") if isinstance(r, dict) else r
            if r_name.lower() == repository_full_name.lower():
                return False
        group = await self.retrieve_group_by_id(group_id)
        default_channel_id = group.get("channel_id") if group else None
        if not default_channel_id and group and group.get("owner_id"):
            account = await self.user_accounts_collection.find_one({"user_id": group["owner_id"]})
            if account:
                default_channel_id = account.get("log_channel_id") or account.get("channel_id")
                if default_channel_id:
                    await self.groups_collection.update_one(
                        {"group_id": group_id},
                        {"$set": {"channel_id": default_channel_id}}
                    )

        repo_data = {
            "name": repository_full_name,
            "commits_enabled": True,
            "issues_enabled": True,
            "releases_enabled": True,
            "workflows_enabled": True,
            "stars_enabled": True,
            "private_alerts": False,
            "auto_delete_24h": False,
            "channel_id": default_channel_id,
            "last_polled_sha": None,
            "last_issue_id": None,
            "last_release_id": None,
            "last_workflow_run_id": None,
            "last_stars_count": None,
            "last_forks_count": None
        }
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {
                "$push": {"repositories": repo_data},
                "$set": {"repository": repository_full_name, "updated_at": datetime.utcnow()}
            }
        )
        return True

    async def retrieve_connected_repositories(self, group_id: int):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return []
        group_channel = group.get("channel_id")
        repos = group.get("repositories", [])
        if not repos and group.get("repository"):
            repos = [{
                "name": group["repository"],
                "commits_enabled": True,
                "issues_enabled": True,
                "releases_enabled": True,
                "workflows_enabled": True,
                "stars_enabled": True,
                "private_alerts": False,
                "auto_delete_24h": False,
                "channel_id": group_channel,
                "last_polled_sha": group.get("last_polled_sha"),
                "last_issue_id": group.get("last_issue_id"),
                "last_release_id": group.get("last_release_id"),
                "last_workflow_run_id": group.get("last_workflow_run_id"),
                "last_stars_count": group.get("last_stars_count"),
                "last_forks_count": group.get("last_forks_count")
            }]
        for r in repos:
            if isinstance(r, dict):
                if not r.get("channel_id") and group_channel:
                    r["channel_id"] = group_channel
                if "releases_enabled" not in r:
                    r["releases_enabled"] = True
                if "workflows_enabled" not in r:
                    r["workflows_enabled"] = True
                if "stars_enabled" not in r:
                    r["stars_enabled"] = True
        return repos

    async def toggle_repository_setting(self, group_id: int, repository_name: str, setting_key: str):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return False
        repos = group.get("repositories", [])
        if not repos and group.get("repository") == repository_name:
            repos = [{
                "name": repository_name,
                "commits_enabled": True,
                "issues_enabled": True,
                "private_alerts": False,
                "auto_delete_24h": False
            }]
        updated_state = False
        for repo in repos:
            if repo.get("name") == repository_name:
                default_val = False if setting_key in ["private_alerts", "auto_delete_24h"] else True
                repo[setting_key] = not repo.get(setting_key, default_val)
                updated_state = repo[setting_key]
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"repositories": repos, "updated_at": datetime.utcnow()}}
        )
        return updated_state

    async def toggle_all_repositories_setting(self, group_id: int, setting_key: str):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return False
        repos = group.get("repositories", [])
        if not repos and group.get("repository"):
            repos = [{
                "name": group["repository"],
                "commits_enabled": True,
                "issues_enabled": True,
                "private_alerts": False,
                "auto_delete_24h": False
            }]
        current_state = any(r.get(setting_key, False) for r in repos)
        new_state = not current_state
        for repo in repos:
            repo[setting_key] = new_state
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"repositories": repos, "updated_at": datetime.utcnow()}}
        )
        return new_state

    async def delete_connected_repository(self, group_id: int, repository_name: str):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return False
        repos = group.get("repositories", [])
        updated_repos = [r for r in repos if (r.get("name") if isinstance(r, dict) else r) != repository_name]
        update_fields = {"repositories": updated_repos, "updated_at": datetime.utcnow()}
        if group.get("repository") == repository_name:
            update_fields["repository"] = updated_repos[0]["name"] if updated_repos else None
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": update_fields}
        )
        return True

    async def set_repository_destination_channel(self, group_id: int, repository_name: str, channel_id: int):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return
        repos = group.get("repositories", [])
        for repo in repos:
            if repo.get("name") == repository_name:
                repo["channel_id"] = channel_id
        owner_id = group.get("owner_id")
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"repositories": repos, "channel_id": channel_id, "updated_at": datetime.utcnow()}}
        )
        if owner_id:
            await self.user_accounts_collection.update_one(
                {"user_id": owner_id},
                {"$set": {"log_channel_id": channel_id, "channel_id": channel_id}}
            )

    async def store_user_github_token(self, user_id: int, github_token: str, github_username: str):
        await self.user_accounts_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "github_token": github_token,
                    "github_username": github_username,
                    "authenticated_at": datetime.utcnow()
                }
            },
            upsert=True
        )

    async def retrieve_user_github_token(self, user_id: int):
        doc = await self.user_accounts_collection.find_one({"user_id": user_id})
        if doc and doc.get("github_token"):
            return doc.get("github_token")
        if user_id == system_config.developer_owner_id and system_config.github_personal_token:
            return system_config.github_personal_token
        return None

    async def retrieve_user_github_account_info(self, user_id: int):
        doc = await self.user_accounts_collection.find_one({"user_id": user_id})
        if doc and doc.get("github_username"):
            return {
                "username": doc.get("github_username"),
                "token": doc.get("github_token"),
                "authenticated_at": doc.get("authenticated_at")
            }
        if user_id == system_config.developer_owner_id and system_config.github_personal_token:
            return {
                "username": "Veez-Mega",
                "token": system_config.github_personal_token,
                "authenticated_at": datetime.utcnow()
            }
        return None

    async def unlink_user_github_account(self, user_id: int):
        await self.user_accounts_collection.delete_one({"user_id": user_id})

    async def retrieve_all_tracked_groups(self):
        cursor = self.groups_collection.find({
            "$or": [
                {"repositories": {"$exists": True, "$ne": []}},
                {"repository": {"$ne": None}}
            ]
        })
        return await cursor.to_list(length=1000)

    async def update_repository_polling_markers(
        self,
        group_id: int,
        repository_name: str = None,
        last_sha: str = None,
        last_issue_number: int = None,
        last_release_id: int = None,
        last_workflow_run_id: int = None,
        last_stars_count: int = None,
        last_forks_count: int = None
    ):
        group = await self.retrieve_group_by_id(group_id)
        if not group:
            return
        repos = group.get("repositories", [])
        if repository_name and repos:
            for repo in repos:
                if repo.get("name") == repository_name:
                    if last_sha is not None:
                        repo["last_polled_sha"] = last_sha
                    if last_issue_number is not None:
                        repo["last_issue_id"] = last_issue_number
                    if last_release_id is not None:
                        repo["last_release_id"] = last_release_id
                    if last_workflow_run_id is not None:
                        repo["last_workflow_run_id"] = last_workflow_run_id
                    if last_stars_count is not None:
                        repo["last_stars_count"] = last_stars_count
                    if last_forks_count is not None:
                        repo["last_forks_count"] = last_forks_count
            await self.groups_collection.update_one(
                {"group_id": group_id},
                {"$set": {"repositories": repos, "updated_at": datetime.utcnow()}}
            )
        else:
            fields_to_update = {"updated_at": datetime.utcnow()}
            if last_sha is not None:
                fields_to_update["last_polled_sha"] = last_sha
            if last_issue_number is not None:
                fields_to_update["last_issue_id"] = last_issue_number
            if last_release_id is not None:
                fields_to_update["last_release_id"] = last_release_id
            if last_workflow_run_id is not None:
                fields_to_update["last_workflow_run_id"] = last_workflow_run_id
            if last_stars_count is not None:
                fields_to_update["last_stars_count"] = last_stars_count
            if last_forks_count is not None:
                fields_to_update["last_forks_count"] = last_forks_count
            await self.groups_collection.update_one(
                {"group_id": group_id},
                {"$set": fields_to_update}
            )

    async def retrieve_connected_group_by_owner(self, owner_id: int):
        return await self.groups_collection.find_one({"owner_id": owner_id})

    async def retrieve_group_by_id(self, group_id: int):
        return await self.groups_collection.find_one({"group_id": group_id})

    async def store_monthly_banner(self, group_id: int, month_identifier: str, telegram_file_id: str):
        record = {
            "group_id": group_id,
            "month_identifier": month_identifier.strip().capitalize(),
            "telegram_file_id": telegram_file_id,
            "uploaded_at": datetime.utcnow()
        }
        result = await self.banners_collection.insert_one(record)
        return str(result.inserted_id)

    async def retrieve_distinct_banner_months(self, group_id: int):
        return await self.banners_collection.distinct("month_identifier", {"group_id": group_id})

    async def retrieve_banners_by_month(self, group_id: int, month_identifier: str):
        cursor = self.banners_collection.find({
            "group_id": group_id,
            "month_identifier": month_identifier.strip().capitalize()
        })
        return await cursor.to_list(length=100)

    async def delete_banner_by_id(self, banner_object_id):
        from bson import ObjectId
        await self.banners_collection.delete_one({"_id": ObjectId(banner_object_id)})

    async def record_github_commit(self, group_id: int, commit_identifier: str, commit_message: str, author_name: str, repository_name: str, timestamp_iso: str):
        try:
            parsed_datetime = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        except Exception:
            parsed_datetime = datetime.utcnow()
        await self.commits_collection.update_one(
            {"group_id": group_id, "commit_identifier": commit_identifier},
            {
                "$set": {
                    "commit_message": commit_message,
                    "author_name": author_name,
                    "repository_name": repository_name,
                    "committed_timestamp": parsed_datetime
                }
            },
            upsert=True
        )

    async def fetch_commits_in_timespan(self, group_id: int, start_date: datetime, end_date: datetime, repository_name: str = None):
        search_query = {
            "group_id": group_id,
            "committed_timestamp": {"$gte": start_date, "$lte": end_date}
        }
        if repository_name:
            search_query["repository_name"] = repository_name
        cursor = self.commits_collection.find(search_query).sort("committed_timestamp", 1)
        return await cursor.to_list(length=1000)

    async def update_custom_buttons(self, group_id: int, button_configurations: list):
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"custom_buttons": button_configurations}}
        )

    async def update_custom_links(self, group_id: int, links_configurations: list):
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"custom_links": links_configurations}}
        )

    async def update_custom_template(self, group_id: int, message_template: str):
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"custom_template": message_template}}
        )

    async def reset_custom_template(self, group_id: int):
        await self.groups_collection.update_one(
            {"group_id": group_id},
            {"$set": {"custom_template": ""}}
        )

    async def set_user_interaction_state(self, user_id: int, interaction_state: str, metadata: dict = None):
        payload = {
            "user_id": user_id,
            "state": interaction_state,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow()
        }
        await self.user_states_collection.update_one({"user_id": user_id}, {"$set": payload}, upsert=True)

    async def retrieve_user_interaction_state(self, user_id: int):
        return await self.user_states_collection.find_one({"user_id": user_id})

    async def reset_user_interaction_state(self, user_id: int):
        await self.user_states_collection.delete_one({"user_id": user_id})

    async def schedule_message_deletion(self, chat_id: int, message_id: int, repo_name: str = "", alert_type: str = "alert", delay_seconds: int = 86400):
        from datetime import timedelta
        delete_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        await self.scheduled_deletions.insert_one({
            "chat_id": chat_id,
            "message_id": message_id,
            "repo_name": repo_name,
            "alert_type": alert_type,
            "created_at": datetime.utcnow(),
            "delete_at": delete_at
        })

    async def process_due_message_deletions(self, bot_client):
        now = datetime.utcnow()
        cursor = self.scheduled_deletions.find({"delete_at": {"$lte": now}})
        due_items = await cursor.to_list(length=100)
        for item in due_items:
            try:
                await bot_client.delete_messages(
                    chat_id=item["chat_id"],
                    message_ids=item["message_id"]
                )
            except Exception:
                pass
            await self.scheduled_deletions.delete_one({"_id": item["_id"]})

database_service = DatabaseManager()
