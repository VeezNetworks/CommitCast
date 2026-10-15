import httpx
from app.core.config import system_config

class GitHubApiClient:
    def __init__(self):
        self.api_base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {system_config.github_personal_token}"
        }

    async def fetch_user_repositories(self, client: httpx.AsyncClient, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/user/repos"
        response = await client.get(
            url,
            headers=auth_headers,
            params={"per_page": 100, "affiliation": "owner,collaborator,organization_member", "sort": "updated"}
        )
        if response.status_code == 200:
            return response.json()
        return []

    async def fetch_repository_commits_since(self, client: httpx.AsyncClient, repository: str, since_iso: str, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}/commits"
        response = await client.get(
            url,
            headers=auth_headers,
            params={"since": since_iso, "per_page": 100}
        )
        if response.status_code == 200:
            return response.json()
        return []

    async def fetch_open_pull_requests(self, client: httpx.AsyncClient, repository: str):
        url = f"{self.api_base_url}/repos/{repository}/pulls"
        response = await client.get(url, headers=self.headers, params={"state": "open", "per_page": 50})
        if response.status_code == 200:
            return response.json()
        return []

    async def close_single_pull_request(self, client: httpx.AsyncClient, repository: str, pr_number: int):
        url = f"{self.api_base_url}/repos/{repository}/pulls/{pr_number}"
        response = await client.patch(url, headers=self.headers, json={"state": "closed"})
        return response.status_code == 200

    async def fetch_active_issues(self, client: httpx.AsyncClient, repository: str):
        url = f"{self.api_base_url}/repos/{repository}/issues"
        response = await client.get(url, headers=self.headers, params={"state": "open", "per_page": 10})
        if response.status_code == 200:
            raw_items = response.json()
            return [issue for issue in raw_items if "pull_request" not in issue]
        return []

    async def post_commit_comment(self, client: httpx.AsyncClient, repository: str, sha: str, body: str, token: str):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}"
        }
        url = f"{self.api_base_url}/repos/{repository}/commits/{sha}/comments"
        response = await client.post(url, headers=headers, json={"body": body})
        if response.status_code == 201:
            return True, response.json()
        try:
            err_json = response.json()
            msg = err_json.get("message", response.text)
        except Exception:
            msg = response.text
        return False, msg

    async def post_issue_or_pr_comment(self, client: httpx.AsyncClient, repository: str, item_number: int, body: str, token: str):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}"
        }
        url = f"{self.api_base_url}/repos/{repository}/issues/{item_number}/comments"
        response = await client.post(url, headers=headers, json={"body": body})
        if response.status_code == 201:
            return True, response.json()
        try:
            err_json = response.json()
            msg = err_json.get("message", response.text)
        except Exception:
            msg = response.text
        return False, msg

    async def fetch_recent_releases(self, client: httpx.AsyncClient, repository: str, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}/releases"
        try:
            response = await client.get(url, headers=auth_headers, params={"per_page": 5})
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    async def fetch_recent_workflow_runs(self, client: httpx.AsyncClient, repository: str, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}/actions/runs"
        try:
            response = await client.get(url, headers=auth_headers, params={"per_page": 10})
            if response.status_code == 200:
                data = response.json()
                return data.get("workflow_runs", [])
        except Exception:
            pass
        return []

    async def fetch_repository_details(self, client: httpx.AsyncClient, repository: str, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}"
        try:
            response = await client.get(url, headers=auth_headers)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

    async def fetch_recent_stargazers(self, client: httpx.AsyncClient, repository: str, token: str = None):
        auth_headers = dict(self.headers)
        auth_headers["Accept"] = "application/vnd.github.v3.star+json"
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}/stargazers"
        try:
            response = await client.get(url, headers=auth_headers, params={"per_page": 10})
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    async def fetch_recent_forks(self, client: httpx.AsyncClient, repository: str, token: str = None):
        auth_headers = dict(self.headers)
        if token:
            auth_headers["Authorization"] = f"token {token}"
        url = f"{self.api_base_url}/repos/{repository}/forks"
        try:
            response = await client.get(url, headers=auth_headers, params={"sort": "newest", "per_page": 5})
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    async def close_issue_or_pr(self, client: httpx.AsyncClient, repository: str, item_number: int, token: str):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}"
        }
        url = f"{self.api_base_url}/repos/{repository}/issues/{item_number}"
        try:
            response = await client.patch(url, headers=headers, json={"state": "closed"})
            if response.status_code == 200:
                return True, response.json()
            try:
                err_json = response.json()
                msg = err_json.get("message", response.text)
            except Exception:
                msg = response.text
            return False, msg
        except Exception as e:
            return False, str(e)

    async def reopen_issue_or_pr(self, client: httpx.AsyncClient, repository: str, item_number: int, token: str):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}"
        }
        url = f"{self.api_base_url}/repos/{repository}/issues/{item_number}"
        try:
            response = await client.patch(url, headers=headers, json={"state": "open"})
            if response.status_code == 200:
                return True, response.json()
            try:
                err_json = response.json()
                msg = err_json.get("message", response.text)
            except Exception:
                msg = response.text
            return False, msg
        except Exception as e:
            return False, str(e)

    async def add_issue_labels(self, client: httpx.AsyncClient, repository: str, item_number: int, labels: list[str], token: str):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}"
        }
        url = f"{self.api_base_url}/repos/{repository}/issues/{item_number}/labels"
        try:
            response = await client.post(url, headers=headers, json={"labels": labels})
            if response.status_code in [200, 201]:
                return True, response.json()
            try:
                err_json = response.json()
                msg = err_json.get("message", response.text)
            except Exception:
                msg = response.text
            return False, msg
        except Exception as e:
            return False, str(e)

github_api_service = GitHubApiClient()
