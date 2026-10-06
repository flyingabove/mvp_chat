# Owner actions: webhook secret and API key rotation

## BL-14 — GitHub webhook secret is recoverable from git history (owner action)
- **Bucket:** A (owner action, no code)
- **Open:** `deployment/legacy_cpanel_unused/gitwebhook.php.disabled` (formerly `deployment/gitwebhook.php`) once held a literal HMAC secret (history: `2caee48`, `57c1a9a`, `612d104`, `0fa402e`, `0578a87`); the file is disabled and fails closed, but history still has the value.
- **Touches:** GitHub repository webhook settings only.
- **Next:** delete the webhook in GitHub settings (preferred; the cPanel/PHP path has no live listener since Railway serves both hosts) or rotate the secret and set `GITWEBHOOK_SECRET`. History rewrite was rejected (it breaks the parallel-agent workflow).

## BL-05 — Rotate any API key that went through the old Docker build-arg path (owner action)
- **Bucket:** A (owner action, no code)
- **Open:** before commit `1cf4c9d` the Dockerfile persisted `OPENAI_API_KEY` from a build ARG into image `ENV`. The code is fixed (the Dockerfile no longer writes the key into the image); only the owner action is left: if such an image was ever built with a real key, rotate it in the provider dashboard and the deployment secret.
- **Next:** owner rotates the key; delete this section.
- **Touches:** provider dashboard and Railway secrets only.
