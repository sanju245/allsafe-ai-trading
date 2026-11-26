"""Offline, fail-closed release gate for a Guardian repair candidate.

This module never deploys. Platform-specific promotion must consume a passing
gate record and provide its own verified credentials and rollback adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable


ALLOWED_PATH = "apps/web/src/components/landing/WhatWeDonePage.tsx"
SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_ADDED_CODE = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon|eval|Function|require|import|localStorage|sessionStorage)\b"
    r"|process\.env|document\.cookie|dangerouslySetInnerHTML|<script|https?://",
    re.IGNORECASE,
)


def evaluate(manifest: dict, patch: bytes, triage: dict) -> list[str]:
    """Return all release blockers; an empty list is necessary, not sufficient."""
    blockers: list[str] = []
    if len(patch) > 12_000 or b"\x00" in patch:
        blockers.append("patch size or binary content exceeds policy")
    try:
        lines = patch.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return ["patch is not UTF-8"]
    changed = [line for line in lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    added = [line[1:] for line in changed if line.startswith("+")]
    if any(FORBIDDEN_ADDED_CODE.search(line) for line in added):
        blockers.append("added code contains network, secret, dynamic execution, or browser storage surface")
    headers = [line for line in lines if line.startswith("diff --git ")]
    if len(changed) > 80 or len(headers) != 1 or headers[0] != f"diff --git a/{ALLOWED_PATH} b/{ALLOWED_PATH}":
        blockers.append("patch is outside the single-file, 80-line allowlist")
    if f"--- a/{ALLOWED_PATH}" not in lines or f"+++ b/{ALLOWED_PATH}" not in lines:
        blockers.append("patch file headers are invalid")
    if any(line.startswith(("rename ", "new file ", "deleted file ", "GIT binary patch", "old mode ", "new mode ", "new file mode ", "deleted file mode ")) for line in lines):
        blockers.append("patch changes file identity or contains binary data")
    if [line for line in lines if line.startswith("--- ")] != [f"--- a/{ALLOWED_PATH}"] or [line for line in lines if line.startswith("+++ ")] != [f"+++ b/{ALLOWED_PATH}"]:
        blockers.append("patch has unexpected file headers")
    if triage.get("deployment_allowed") is not False:
        blockers.append("AI triage must explicitly deny deployment authority")
    if manifest.get("patch_sha256") != hashlib.sha256(patch).hexdigest():
        blockers.append("patch digest mismatch")
    candidate = manifest.get("candidate_sha")
    baseline = manifest.get("baseline_sha")
    if not isinstance(candidate, str) or not SHA.fullmatch(candidate):
        blockers.append("candidate commit is not pinned")
    if not isinstance(baseline, str) or not SHA.fullmatch(baseline) or baseline == candidate:
        blockers.append("distinct baseline commit is not pinned")
    ci = manifest.get("ci", {})
    for job in ("frontend", "backend", "targeted_repair"):
        record = ci.get(job, {}) if isinstance(ci, dict) else {}
        if record.get("conclusion") != "success" or record.get("head_sha") != candidate or not record.get("run_url"):
            blockers.append(f"{job} CI evidence is missing or mismatched")
    reviews = manifest.get("reviews", {})
    names = []
    for role in ("qa", "security"):
        record = reviews.get(role, {}) if isinstance(reviews, dict) else {}
        if record.get("verdict") != "pass" or record.get("candidate_sha") != candidate or not record.get("evidence_url") or not record.get("reviewer"):
            blockers.append(f"{role} independent review is missing or mismatched")
        else:
            names.append(record["reviewer"])
    if len(names) != 2 or names[0] == names[1]:
        blockers.append("QA and security reviewers must be distinct")
    previous = manifest.get("previous_known_good", {})
    if not isinstance(previous, dict) or not all(previous.get(k) for k in ("git_sha", "vercel_deployment_id", "render_deploy_id")):
        blockers.append("previous known-good release is not pinned for both services")
    elif not SHA.fullmatch(str(previous["git_sha"])):
        blockers.append("previous known-good git SHA is invalid")
    if manifest.get("rollback_drill") != "pass" or not manifest.get("rollback_evidence_url"):
        blockers.append("rollback drill is not evidenced")
    if manifest.get("production_change_scope") != "public-frontend-only":
        blockers.append("production change scope is not public-frontend-only")
    return blockers


def rollback_once(
    pinned_targets: dict[str, str],
    restore: Callable[[str, str], bool],
    healthy: Callable[[str], bool],
) -> list[str]:
    """Restore each pinned service at most once; stop immediately on failure."""
    completed: list[str] = []
    for service, deployment_id in pinned_targets.items():
        if service not in ("vercel", "render") or service in completed or not deployment_id:
            raise ValueError("unrecognized or duplicate rollback target")
        if not restore(service, deployment_id):
            raise RuntimeError(f"rollback restore failed for {service}; stop and escalate")
        if not healthy(service):
            raise RuntimeError(f"rollback health failed for {service}; stop and escalate")
        completed.append(service)
    return completed


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: guardian_release_gate.py manifest.json candidate.patch triage.json", file=sys.stderr)
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    patch = Path(sys.argv[2]).read_bytes()
    triage = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    blockers = evaluate(manifest, patch, triage)
    # This offline tool cannot authenticate CI runs, reviewer identities, or
    # rollback evidence. Never let self-asserted JSON become deploy authority.
    blockers.append("trusted evidence provenance and platform rollback drill are not verified")
    print(json.dumps({"gate": "HOLD", "blockers": blockers}, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
