# ROLLBACK_PLAN

No database change is part of this work, so rollback is code-only.
1. Preferred: revert the merge commit on `main` (`git revert -m 1 <merge sha>`), push; Render auto-deploys the reverted code and Vercel redeploys.
2. Fast path: Render dashboard → `allsafe-ai-api` → Events/Deploys → redeploy the previous good deploy (`d012167`, live before this work). Vercel dashboard → redeploy the previous production deployment.
3. Rolling back restores the original (stricter) behaviour: **the Super Admin is again blocked from non-registered IPs.** Workaround while rolled back: sign in from the stored IP.
4. Env vars added by this work are optional; leaving them set is harmless.
5. Confirm after rollback: `/health` OK; customer sign-in from the registered IP works.
Never force-push `main`.
