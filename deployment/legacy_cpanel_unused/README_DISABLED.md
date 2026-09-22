# Legacy cPanel deployment — DEAD, DO NOT RE-ENABLE

These two files are a retired cPanel/PHP deployment mechanism. They are kept only
as history. **Nothing here runs.** Do not re-enable either without re-reading this
file and re-running the verification below.

Quarantined 2026-09-21 as Phase 0A of
`documentation/ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md`.

## Why these are dead

Both environments are served entirely by **Railway**, with Cloudflare in front.
Verified by response headers on 2026-09-21:

```
$ curl -sI https://storieschat.ai/
HTTP/1.1 200 OK
x-railway-edge: lax1
x-railway-request-id: 4uwaib2LTti1adYnlt7tkg

$ curl -sI https://beta-api.storieschat.ai/api/health
x-railway-edge: lax1
x-railway-request-id: 7108quqdRCGP3dPzqmzx2A
```

No Apache/LiteSpeed/cPanel signature on any host. The frontend is served by
FastAPI itself (`backend/app/main.py` — `FileResponse` for `index.html`,
`StaticFiles` for `/img`), not by a copied web root. So the cPanel tasks have no
target and the PHP webhook has no live listener.

## What was wrong with them

### `gitwebhook.php.disabled` — leaked credential (was P0)

It contained a **literal HMAC signing secret** in source. That file was tracked in
git, so the secret is present in history across at least five commits:
`2caee48`, `57c1a9a`, `612d104`, `0fa402e`, `0578a87`.

**Removing it from the working tree does not remove it from history.** Anyone with
read access to this repository can recover the original value. Treat it as public.

Changes made here:
- The literal was replaced with `getenv("GITWEBHOOK_SECRET")`, purely so this file
  is no longer a credential store.
- It now **fails closed**: with no env var set it returns `503` and exits, instead
  of computing an HMAC against an empty secret.

### `cpanel.yml.disabled` — destructive, ran against the prod web root (was P1)

It ran `/bin/rm -rf $DEPLOYPATH/*` and `/bin/rm -rf $BETAPATH/*` against
`/home/storvrfx/public_html`, with:
- no exit-code checking, so a failed copy could leave an emptied web root;
- **one checkout copied to both prod and beta**, which directly contradicts the
  webhook's per-branch routing — whichever ran last would win.

Both delete lines were removed. The file is retained only to show what the old
process did.

## Still outstanding — owner action required

Quarantining the file does **not** rotate the credential. Tracked as **BL-14** in
`documentation/BACKLOG.md`.

If the GitHub webhook still exists for this repository, its secret must be
rotated or the webhook deleted, because the old value is recoverable from git
history. This needs repository-settings access:

1. GitHub → repo **Settings → Webhooks**.
2. If a webhook points at `gitwebhook.php` on the cPanel host: **delete it** (it
   serves no purpose now that Railway deploys) or rotate its secret and set
   `GITWEBHOOK_SECRET` on the host.
3. Confirm no other automation depends on it.

Deleting is preferred. Railway deploys from the `beta` and `prod` branches
directly, so this webhook is redundant as well as compromised.

## If you ever need to bring cPanel back

Do not restore these files as-is. Start over with:
- the secret in an env var (never in source);
- explicit per-branch isolation — prod and beta must not derive from one checkout;
- explicit file ownership instead of `rm -rf` on a web root;
- exit-code checks on every step;
- immutable release identities so a rollback is possible.
