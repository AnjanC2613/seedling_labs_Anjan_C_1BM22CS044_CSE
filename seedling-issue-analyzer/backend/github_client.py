import re
import logging
from typing import Tuple, List
import os

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def parse_github_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Parse and validate GitHub URL like:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/
      - https://github.com/owner/repo.git
    
    Returns (owner, repo) after validation.
    """
    # Parse basic structure
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(\.git)?/?$", str(repo_url))
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub repository URL. Expected format: https://github.com/owner/repo",
        )
    
    owner, repo = m.group(1), m.group(2)
    
    # Validate owner name (GitHub allows: alphanumeric, hyphens, underscores)
    # Max length is 39 characters
    if not re.match(r'^[a-zA-Z0-9_-]{1,39}$', owner):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository owner name. Must be 1-39 alphanumeric characters, hyphens, or underscores.",
        )
    
    # Validate repo name (GitHub allows: alphanumeric, hyphens, underscores, periods)
    # Max length is 100 characters
    if not re.match(r'^[a-zA-Z0-9_.-]{1,100}$', repo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository name. Must be 1-100 alphanumeric characters, hyphens, underscores, or periods.",
        )
    
    logger.info(f"Parsed GitHub repo: {owner}/{repo}")
    return owner, repo


def get_github_headers() -> dict:
    """Get GitHub API headers with optional authentication"""
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
        logger.debug("Using authenticated GitHub API requests")
    else:
        logger.warning("No GITHUB_TOKEN found - using unauthenticated requests (rate limited to 60/hour)")
    
    return headers


async def fetch_issue(owner: str, repo: str, issue_number: int) -> dict:
    """
    Fetch a GitHub issue by number.
    
    Raises HTTPException on errors with appropriate status codes.
    """
    if issue_number < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Issue number must be positive",
        )
    
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}"
    logger.info(f"Fetching issue: {owner}/{repo}#{issue_number}")
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, 
                headers=get_github_headers(),
                timeout=30.0
            )
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching issue from GitHub")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="GitHub API request timed out. Please try again.",
        )
    except httpx.RequestError as e:
        logger.error(f"Network error fetching issue: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Network error communicating with GitHub API.",
        )
    
    # Handle specific GitHub API responses
    if resp.status_code == 404:
        logger.warning(f"Issue not found: {owner}/{repo}#{issue_number}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue #{issue_number} not found in {owner}/{repo}. It may not exist or the repository may be private.",
        )
    
    if resp.status_code == 410:
        logger.warning(f"Issue gone (410): {owner}/{repo}#{issue_number}")
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Issue #{issue_number} has been permanently deleted.",
        )
    
    if resp.status_code == 403:
        logger.error(f"GitHub API rate limit or forbidden: {resp.status_code}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit exceeded. Please try again later or add a GITHUB_TOKEN.",
        )
    
    if resp.status_code >= 400:
        logger.error(f"GitHub API error: {resp.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error from GitHub API (status {resp.status_code}). Please try again.",
        )
    
    logger.info(f"Successfully fetched issue: {owner}/{repo}#{issue_number}")
    return resp.json()


async def fetch_issue_comments(owner: str, repo: str, issue_number: int) -> List[str]:
    """
    Fetch comments for a GitHub issue.
    
    Returns empty list on error (non-critical for triage).
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    logger.info(f"Fetching comments for: {owner}/{repo}#{issue_number}")
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, 
                headers=get_github_headers(),
                timeout=30.0
            )
        
        if resp.status_code >= 400:
            logger.warning(f"Failed to fetch comments (status {resp.status_code}), continuing without them")
            return []
        
        comments_json = resp.json()
        comment_bodies = [c.get("body", "") for c in comments_json if c.get("body")]
        
        logger.info(f"Fetched {len(comment_bodies)} comments")
        return comment_bodies
    
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning(f"Error fetching comments: {e}, continuing without them")
        return []