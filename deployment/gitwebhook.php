<?php
/**
 * GitHub Webhook Deployment — SAFE & CORRECT
 * - Pulls repo for beta/prod
 * - Deploys ONLY frontend
 * - PRESERVES /api and /webhook
 * - Does NOT delete backend
 */

$SECRET = "vtJ43JLqcKXsrC3u6ZQjVnBX878Qcmnfo2BmYd7xpkdu14h/PPrxZ6L9UESfrxqaWlo+dabbCe8JNtfburg4pGIWjemb+VllZC62iZ2//twMuDBJ1GjmZCKVP77Iy41dSEPg18y7jhrD9KZ50NtDL5xTfcL9GgxwBBV7J7zk9sKjT/CIkl9jd9gEUGy+zqc92wGcWTZ/znU0QR5zu3tc0FxApKcgvIwcDTuO5bXkbr1LRB6Jcfu+eCW9uRhfJmJiJ4TX3hMZQIBxZZVX+3c1g2KVMRKEmDwbEgkyr5cF2uPxEsL4D1WCaiUEiOZGIhsPB8hpsAeHb8YEWrwSNLqj";

/* -----------------------------
   Validate GitHub signature
----------------------------- */
$payload   = file_get_contents("php://input");
$signature = $_SERVER["HTTP_X_HUB_SIGNATURE_256"] ?? "";
$expected  = "sha256=" . hash_hmac("sha256", $payload, $SECRET);

if (!hash_equals($expected, $signature)) {
    http_response_code(403);
    echo "Invalid signature";
    exit;
}

$event = json_decode($payload, true);
$ref   = $event["ref"] ?? "";

/* -----------------------------
   Determine branch → repo + target
----------------------------- */
if ($ref === "refs/heads/beta") {
    $repoDir   = "/home/storvrfx/repositories/mvp_chat_beta";
    $publicDir = "/home/storvrfx/public_html/beta";
} elseif ($ref === "refs/heads/prod") {
    $repoDir   = "/home/storvrfx/repositories/mvp_chat_prod";
    $publicDir = "/home/storvrfx/public_html";
} else {
    echo "Ignored branch: $ref";
    exit;
}

/* -----------------------------
   1. Pull repo
----------------------------- */
exec("cd $repoDir && git reset --hard HEAD && git pull 2>&1", $gitOutput);

/* -----------------------------
   2. Clean target directory (safe)
----------------------------- */
exec(
    "find $publicDir -mindepth 1 -maxdepth 1 \
     ! -name 'api' \
     ! -name 'webhook' \
     -exec rm -rf {} +",
    $cleanOutput
);

/* -----------------------------
   3. Copy frontend only
----------------------------- */
exec(
    "rsync -av --delete \
     --exclude='.git/' \
     --exclude='.github/' \
     --exclude='Dockerfile' \
     --exclude='Railway.toml' \
     $repoDir/frontend/ $publicDir/",
    $rsyncOutput
);

/* -----------------------------
   Logging
----------------------------- */
file_put_contents(
    "/home/storvrfx/deploy.log",
    "===== Deployment: $ref =====\n".
    "GIT:\n".implode("\n",$gitOutput)."\n\n".
    "CLEAN:\n".implode("\n",$cleanOutput)."\n\n".
    "RSYNC:\n".implode("\n",$rsyncOutput)."\n\n",
    FILE_APPEND
);

echo "OK";
