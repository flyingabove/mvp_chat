<?php
/**
 * GitHub Webhook Deployment — HARD-SAFE
 * - NEVER deletes anything
 * - NEVER touches /webhook or /api
 * - Copies ONLY frontend-owned files
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
   Branch → paths
----------------------------- */
if ($ref === "refs/heads/beta") {
    $repoDir   = "/home/storvrfx/repositories/mvp_chat_beta";
    $targetDir = "/home/storvrfx/public_html/beta";
} elseif ($ref === "refs/heads/prod") {
    $repoDir   = "/home/storvrfx/repositories/mvp_chat_prod";
    $targetDir = "/home/storvrfx/public_html";
} else {
    echo "Ignored branch: $ref";
    exit;
}

/* -----------------------------
   Ensure target exists
----------------------------- */
if (!is_dir($targetDir)) {
    mkdir($targetDir, 0755, true);
}

/* -----------------------------
   Pull repo
----------------------------- */
exec(
    "cd $repoDir && git fetch origin && git reset --hard HEAD && git pull 2>&1",
    $gitOutput
);

/* -----------------------------
   Copy frontend files (WHITELIST)
----------------------------- */
$frontend = $repoDir . "/frontend";

$files = [
    "index.html",
    "dialogue.js",
    "dialogue.css",
    "version.json"
];

foreach ($files as $file) {
    $src = "$frontend/$file";
    $dst = "$targetDir/$file";

    if (file_exists($src)) {
        copy($src, $dst);
    }
}

/* -----------------------------
   Logging
----------------------------- */
file_put_contents(
    "/home/storvrfx/deploy.log",
    "===== DEPLOY $ref =====\n".
    "FILES COPIED: ".implode(", ", $files)."\n".
    "GIT:\n".implode("\n", $gitOutput)."\n\n",
    FILE_APPEND
);

echo "OK";
