import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from guardian_release_gate import ALLOWED_PATH, evaluate, rollback_once
from guardian_platform_adapters import verify_github_ci, verify_distinct_pr_approvals, rollback_vercel, rollback_render


PATCH = (f"diff --git a/{ALLOWED_PATH} b/{ALLOWED_PATH}\n"
         "index 1111111..2222222 100644\n"
         f"--- a/{ALLOWED_PATH}\n+++ b/{ALLOWED_PATH}\n"
         "@@ -1 +1 @@\n-old public copy\n+new public copy\n").encode()
CANDIDATE = "a" * 40


def manifest():
    return {
        "patch_sha256": hashlib.sha256(PATCH).hexdigest(),
        "candidate_sha": CANDIDATE,
        "baseline_sha": "b" * 40,
        "ci": {job: {"conclusion": "success", "head_sha": CANDIDATE, "run_url": "https://github.com/example/run"}
               for job in ("frontend", "backend", "targeted_repair")},
        "reviews": {role: {"verdict": "pass", "candidate_sha": CANDIDATE,
                            "reviewer": role, "evidence_url": "https://www.dropbox.com/example"}
                    for role in ("qa", "security")},
        "previous_known_good": {"git_sha": "c" * 40, "vercel_deployment_id": "dpl_old", "render_deploy_id": "dep_old"},
        "rollback_drill": "pass", "rollback_evidence_url": "https://www.dropbox.com/drill",
        "production_change_scope": "public-frontend-only",
    }


class ReleaseGateTests(unittest.TestCase):
    def test_complete_evidence_is_eligible_for_review(self):
        self.assertEqual(evaluate(manifest(), PATCH, {"deployment_allowed": False}), [])

    def test_missing_independent_evidence_holds(self):
        data = manifest()
        data["reviews"]["qa"]["candidate_sha"] = "d" * 40
        data["rollback_drill"] = "missing"
        blockers = evaluate(data, PATCH, {"deployment_allowed": False})
        self.assertTrue(any("qa independent" in b for b in blockers))
        self.assertTrue(any("rollback drill" in b for b in blockers))

    def test_out_of_scope_patch_holds(self):
        altered = PATCH.replace(ALLOWED_PATH.encode(), b"apps/api/app/security.py")
        data = manifest()
        data["patch_sha256"] = hashlib.sha256(altered).hexdigest()
        self.assertTrue(any("allowlist" in b for b in evaluate(data, altered, {"deployment_allowed": False})))

    def test_ai_cannot_authorize_deployment(self):
        self.assertTrue(any("AI triage" in b for b in evaluate(manifest(), PATCH, {"deployment_allowed": True})))

    def test_added_network_call_holds_even_in_allowlisted_file(self):
        altered = PATCH.replace(b"+new public copy", b"+fetch('https://example.invalid/collect')")
        data = manifest()
        data["patch_sha256"] = hashlib.sha256(altered).hexdigest()
        self.assertTrue(any("network" in b for b in evaluate(data, altered, {"deployment_allowed": False})))

    def test_rollback_stops_after_first_failed_service(self):
        attempts = []
        def restore(service, deployment_id):
            attempts.append((service, deployment_id))
            return service != "vercel"
        with self.assertRaises(RuntimeError):
            rollback_once({"vercel": "dpl_old", "render": "dep_old"}, restore, lambda _: True)
        self.assertEqual(attempts, [("vercel", "dpl_old")])

    def test_rollback_requires_health(self):
        attempts = []
        with self.assertRaises(RuntimeError):
            rollback_once({"vercel": "dpl_old", "render": "dep_old"}, lambda s, d: attempts.append((s, d)) or True, lambda _: False)
        self.assertEqual(attempts, [("vercel", "dpl_old")])

    def test_cli_holds_even_with_self_asserted_complete_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
            (root / "candidate.patch").write_bytes(PATCH)
            (root / "triage.json").write_text(json.dumps({"deployment_allowed": False}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "guardian_release_gate.py"),
                 str(root / "manifest.json"), str(root / "candidate.patch"), str(root / "triage.json")],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["gate"], "HOLD")

    def test_github_ci_checks_exact_sha_and_both_jobs(self):
        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return json.dumps(self.value).encode()
        def opener(req, timeout):
            if req.full_url.endswith("/jobs?per_page=100"):
                return Response({"jobs": [{"name": "frontend", "conclusion": "success"},
                                          {"name": "backend", "conclusion": "success"}]})
            return Response({"head_sha": CANDIDATE, "conclusion": "success", "name": "Guardian verification"})
        self.assertTrue(verify_github_ci(123, CANDIDATE, opener))
        self.assertFalse(verify_github_ci(123, "d" * 40, opener))

    def test_pr_approvals_require_distinct_reviewers_at_exact_commit(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps({"reviews": [
                    {"user": {"login": "qa-user"}, "state": "APPROVED", "commit_id": CANDIDATE},
                    {"user": {"login": "security-user"}, "state": "APPROVED", "commit_id": CANDIDATE},
                ]}).encode()
        self.assertTrue(verify_distinct_pr_approvals(20, CANDIDATE, "qa-user", "security-user", lambda *_args, **_kw: Response()))
        self.assertFalse(verify_distinct_pr_approvals(20, CANDIDATE, "qa-user", "qa-user", lambda *_args, **_kw: Response()))

    def test_platform_rollback_calls_pinned_ids_and_render_autodeploy_guard(self):
        seen = []
        class Response:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *_): return False
        def opener(req, timeout):
            seen.append((req.full_url, req.get_method(), req.data))
            return Response()
        self.assertTrue(rollback_vercel("prj_example", "dpl_previous", "secret-test-token", "team_example", opener))
        with self.assertRaises(ValueError):
            rollback_render("srv_example", "dep_previous", "secret-test-token", autodeploy_disabled=False, opener=opener)
        self.assertTrue(rollback_render("srv_example", "dep_previous", "secret-test-token", autodeploy_disabled=True, opener=opener))
        self.assertIn("/rollback/dpl_previous", seen[0][0])
        self.assertIn("/services/srv_example/rollback", seen[1][0])
        self.assertEqual(json.loads(seen[1][2]), {"deployId": "dep_previous"})


if __name__ == "__main__":
    unittest.main()
