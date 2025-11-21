<?php
/*
  Universal secure router for PROD + BETA
  ---------------------------------------
  - Serves backend files from OUTSIDE public_html
  - Auto-detects whether request is prod or beta
  - Routes ANY file under api/ or stories/
  - Prevents directory traversal attacks
  - Static files (json, txt, etc) are streamed safely
  - PHP files are executed via include()
*/

$isBeta = strpos($_SERVER['REQUEST_URI'], '/beta/') === 0;

// Backend root directories (outside web root)
$prodBackend = "/home/storvrfx/prod_backend";
$betaBackend = "/home/storvrfx/beta_backend";

// Choose correct environment
$backendRoot = $isBeta ? $betaBackend : $prodBackend;

// Requested backend file, ex: api/chat.php or stories/x.json
$path = isset($_GET['path']) ? ltrim($_GET['path'], "/") : "";
$fullPath = realpath($backendRoot . "/" . $path);

// SECURITY: Stop directory traversal attempts
if (!$fullPath || strpos($fullPath, $backendRoot) !== 0) {
    http_response_code(404);
    echo "Invalid path";
    exit;
}

// File must exist
if (!file_exists($fullPath)) {
    http_response_code(404);
    echo "File not found";
    exit;
}

// Determine MIME type
$ext = strtolower(pathinfo($fullPath, PATHINFO_EXTENSION));
$mime = [
    "php"  => "text/html",
    "json" => "application/json",
    "txt"  => "text/plain",
    "csv"  => "text/csv",
];

/* Default MIME if unknown */
$ctype = isset($mime[$ext]) ? $mime[$ext] : "application/octet-stream";
header("Content-Type: $ctype");

/* Execute PHP files, serve static assets normally */
if ($ext === "php") {
    include $fullPath;
} else {
    readfile($fullPath);
}
exit;
?>
