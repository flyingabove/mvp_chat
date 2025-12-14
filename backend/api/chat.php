<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
session_start();

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/game_logic.php';

function json_error(string $msg, int $code=400) {
  http_response_code($code);
  echo json_encode(['error'=>$msg], JSON_UNESCAPED_SLASHES);
  exit;
}

$raw = file_get_contents('php://input');
if (!$raw) json_error('no body');
$in = json_decode($raw, true);
if (!is_array($in)) json_error('bad json');

$msg = (string)($in['message'] ?? '');

if (!isset($_SESSION['state']) || !is_array($_SESSION['state'])) $_SESSION['state'] = init_state();
if (!isset($_SESSION['log'])   || !is_array($_SESSION['log']))   $_SESSION['log']   = [];

$state = &$_SESSION['state'];
$log   = &$_SESSION['log'];

/** Replace {{PLAYER_NAME}} and {{HONORIFIC}} in any story text */
function apply_placeholders(string $text, array $state): string {
  $name = $state['player_name'] ?? 'Player';
  $honorific = ($state['gender'] === 'F') ? 'unnie' : 'oppa';
  $repl = [
    '{{PLAYER_NAME}}' => $name,
    '{{HONORIFIC}}'   => $honorific
  ];
  return strtr($text, $repl);
}

// Commands
if ($msg === '__cmd_reset__') {
  $_SESSION['state'] = init_state();
  $_SESSION['log']   = [];
  echo json_encode(['reply'=>'[memory cleared]', 'usage'=>['total_tokens'=>0], 'character'=>'default']);
  exit;
}

if (strpos($msg, '__cmd_newgame__:') === 0) {
  // format: __cmd_newgame__:<story_id>|<F/M>|<player_name>
  $payload = substr($msg, strlen('__cmd_newgame__:'));
  [$story_id, $gender, $player_name] = array_pad(explode('|', $payload, 3), 3, '');
  $gender = strtoupper(trim($gender ?: 'M'));
  $player_name = preg_replace('/[^A-Za-z\s\-\'"]/','', trim($player_name));
  $player_name = mb_substr($player_name ?: 'Player', 0, 40, 'UTF-8');

  $cfg = load_story($story_id);
  if (!$cfg) json_error("story not found: $story_id", 404);

  // Reset & seed
  $state = init_state();
  $state['story']       = $story_id;
  $state['gender']      = ($gender === 'F' ? 'F' : 'M');
  $state['player_name'] = $player_name;
  $state['_story_cfg']  = $cfg;
  $state['location']    = $cfg['setting']['start_location'] ?? START_LOCATION;
  $state['iu_emotion']  = $cfg['emotion']['start'] ?? EMOTION_START;

  // Deterministic opening (with placeholders)
  $opening = (string)($cfg['opening']['text'] ?? "The room is quiet. A story begins.");
  $opening = apply_placeholders($opening, $state);

  $_SESSION['log'] = [
    ['role'=>'system','content'=>system_prompt($state)],
    ['role'=>'assistant','content'=>$opening],
  ];
  echo json_encode(['reply'=>$opening, 'usage'=>['total_tokens'=>0], 'character'=>'default']);
  exit;
}

// Regular turn flow
if (empty($state['story']) || empty($state['_story_cfg'])) {
  echo json_encode(['reply'=>'No active game. Choose a story, enter your name, and select F/M to start.', 'character'=>'default']); exit;
}
if ($state['over']) {
  echo json_encode(['reply'=>'Game already finished. Type /reset to play again.', 'character'=>'default']); exit;
}

advance_time($state, $msg);
$state['turns'] += 1;

$messages = build_messages($state, $log, $msg);

// --- OpenAI call (unchanged) ---
$payload = json_encode([
  'model' => OPENAI_MODEL,
  'messages' => $messages,
  'temperature' => TEMPERATURE,
  'max_tokens' => MAX_TOKENS,
], JSON_UNESCAPED_SLASHES);

$ch = curl_init('https://api.openai.com/v1/chat/completions');
curl_setopt_array($ch, [
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_POST => true,
  CURLOPT_HTTPHEADER => [
    'Content-Type: application/json',
    'Authorization: Bearer ' . OPENAI_API_KEY
  ],
  CURLOPT_POSTFIELDS => $payload,
  CURLOPT_TIMEOUT => 30,
]);
$resp = curl_exec($ch);
if ($resp === false) json_error('upstream error: '.curl_error($ch), 502);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);
if ($code < 200 || $code >= 300) json_error("upstream HTTP {$code}: {$resp}", 502);

$data  = json_decode($resp, true);
$reply = (string)($data['choices'][0]['message']['content'] ?? '');

// State tag
[$clean, $tag] = extract_state_tag($reply);
if (!is_array($tag)) { $tag = ['iu_emotion'=>$state['iu_emotion'], 'rel_delta'=>0]; }
apply_state_tag($state, $tag);

// Update memory
$log[] = ['role'=>'user','content'=>$msg];
$log[] = ['role'=>'assistant','content'=>$clean];
$log   = array_slice($log, -MEMORY_TURNS);

// Win detection
if (confession_detected($clean, $state)) {
  $state['over'] = true;
  $clean .= "\n\nEND GAME YOU WIN — turns: {$state['turns']}";
}

echo json_encode(['reply'=>$clean, 'usage'=>$data['usage'] ?? null, 'character'=>'default'], JSON_UNESCAPED_SLASHES);
