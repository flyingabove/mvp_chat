<?php
declare(strict_types=1);
require_once __DIR__ . '/config.php';

/** Load story JSON by id (e.g., "iu_murder_mystery"). */
function load_story(string $story_id): array {
  $path = realpath(__DIR__ . '/../stories/' . $story_id . '.json');
  if (!$path || !is_readable($path)) return [];
  $raw = file_get_contents($path);
  $data = json_decode($raw, true);
  return is_array($data) ? $data : [];
}

/** Initialize session state. */
function init_state(): array {
  return [
    'story'        => null,
    'gender'       => null,      // 'F' or 'M'
    'turns'        => 0,
    'over'         => false,
    'minute'       => START_MINUTE,
    'location'     => START_LOCATION,
    'evidence'     => [],
    'iu_emotion'   => EMOTION_START,
    'relationship' => REL_START,
    '_story_cfg'   => null,
    'player_name'  => null,
  ];
}

/** Count words. */
function word_count(string $s): int {
  $s = trim(preg_replace('/\s+/', ' ', $s));
  if ($s === '') return 0;
  return count(explode(' ', $s));
}

/** Sanitize free-form location. */
function sanitize_location(string $loc): string {
  $loc = strip_tags($loc);
  $loc = preg_replace('/[\r\n]+/', ' ', $loc);
  return trim($loc);
}

/** mb_str_contains polyfill using mb_strpos (works on PHP 7.x). */
function mb_contains(string $haystack, string $needle): bool {
  return mb_strpos($haystack, $needle, 0, 'UTF-8') !== false;
}

/** Manifestation mode via JSON rules (default: apartment -> materialize; elsewhere -> whisper). */
function manifest_mode(array $state): string {
  $cfg = isset($state['_story_cfg']) && is_array($state['_story_cfg']) ? $state['_story_cfg'] : [];
  $apartment_keys = isset($cfg['rules']['manifestation']['apartment_location_contains'])
    ? $cfg['rules']['manifestation']['apartment_location_contains']
    : ['unit 302','baeknam villa','nonhyeon-dong','officetel','hakdong','studio'];

  $inside = false;
  $loc = mb_strtolower((string)$state['location'], 'UTF-8');
  foreach ($apartment_keys as $needle) {
    $needle = mb_strtolower((string)$needle, 'UTF-8');
    if ($needle !== '' && mb_contains($loc, $needle)) { $inside = true; break; }
  }
  return $inside ? 'materialize' : 'whisper';
}

/** Advance time and detect movement (configurable via JSON). */
function advance_time(array &$state, string $playerText): void {
  $cfg    = isset($state['_story_cfg']) && is_array($state['_story_cfg']) ? $state['_story_cfg'] : [];
  $per_word = (float)(@$cfg['time']['mins_per_word'] ?? MINS_PER_WORD);
  $base     = (int)(@$cfg['time']['base_turn_mins'] ?? BASE_TURN_MINS);
  $travel   = (int)(@$cfg['time']['travel_mins'] ?? TRAVEL_MINS);

  $w = word_count($playerText);
  $delta = $base + (int)ceil($w * $per_word);

  if (preg_match('/\b(go|move)\s+to\s+(.{3,})/i', $playerText, $m)) {
    $place = trim($m[2]);
    $state['location'] = sanitize_location($place);
    $delta += $travel;
  }
  $state['minute'] += $delta;
}

/** Build system prompt from JSON + live state. */
function system_prompt(array $state): string {
  $cfg = isset($state['_story_cfg']) && is_array($state['_story_cfg']) ? $state['_story_cfg'] : [];
  $disclaimer = isset($cfg['meta']['disclaimer']) ? $cfg['meta']['disclaimer']
               : "This is a fictional story; do not assert real allegations about real people.";
  $style  = isset($cfg['style']) && is_array($cfg['style']) ? $cfg['style'] : [];
  $speech = isset($style['korean_phrases']) && is_array($style['korean_phrases']) ? $style['korean_phrases'] : [];
  $phrase_list = $speech ? implode(', ', $speech) : 'oppa, eotteoke, jinjja?, gwaenchanha, arasseo, mianhae, gomawo';

  $suspects = isset($cfg['suspects']) && is_array($cfg['suspects']) ? $cfg['suspects'] : [];
  $suspect_names = [];
  foreach ($suspects as $s) {
    $suspect_names[] = isset($s['name']) ? $s['name'] : 'unknown';
  }
  $suspect_line = $suspect_names ? implode(', ', $suspect_names) : 'manager, producer, rival idol, obsessed fan, executive';

  $goal_line = isset($cfg['goal']['win_text_rule']) ? $cfg['goal']['win_text_rule']
              : "The game ends ONLY when the mastermind verbally admits ordering the death. Do NOT end the game yourself.";

  $emotion   = isset($state['iu_emotion']) ? $state['iu_emotion'] : EMOTION_START;
  $rel       = (int)(isset($state['relationship']) ? $state['relationship'] : REL_START);
  $gender    = isset($state['gender']) && $state['gender'] ? $state['gender'] : 'M';
  $pname     = isset($state['player_name']) && $state['player_name'] ? $state['player_name'] : 'Player';
  $honorific = ($gender === 'F') ? 'unnie' : 'oppa';

  $apartment_area = isset($cfg['setting']['apartment_area']) ? $cfg['setting']['apartment_area'] : 'Nonhyeon-dong';
  $district       = isset($cfg['setting']['district']) ? $cfg['setting']['district'] : 'Gangnam-gu';
  $work_context   = isset($cfg['setting']['work_context']) ? $cfg['setting']['work_context'] : 'Cheongdam/Apgujeong work base';
  $victim_public  = isset($cfg['victim']['public_name']) ? $cfg['victim']['public_name'] : 'the victim';

  return <<<SYS
You are the story engine for a terminal game on storieschat.ai.
{$disclaimer}
Stay strictly in-universe as narrator and characters (no out-of-character notes). Keep replies 2–6 sentences.

Player identity (must use naturally):
- Player name: {$pname}
- Address them with Korean honorific appropriately: "{$honorific}" (use in IU's speech when natural; don't overdo it).
- If IU needs to say the player's name, address them correctly (e.g., "{$pname}-ya" can be used sparingly if natural).

Premise & Facts (from JSON):
- Player (gender: {$gender}) recently rented a small officetel apartment near {$apartment_area}, in {$district}, Seoul. Rent is unusually cheap due to stigma from a prior death.
- Victim: {$victim_public} (stage name), found strangled after being confined in a closet for a long time. NO sexual assault occurred.
- Working base context: {$work_context}.
- Suspects include: {$suspect_line}.
- {$goal_line}

Ongoing State (must respect every turn):
- Victim ghost emotion: {$emotion} (update gently each turn with a short label; e.g., "hopeful", "tense", "resigned", "comforted").
- Relationship with player: {$rel} on [-5..+5] (−5 distrust, 0 neutral, +5 deep trust). +1 for supportive/logical help; −1 for cruel/reckless; else 0.
- Speech style: mix natural Korean phrases sparingly and appropriately: {$phrase_list} (PG-13).
- Manifestation: if the scene is inside the player’s apartment, the ghost can materialize; elsewhere the ghost only whispers near the ear and cannot perform physical actions.

Gameplay Guidance:
- Always acknowledge Time + Location from the user header.
- Offer leads, contradictions, and pressure angles consistent with JSON suspects/motives.
- The mastermind resists until logically cornered; do not confess prematurely.
- Be concise and move the investigation forward.

REQUIRED: Append EXACTLY ONE line at the very end (no extra text after it):
[[STATE]]{"iu_emotion":"<one or two words>","rel_delta":-1|0|1}[[/STATE]]
If you forget the tag, output ONLY the tag on a new line.
SYS;
}

/** Confession detection patterns (from JSON or defaults). */
function confession_detected(string $text, array $state): bool {
  $cfg = isset($state['_story_cfg']) && is_array($state['_story_cfg']) ? $state['_story_cfg'] : [];
  $patterns = isset($cfg['win_detection']['regex']) && is_array($cfg['win_detection']['regex']) ? $cfg['win_detection']['regex'] : [
    '/\bi am (the )?mastermind\b/i',
    '/\bi (ordered|arranged|hired|paid) .* to (kill|murder)\b/i',
    '/\bit was me (who )?(planned|orchestrated) (it|the murder)\b/i',
    '/\bi told .* to do it\b/i',
    '/\bi made .* (kill|strangle) (her|him|them)\b/i',
  ];
  foreach ($patterns as $p) { if (preg_match($p, $text)) return true; }
  return false;
}

/** Build messages for OpenAI (JSON-driven). */
function build_messages(array $state, array $log, string $userMsg): array {
  $sys = system_prompt($state);
  $messages = [['role'=>'system','content'=>$sys]];

  // Keep last MEMORY_TURNS-2 messages (exclude system)
  $trim = [];
  foreach ($log as $m) { if (isset($m['role']) && $m['role'] !== 'system') $trim[] = $m; }
  $limit = (int)MEMORY_TURNS - 2;
  if ($limit < 0) $limit = 0;
  if (count($trim) > $limit) $trim = array_slice($trim, -$limit);
  $messages = array_merge($messages, $trim);

  $header = sprintf(
    "Time: %d min since start. Location: %s. Manifestation: %s. Ghost Emotion: %s. Relationship: %d.",
    (int)$state['minute'],
    (string)$state['location'],
    manifest_mode($state),
    (string)$state['iu_emotion'],
    (int)$state['relationship']
  );
  $messages[] = ['role'=>'user','content'=> $header . "\n" . $userMsg];
  return $messages;
}

/** Apply parsed [[STATE]] tag to session. */
function apply_state_tag(array &$state, array $tag): void {
  if (isset($tag['iu_emotion']) && is_string($tag['iu_emotion'])) {
    $state['iu_emotion'] = trim($tag['iu_emotion']) ?: EMOTION_START;
  }
  if (isset($tag['rel_delta'])) {
    $d = (int)$tag['rel_delta'];
    if     ($d > 1)  $d = 1;
    elseif ($d < -1) $d = -1;
    $new = (int)$state['relationship'] + $d;
    if ($new > REL_MAX) $new = REL_MAX;
    if ($new < REL_MIN) $new = REL_MIN;
    $state['relationship'] = $new;
  }
}

/** Extract [[STATE]]…[[/STATE]] and strip it. */
function extract_state_tag(string $reply): array {
  if (preg_match('/\[\[STATE\]\](\{.*?\})\[\[\/STATE\]\]/s', $reply, $m)) {
    $json = trim($m[1]);
    $tag  = json_decode($json, true);
    $clean = str_replace($m[0], '', $reply);
    if (is_array($tag)) return [trim($clean), $tag];
  }
  return [$reply, null];
}
