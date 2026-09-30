# Owner actions: webhook secret and API key rotation

## BL-14 — GitHub webhook secret is recoverable from git history (owner action)
- **Open:** `deployment/gitwebhook.php` once held a literal HMAC secret (history: `2caee48`, `57c1a9a`, `612d104`, `0fa402e`, `0578a87`); the file is disabled and fails closed, but history still has the value.
- **Next:** delete the webhook in GitHub settings (preferred; the cPanel/PHP path has no live listener since Railway serves both hosts) or rotate the secret and set `GITWEBHOOK_SECRET`. History rewrite was rejected (it breaks the parallel-agent workflow).

## BL-05 — Rotate any API key that went through the old Docker build-arg path (owner action)
- **Open:** before commit `1cf4c9d` the Dockerfile persisted `OPENAI_API_KEY` from a build ARG into image `ENV`. If such an image was ever built with a real key, rotate it in the provider dashboard and the deployment secret.
