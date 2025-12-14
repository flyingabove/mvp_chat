<?php
header('Content-Type: application/json; charset=utf-8');
$raw=file_get_contents('php://input');
echo json_encode(['method'=>$_SERVER['REQUEST_METHOD'] ?? 'CLI','raw'=>$raw,'json'=>json_decode($raw,true)]);