# StoriesChat UI Redesign — Design Spec (2026)

> **What this doc is for:** Full design spec for the 2026 Netflix+Character.AI UI redesign. Edit this doc when UI screens, components, CSS system, or navigation changes.

## Context

The original terminal-style `frontend/index.html` was replaced with a modern
dark SPA that blends Netflix-style game discovery with Character.AI-style chat.
This document is the canonical design spec.

The user-provided screenshots that drove this design:
1. **Character.AI profile page** — dark bg, rounded avatar, follower/interaction counts, icon tab row, empty state
2. **Character.AI Chats list (compact)** — dark bg, square-rounded thumbnails, game title, bottom Create sheet
3. **Character.AI Chats list (expanded)** — full list: Zeno Re9, Sukuna, Fushiguro, Gojo, Bruce Wayne, Percy Jackson RP, Elon Musk, Yor Forger
4. **Character.AI chat screen** — character name + "c.ai" badge, chat bubbles, right panel: Voice/History/Customize/Pinned/Persona/Style
5. **Character.AI search** — character cards, trending panel
6. **Netflix desktop** — hero banner, "Today's Top Picks", horizontal card rows with TOP 10 and Recently Added badges
7. **Netflix mobile home** — "For [User]" header, horizontal rows, "Gems for You", "Mobile Games"
8. **Netflix mobile rows** — genre rows: "Japanese Movies & TV", "Boredom Busters", "We Think You'll Love These"

**Design synthesis:**
- Home page = Netflix dark rows, but card styling is Character.AI (square, rounded, with emoji/image)
- Chat = Character.AI exact clone (bubbles, avatar, name badge, 3-dot menu)
- My Games = Character.AI Chats list (session thumbnail + title + last time)
- Create = Character.AI Create flow, simplified for games
- Profile = Character.AI profile adapted for game stats
- Color palette = Netflix dark (#141414) — NOT the white Character.AI palette

---

## Screen Inventory

### 1. Home Screen (`#screen-home`)
**Purpose:** Game discovery — feels like Netflix

**Layout:**
- Top bar: "StoriesChat" logo (red) + search icon + profile icon
- Hero banner: Featured game with gradient overlay, genre badge, title, description, "Play" + "More Info" buttons
- Game rows (horizontal scroll):
  - "Featured Games" (wide 16:9 cards)
  - Per-genre rows (e.g., "Murder Mystery", "Romance")
  - "All Games"
- Each card: 130px wide, 2:3 aspect image, genre badge overlay, title below

**API calls:**
- `GET /api/stories` → renders all rows
- Card click → Game Detail Modal

---

### 2. My Games Screen (`#screen-games`)
**Purpose:** Currently active/recent sessions — feels like Character.AI Chats

**Layout:**
- Top bar: "My Games" + "+" button (→ Home)
- List of sessions from localStorage (`storieschat_sessions`)
- Each row: 56px square-rounded thumbnail (emoji), game title, last message snippet, time ago
- Empty state: "No games yet" with "Explore Games" button

**Data source:** localStorage only — no backend call needed for the list

---

### 3. Chat Screen (`#screen-chat`)
**Purpose:** In-game conversation — Character.AI exact clone (no tab bar)

**Layout:**
- Top bar: back arrow, centered character name + genre sub-label, 3-dot menu
- Character header (shown at session start): 80px avatar, game title, genre badge
- Messages area (scrollable):
  - NPC: left-aligned bubble (dark #1e1e1e), small emoji avatar left
  - Player: right-aligned bubble (red #e50914)
  - System: centered muted text
- Typing indicator: animated 3 dots (visible while awaiting response)
- Input area: rounded textarea + red send button (fixed bottom)

**3-dot menu items:**
- 🗺 World Map → shows `#map-modal`
- 🔬 Debug Info → toggles debug mode, sends `[DEBUG]` to backend
- 💡 Truth Mode → toggles, sends `[TRUTH]` to backend
- 🀄 Chinese Mode → toggles, sends `[CHINESE]` to backend
- 🧠 Epistemic State → toggles, sends `[EPISTEMICSTATE]` to backend
- 🚪 Exit Game → confirm → returns to Home

---

### 4. Create Screen (`#screen-create`)
**Purpose:** Create a new game draft — simplified Character.AI Create flow

**Fields:**
- Game Title (text input, max 100)
- Genre (select: Murder Mystery / Romance / Horror / Fantasy / Comedy / Sci-Fi / Thriller)
- Short Description (textarea, max 500)

**API call:** `POST /api/stories/draft` → `{ title, genre, description }`

**On success:** Shows green success banner. Game appears in `/api/stories` list.

---

### 5. Profile Screen (`#screen-profile`)
**Purpose:** Player identity + stats + settings — Character.AI profile adapted

**Sections:**
- Avatar (emoji), username, handle
- Stats: Games played / Wins / Turns (from localStorage `storieschat_stats`)
- Settings: Dark Mode (always on, decorative toggle), Notifications (coming soon)
- About: App version (from `/version.json`), link to Debug Console

---

## CSS Design System

### Color Variables
```css
--bg:           #141414;   /* Netflix background */
--surface:      #1c1c1c;   /* Cards, modals */
--card:         #222222;   /* Input backgrounds */
--card-hover:   #2a2a2a;
--border:       #2e2e2e;
--red:          #e50914;   /* Netflix red — primary accent */
--red-dark:     #b2070f;   /* Hover/pressed state */
--text:         #ffffff;
--text-sub:     #aaaaaa;
--text-muted:   #666666;
--bubble-user:  #e50914;   /* Player chat bubble */
--bubble-npc:   #1e1e1e;   /* NPC chat bubble */
```

### Typography
- Font: System UI sans-serif (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`)
- NO monospace — this is the key break from the old terminal UI
- Base: 15px / 1.5 line-height

### Layout Constants
```css
--tab-h:        60px;    /* Bottom tab bar height */
--top-h:        56px;    /* Top bar height */
--radius:       12px;    /* Standard card radius */
--radius-sm:    8px;     /* Small card radius */
--radius-bubble:18px;    /* Chat bubble radius */
```

---

## Component Library

### GameCard
```
.game-card (130px wide, 2:3 image, .wide variant for 16:9)
  .game-card-img (image or emoji fallback, .card-genre-badge overlay)
  .game-card-body (.game-card-title)
```

### ChatBubble
```
.msg-row.npc → .msg-avatar + .msg-bubble.npc
.msg-row.user → .msg-bubble.user
.msg-row.system → .msg-bubble.system-msg
```

### TabBar
```
#tab-bar
  .tab-item (data-screen="home|games|create|profile")
    .tab-icon
    span (label)
```
Tab bar is hidden when `#screen-chat` is active.

### TopBar
```
.top-bar
  .back-btn (← back)
  .logo (StoriesChat wordmark)
  .page-title (centered)
  .top-actions (.icon-btn)
```

---

## localStorage Schema

### Sessions (`storieschat_sessions`) — Array
```json
[
  {
    "story_id": "jennie_murder_mini",
    "story_title": "The Quiet Agreement",
    "session_id": "uuid-v4",
    "player_name": "Alex",
    "gender": "M",
    "started_at": 1700000000000,
    "last_played": 1700003600000,
    "last_message": "I know you were there that night.",
    "turns": 12
  }
]
```
Max 50 sessions stored. Newest first.

### Profile (`storieschat_profile`)
```json
{ "name": "Player", "handle": "@player" }
```

### Stats (`storieschat_stats`)
```json
{ "games": 3, "wins": 1, "turns": 47 }
```

---

## PWA Setup

### Files
- `frontend/manifest.json` — App name, theme, icons (inline SVG), standalone display
- `frontend/sw.js` — Cache-first for shell, network-first for `/api/*`

### Backend routes (main.py)
```python
GET /manifest.json        → FileResponse(frontend/manifest.json)
GET /beta/manifest.json   → same
GET /sw.js                → FileResponse(frontend/sw.js)
GET /beta/sw.js           → same
```

### Install trigger
- HTML `<link rel="manifest" href="manifest.json" />`
- `<meta name="theme-color" content="#141414" />`
- Apple PWA meta tags
- `navigator.serviceWorker.register("sw.js")` in JS boot

---

## Story JSON New Fields

Fields added to each story JSON to support the new UI:

```json
{
  "description": "Short 1-3 sentence teaser for the game card and modal.",
  "genre": "Murder Mystery",
  "thumbnail_url": null,
  "featured": true
}
```

- `description`: Shown on game cards and detail modal. Max ~200 chars displayed.
- `genre`: Used for row grouping on home screen and badge overlays.
- `thumbnail_url`: Optional path to a card image. If null, falls back to emoji icon.
- `featured`: If true, appears in the "Featured Games" row and can be the hero.

The `/api/stories` endpoint returns all four fields.

---

## Backend Changes

### `backend/app/api/stories.py`
- `list_stories()` now returns `genre`, `description`, `thumbnail_url`, `featured` per story
- New `POST /api/stories/draft` endpoint:
  - Accepts `{ title, genre, description }`
  - Generates slug-based ID: `draft_{slug}_{6-char-hex}`
  - Saves stub JSON to `backend/app/stories/`
  - Returns `{ id, title }`

### `backend/app/main.py`
- Imports `FileResponse`
- Adds `_MANIFEST_PATH` and `_SW_PATH` path constants
- Adds 4 new routes for PWA assets (`/manifest.json`, `/beta/manifest.json`, `/sw.js`, `/beta/sw.js`)

---

## Scalability Notes

The UI is fully stateless on the server side:
- All session/profile/stats data lives in localStorage
- The backend only stores active LLM state (in-memory, keyed by session UUID)
- 100+ concurrent users = 100+ in-memory sessions, no coordination needed
- Story drafts are written to disk — at scale these should move to a database, but for MVP the file-based approach is fine
- The PWA service worker caches the shell — reduces Railway egress at scale

---

## Preserved Legacy Functionality

All original bracket commands still work, now via the 3-dot menu or by typing them directly in the chat input:

| Command | Trigger in new UI |
|---------|-------------------|
| `[DEBUG]` | 🔬 Debug Info menu item |
| `[TRUTH]` | 💡 Truth Mode menu item |
| `[CHINESE]` | 🀄 Chinese Mode menu item |
| `[EPISTEMICSTATE]` | 🧠 Epistemic State menu item |
| `[MAP]` | 🗺 World Map menu item |
| `[EXIT]` | 🚪 Exit Game menu item |

The integration playback feature is now accessible only via the `/debug` console URL (debug.html).
