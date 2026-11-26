"""Unwired, testable release evidence and pinned rollback adapters.

No entry point invokes a production mutation. A future trusted release runner
must perform fresh gate checks before calling either rollback function.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO = "sanju245/allsafe-ai-trading"
ID = re.compile(r"^[A-Za-z0-9_-]{4,100}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def _json_get(url: str, opener=urlopen) -> dict:
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AllSafe-Guardian-Gate/1.0"})
    with opener(req, timeout=15) as response:
        return json.load(response)


def verify_github_ci(run_id: int, candidate_sha: str, opener=urlopen) -> bool:
    """Confirm real GitHub run and both independent jobs for the pinned SHA."""
    if not isinstance(run_id, int) or run_id <= 0 or not SHA.fullmatch(candidate_sha):
        return False
    base = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}"
    try:
        run = _json_get(base, opener)
        if run.get("head_sha") != candidate_sha or run.get("conclusion") != "success" or run.get("name") != "Guardian verification":
            return False
        jobs = _json_get(base + "/jobs?per_page=100", opener).get("jobs", [])
        names = {job.get("name") for job in jobs if job.get("conclusion") == "success"}
        return {"frontend", "backend"}.issubset(names)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def verify_distinct_pr_approvals(
    pr_number: int, candidate_sha: str, qa_login: str, security_login: str, opener=urlopen
) -> bool:
    """Require two protected-config reviewer logins approving the exact commit."""
    if not isinstance(pr_number, int) or pr_number <= 0 or not SHA.fullmatch(candidate_sha):
        return False
    if not qa_login or not security_login or qa_login == security_login:
        return False
    try:
        reviews = _json_get(f"https://api.github.com/repos/{REPO}/pulls/{pr_number}/reviews?per_page=100", opener).get("reviews", [])
        approvals = {review.get("user", {}).get("login") for review in reviews
                     if review.get("state") == "APPROVED" and review.get("commit_id") == candidate_sha}
        return {qa_login, security_login}.issubset(approvals)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _post(url: str, token: str, opener=urlopen) -> bool:
    if not token:
        raise ValueError("platform token unavailable")
    request = Request(url, data=b"{}", method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "User-Agent": "AllSafe-Guardian-Rollback/1.0",
    })
    with opener(request, timeout=20) as response:
        return response.status in (200, 201, 202)


def rollback_vercel(project_id: str, deployment_id: str, token: str, team_id: str, opener=urlopen) -> bool:
    """Request routing rollback to an exact prior production deployment ID."""
    if not all(ID.fullmatch(value or "") for value in (project_id, deployment_id, team_id)):
        raise ValueError("invalid Vercel rollback identifiers")
    url = (f"https://api.vercel.com/v1/projects/{quote(project_id)}/rollback/"
           f"{quote(deployment_id)}?teamId={quote(team_id)}")
    return _post(url, token, opener)


def rollback_render(service_id: str, deploy_id: str, token: str, *, autodeploy_disabled: bool, opener=urlopen) -> bool:
    """Request rollback to pinned deploy; refuse while Render autodeploy is on."""
    if not autodeploy_disabled:
        raise ValueError("Render autodeploy must be disabled before API rollback")
    if not all(ID.fullmatch(value or "") for value in (service_id, deploy_id)):
        raise ValueError("invalid Render rollback identifiers")
    url = f"https://api.render.com/v1/services/{quote(service_id)}/rollback"
    if not token:
        raise ValueError("platform token unavailable")
    request = Request(url, data=json.dumps({"deployId": deploy_id}).encode(), method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "User-Agent": "AllSafe-Guardian-Rollback/1.0",
    })
    with opener(request, timeout=20) as response:
        return response.status == 201
