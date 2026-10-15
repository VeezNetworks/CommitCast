from typing import Optional, List, Dict, Any
from app.database.database import database_service

class RepositoryDataManager:
    @staticmethod
    async def get_repositories_for_group(group_id: int) -> List[Dict[str, Any]]:
        return await database_service.retrieve_connected_repositories(group_id)

    @staticmethod
    async def link_repository(group_id: int, repository_full_name: str) -> bool:
        return await database_service.link_github_repository(group_id, repository_full_name)

    @staticmethod
    async def remove_repository(group_id: int, repository_full_name: str) -> bool:
        return await database_service.delete_connected_repository(group_id, repository_full_name)

    @staticmethod
    async def toggle_setting(group_id: int, repository_full_name: str, setting_key: str) -> bool:
        return await database_service.toggle_repository_setting(group_id, repository_full_name, setting_key)

    @staticmethod
    async def set_log_channel(group_id: int, repository_full_name: str, channel_id: int):
        await database_service.set_repository_destination_channel(group_id, repository_full_name, channel_id)

repository_data_manager = RepositoryDataManager()
