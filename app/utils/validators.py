import re

def is_valid_github_repository(repo_str: str) -> bool:
    if not repo_str or "/" not in repo_str:
        return False
    parts = repo_str.strip().split("/")
    if len(parts) != 2:
        return False
    owner, repo = parts[0].strip(), parts[1].strip()
    return bool(re.match(r"^[A-Za-z0-9_.-]+$", owner) and re.match(r"^[A-Za-z0-9_.-]+$", repo))

def is_valid_github_token(token_str: str) -> bool:
    if not token_str:
        return False
    return bool(re.match(r"^gh[pousr]_[A-Za-z0-9_]+$", token_str.strip()))

def is_valid_telegram_channel_id(channel_id_str: str) -> bool:
    if not channel_id_str:
        return False
    return bool(re.match(r"^-100\d+$", channel_id_str.strip()))
