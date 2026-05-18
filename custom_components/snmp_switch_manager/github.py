"""GitHub API helper for Device Flow and PR generation."""
import asyncio
import logging
from typing import Any, Dict, Optional
import aiohttp
import base64
import json
import time

_LOGGER = logging.getLogger(__name__)

# Placeholder Client ID - User will need to provide their own or we use a default one for the app.
# For now, we use a placeholder.
GITHUB_CLIENT_ID = "YOUR_CLIENT_ID_HERE"

async def request_device_code(client_id: str) -> Optional[Dict[str, Any]]:
    """Request a device code from GitHub."""
    url = "https://github.com/login/device/code"
    headers = {"Accept": "application/json"}
    payload = {"client_id": client_id, "scope": "public_repo"}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, data=payload) as response:
                if response.status == 200:
                    return await response.json()
                _LOGGER.error("Failed to request device code: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error requesting device code: %s", e)
    return None

async def poll_for_token(client_id: str, device_code: str, interval: int = 5) -> Optional[str]:
    """Poll GitHub for the access token."""
    url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    payload = {
        "client_id": client_id,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.post(url, headers=headers, data=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "access_token" in data:
                            return data["access_token"]
                        if "error" in data:
                            err = data["error"]
                            if err == "authorization_pending":
                                pass
                            elif err == "slow_down":
                                interval += 5
                            elif err == "expired_token":
                                _LOGGER.error("Device code expired.")
                                return None
                            else:
                                _LOGGER.error("GitHub error: %s", err)
                                return None
                    else:
                        _LOGGER.error("Failed to poll for token: %s", response.status)
                        return None
            except Exception as e:
                _LOGGER.error("Error polling for token: %s", e)
                return None
                
            await asyncio.sleep(interval)

async def get_user(token: str) -> Optional[Dict[str, Any]]:
    """Get authenticated user info."""
    url = "https://api.github.com/user"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                _LOGGER.error("Failed to get user: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error getting user: %s", e)
    return None

async def fork_repo(token: str, repo: str) -> Optional[Dict[str, Any]]:
    """Fork a repository."""
    url = f"https://api.github.com/repos/{repo}/forks"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers) as response:
                if response.status in (200, 202):
                    return await response.json()
                _LOGGER.error("Failed to fork repo: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error forking repo: %s", e)
    return None

async def get_ref(token: str, repo: str, branch: str) -> Optional[Dict[str, Any]]:
    """Get reference SHA."""
    url = f"https://api.github.com/repos/{repo}/git/ref/heads/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                _LOGGER.error("Failed to get ref: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error getting ref: %s", e)
    return None

async def create_ref(token: str, repo: str, branch: str, sha: str) -> bool:
    """Create a new reference (branch)."""
    url = f"https://api.github.com/repos/{repo}/git/refs"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "ref": f"refs/heads/{branch}",
        "sha": sha,
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 201:
                    return True
                _LOGGER.error("Failed to create ref: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error creating ref: %s", e)
    return False

async def get_file(token: str, repo: str, path: str, ref: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get file content."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    if ref:
        url += f"?ref={ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                _LOGGER.error("Failed to get file: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error getting file: %s", e)
    return None

async def update_file(token: str, repo: str, path: str, branch: str, sha: str, content_base64: str) -> bool:
    """Update a file."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "message": f"Update {path}",
        "content": content_base64,
        "sha": sha,
        "branch": branch,
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True
                _LOGGER.error("Failed to update file: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error updating file: %s", e)
    return False

async def create_pull_request(token: str, repo: str, base: str, head: str, title: str, body: str) -> bool:
    """Create a pull request."""
    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 201:
                    return True
                _LOGGER.error("Failed to create PR: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error creating PR: %s", e)
    return False

async def submit_override(token: str, feature: str, override_data: Dict[str, Any]) -> bool:
    """Full flow to submit an override as a PR."""
    repo = "OtisPresley/snmp-switch-manager"
    base_branch = "main"
    
    # 1. Get user info
    user_info = await get_user(token)
    if not user_info:
        return False
    username = user_info["login"]
    
    # 2. Fork repo
    forked_repo = await fork_repo(token, repo)
    if not forked_repo:
        return False
    
    # Wait for fork to be ready (GitHub takes a few seconds)
    await asyncio.sleep(2)
    
    # 3. Get latest commit of target branch
    ref_data = await get_ref(token, repo, base_branch)
    if not ref_data:
        return False
    sha = ref_data["object"]["sha"]
    
    # 4. Create a new branch in the fork
    vendor = override_data.get("vendor", "unknown").lower().replace(" ", "-")
    branch_name = f"override-{feature}-{vendor}-{int(time.time())}"
    fork_full_name = f"{username}/snmp-switch-manager"
    
    ref_created = await create_ref(token, fork_full_name, branch_name, sha)
    if not ref_created:
        return False
        
    # 5. Get file content from ORIGINAL repo
    file_path = f"custom_components/snmp_switch_manager/database/{feature}.json"
    file_data = await get_file(token, repo, file_path)
    if not file_data:
        return False
        
    # Decode content
    content_str = base64.b64decode(file_data["content"]).decode("utf-8")
    try:
        db = json.loads(content_str)
    except Exception:
        db = []
        
    # Append new item
    db.append(override_data)
    
    # Encode back
    new_content = json.dumps(db, indent=2)
    new_content_base64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    
    # Get SHA of file in the fork on the new branch
    fork_file_data = await get_file(token, fork_full_name, file_path, ref=branch_name)
    if not fork_file_data:
        return False
    file_sha = fork_file_data["sha"]
    
    # 6. Update file in the fork
    updated = await update_file(token, fork_full_name, file_path, branch_name, file_sha, new_content_base64)
    if not updated:
        return False
        
    # 7. Create Pull Request
    pr_title = f"Add {feature} override for {override_data.get('vendor')}"
    pr_body = f"Automated PR from SNMP Switch Manager.\n\nAdded override:\n```json\n{json.dumps(override_data, indent=2)}\n```"
    
    pr_created = await create_pull_request(token, repo, base_branch, f"{username}:{branch_name}", pr_title, pr_body)
    
    return pr_created
