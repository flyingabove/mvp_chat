<?php
/******************************************************************************
 * STORIESCHAT FRONTEND DEPLOY HOOK
 * --------------------------------
 * Deploys frontend for BETA or PROD automatically based onpushed branch.
 *
 * Branch → Repo → Deploy path:
 *   beta → /home/storvrfx/repositories/mvp_chat_beta/frontend → /home/storvrfx/public_html/beta
 *   prod → /home/storvrfx/repositories/mvp_chat_prod/frontend → /home/storvrfx/public_html
 *
 * Back-end is deployed by Railway, and is NOT touched here.
 ******************************************************************************/

$SECRET = "AAAAB3NzaC1yc2EAAAADAQABAAABAQDFvtJ43JLqcKXsrC3u6ZQjVnBX878Qcmnfo2BmYd7xpkdu14h/PPrxZ6L9UESfrxqaWlo+dabbCe8JNtfburg4pGIWjemb+VllZC62iZ2//twMuDBJ1GjmZCKVP77Iy41dSEPg18y7jhrD9KZ50NtDL5xTfcL9GgxwBBV7J7zk9sKjT/CIkl9jd9gEUGy+zqc92wGcWTZ/znU0QR5zu3tc0FxApKcgvIwcDTuO5bXkbr1LRB6Jcfu+eCW9uRhfJmJiJ4TX3hMZQIBxZZVX+3c1g2KVMRKEmDwbEgkyr5cF2uPxEsL4D1WCaiUEiOZGIhsPB8hpsAeHb8YEWrwSNLqj";   // <-- Replace in GitHub webhook settings

/* -------------------- SECURITY CHECK --------------------*/
$headers = getallheaders();
$payload = file_get_contents("php://input");

if (!isset($headers['X-Hub-Signature-256'])) {
    http_response_code(403);
    error_log("[WEBHOOK] Missing signature.\n", 3, __DIR__ . "/webhook.log");
    exit("Forbidden");
}

$signature = $headers['X-Hub-Signature-256'];
$expected  = "sha256=" . hash_hmac("sha256", $payload, $SECRET);

if (!hash_equals($expected, $signature)) {
    http_response_code(403);
    error_log("[WEBHOOK] Invalid signature.\n", 3, __DIR__ . "/webhook.log");
    exit("Forbidden");
}

/* -------------------- PARSE EVENT -------------------- */
$data = json_decode($payload, true);
$branch = basename($data["ref"] ?? "");

$log = __DIR__ . "/webhook.log";
file_put_contents($log, "Webhook triggered for branch: $branch\n", FILE_APPEND);

/* -------------------- DETERMINE TARGET -------------------- */
$mapping = [
    "beta" => [
        "repo" => "/home/storvrfx/repositories/mvp_chat_beta",
        "src"  => "/home/storvrfx/repositories/mvp_chat_beta/frontend",
        "dst"  => "/home/storvrfx/public_html/beta"
    ],
    "prod" => [
        "repo" => "/home/storvrfx/repositories/mvp_chat_prod",
        "src"  => "/home/storvrfx/repositories/mvp_chat_prod/frontend",
        "dst"  => "/home/storvrfx/public_html"
    ],
];

if (!array_key_exists($branch, $mapping)) {
    file_put_contents($log, "Unknown branch. Ignoring.\n", FILE_APPEND);
    exit("OK");
}

$repo = $mapping[$branch]["repo"];
$src  = $mapping[$branch]["src"];
$dst  = $mapping[$branch]["dst"];

file_put_contents($log, "Deploying branch '$branch' from $src to $dst\n", FILE_APPEND);

/* -------------------- GIT PULL -------------------- */
chdir($repo);
exec("git reset --hard HEAD 2>&1", $o1);
exec("git clean -f -d 2>&1", $o2);
exec("git pull origin $branch 2>&1", $o3);

file_put_contents($log, "GIT RESET: " . implode("\n", $o1) . "\n", FILE_APPEND);
file_put_contents($log, "GIT CLEAN: " . implode("\n", $o2) . "\n", FILE_APPEND);
file_put_contents($log, "GIT PULL: " . implode("\n", $o3) ."\n", FILE_APPEND);

/* -------------------- DEPLOY FRONTEND -------------------- */
if (!is_dir($src)) {
    file_put_contents($log, "ERROR: Source folder not found: $src\n", FILE_APPEND);
    exit("Missing source folder");
}

if (!is_dir($dst)) {
    mkdir($dst, 0755, true);
}

function rrmdir($dir) {
    $items = scandir($dir);
    foreach ($items as $item) {
        if ($item === "." || $item === "..") continue;
        $path = "$dir/$item";
        if (is_dir($path)) rrmdir($path);
        else unlink($path);
    }
    rmdir($dir);
}

// Remove only frontend files in target (NOT entire site)
foreach (glob("$dst/*") as $item) {
    if (is_dir($item)) rrmdir($item);
    else unlink($item);
}

// Copy new frontend
exec("cp -R $src/* $dst/ 2>&1", $copyOut);
file_put_contents($log, "COPY OUTPUT: " . implode("\n", $copyOut) . "\n", FILE_APPEND);

file_put_contents($log, "DEPLOY COMPLETE for branch '$branch'.\n\n", FILE_APPEND);

echo "OK";