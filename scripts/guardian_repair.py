"""Bounded, read-only Guardian incident diagnosis for the scheduled workflow.

The only automatic repair here is recovery from transient probe/provider failures:
bounded retries and selection of an actually available Groq chat model. A persistent
website incident remains open for an independently reviewed code repair.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from guardian_candidate import validate_patch


BASE_URL = "https://allsafe-ai-trading.vercel.app"
ROUTES = ("/", "/login", "/admin/login", "/privacy", "/what-we-done")
GROQ_URL = "https://api.groq.com/openai/v1/"
PREFERRED_MODELS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct-0905",
)
MAX_PROBE_ATTEMPTS = 3
MAX_PROVIDER_ATTEMPTS = 2
MAX_PROVIDER_WAIT_SECONDS = 5


def retry_after_seconds(headers: object) -> int | None:
    """Return a provider-directed delay, or None when it cannot be trusted."""
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return 2
    value = str(raw).strip()
    if re.fullmatch(r"[0-9]{1,9}", value):
        return int(value)
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            return None
        return max(0, int((target - datetime.now(timezone.utc)).total_seconds()) + 1)
    except (TypeError, ValueError, OverflowError):
        return None


def probe(route: str, opener=urllib.request.urlopen, sleeper=time.sleep) -> dict:
    """Require two observations of a failure before declaring an incident."""
    observations: list[int | str] = []
    for attempt in range(MAX_PROBE_ATTEMPTS):
        request = urllib.request.Request(BASE_URL + route, headers={"User-Agent": "AllSafe-Guardian/1.0"})
        try:
            with opener(request, timeout=15) as response:
                observation: int | str = response.status
        except urllib.error.HTTPError as exc:
            observation = exc.code
        except (OSError, TimeoutError):
            observation = "transport_error"
        observations.append(observation)
        if observation == 200:
            break
        if attempt + 1 < MAX_PROBE_ATTEMPTS:
            sleeper(attempt + 1)
    return {"status": observations[-1], "observations": observations, "recovered_by_retry": len(observations) > 1 and observations[-1] == 200}


def choose_model(models: object) -> tuple[str | None, list[str]]:
    if not isinstance(models, list):
        return None, []
    available = sorted({
        model["id"] for model in models
        if isinstance(model, dict)
        and isinstance(model.get("id"), str)
        and model.get("active", True)
        and re.fullmatch(r"[a-zA-Z0-9_./-]{1,150}", model["id"])
    })
    return next((model for model in PREFERRED_MODELS if model in available), None), available


def groq_request(path: str, key: str, payload: dict | None = None, opener=urllib.request.urlopen, sleeper=time.sleep) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GROQ_URL + path,
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AllSafe-Guardian/1.0",
        },
    )
    for attempt in range(MAX_PROVIDER_ATTEMPTS):
        try:
            with opener(request, timeout=30) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError("Unexpected Groq response")
            return result
        except urllib.error.HTTPError as exc:
            # A 403 is an access problem; retrying it or changing credentials is unsafe.
            if exc.code == 403:
                raise RuntimeError("Groq HTTP 403: access denied; inspect account and endpoint") from None
            if exc.code == 429:
                delay = retry_after_seconds(exc.headers)
                if delay is None or delay > MAX_PROVIDER_WAIT_SECONDS:
                    raise RuntimeError("Groq HTTP 429: retry deferred beyond bounded wait") from None
                if attempt + 1 < MAX_PROVIDER_ATTEMPTS:
                    sleeper(delay)
                    continue
            raise RuntimeError(f"Groq HTTP {exc.code}") from None
    raise RuntimeError("Groq retry budget exhausted")


def generated_text(result: dict) -> str:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    answer = message.get("content") if isinstance(message, dict) else None
    return answer if isinstance(answer, str) else ""


def analyze_incident(checks: dict, key: str) -> dict:
    if not key:
        return {"state": "unavailable", "reason": "GROQ_API_KEY unavailable"}
    try:
        model, available = choose_model(groq_request("models", key).get("data", []))
        if model is None:
            return {"state": "unavailable", "reason": "No preferred chat model available", "available_models": available}
        prompt = (
            "Analyze only these public HTTP status observations. Give possible causes "
            "and safe diagnostic steps. Do not claim a proven root cause, request "
            "secrets, propose trading or authentication changes, or propose deployment. "
            + json.dumps(checks, sort_keys=True)
        )
        result = groq_request("chat/completions", key, {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
        })
        answer = generated_text(result)
        if not answer.strip():
            return {"state": "unavailable", "reason": "No generated text returned", "model": model}
        return {"state": "generated", "model": model, "analysis": answer[:4000]}
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        # Fixed error messages above avoid including provider response bodies or keys.
        return {"state": "unavailable", "reason": str(exc)}


def propose_candidate(checks: dict, key: str, model: str | None) -> dict:
    """Ask for an evidence-only patch, then reject anything outside the UI fence."""
    candidate_path = Path("guardian-candidate.patch")
    candidate_path.write_text("", encoding="utf-8")
    if not key or not model:
        return {"state": "none", "reason": "Provider unavailable"}
    source_path = Path("apps/web/src/components/landing/WhatWeDonePage.tsx")
    try:
        source = source_path.read_text(encoding="utf-8")[:16_000]
    except (OSError, ValueError):
        return {"state": "none", "reason": "Public component unavailable for review"}
    prompt = (
        "You are preparing a candidate for human review, never a deployment. "
        "Given only these public status observations and the start of one public UI "
        "component, return NO_PATCH unless the evidence directly supports a fix "
        "in that component. If supported, return only a unified git diff for "
        "apps/web/src/components/landing/WhatWeDonePage.tsx. Never change "
        "authentication, trading, customer data, secrets, network calls, or "
        "package scripts. Do not invent a root cause. Observations: "
        + json.dumps(checks, sort_keys=True) + "\nComponent:\n" + source
    )
    try:
        result = groq_request("chat/completions", key, {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
        })
        answer = generated_text(result)
        accepted, reason = validate_patch(answer)
        if not accepted:
            return {"state": "none", "reason": reason}
        candidate_path.write_text(answer, encoding="utf-8")
        return {"state": "untrusted_candidate", "reason": "Path and size check only; no automatic application or execution"}
    except (RuntimeError, ValueError, OSError, TimeoutError):
        return {"state": "none", "reason": "Candidate generation unavailable"}


def main() -> int:
    checks = {route: probe(route) for route in ROUTES}
    incident = any(result["status"] != 200 for result in checks.values())
    report = {
        "checks": checks,
        "incident": incident,
        "automatic_repair_scope": "Transient probe retry and available Groq model selection only",
        "deployment_allowed": False,
        "automated_patch_execution_allowed": False,
    }
    if incident:
        report["analysis"] = analyze_incident(checks, os.environ.get("GROQ_API_KEY", ""))
        model = report["analysis"].get("model") if report["analysis"]["state"] == "generated" else None
        report["candidate"] = propose_candidate(checks, os.environ.get("GROQ_API_KEY", ""), model)
    Path("guardian-triage.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("Guardian incident:", incident)
    for route, result in checks.items():
        print(route, result["observations"])
    if incident:
        print("AI analysis state:", report["analysis"]["state"])
    return 1 if incident else 0


if __name__ == "__main__":
    sys.exit(main())
