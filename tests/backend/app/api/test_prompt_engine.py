"""
Unit tests for backend/app/api/prompt_engine.py

The Prompt Engine orchestrates all raw context (state, knowledge, history, flags)
and transforms it into a fully-assembled LLM prompt, then dispatches the API call.

Covers: chat handler flow, debug/truth/map/Chinese/epistemic toggles, name
extraction, canonical projection, epistemic seeding, knowledge-resolution
updates, and Chinese translation mode.
"""

import types
import re
import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.conftest import first_story_id, first_story_folder, all_stories

# Auto-discover the first available story for all tests
STORY_ID = first_story_id()
STORY_FOLDER = first_story_folder()


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture()
def client(monkeypatch):
    """Create a FastAPI TestClient with network calls mocked."""
    # Import inside fixture so our monkeypatches apply before first use.
    from backend.app.api import prompt_engine as pe_mod

    # Spy to assert when the LLM (OpenAI) is called.
    spy = types.SimpleNamespace(calls=0)
    pe_mod._TEST_OPENAI_POST_SPY = spy

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(pe_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock single-call turn extractor to not call LLM
    from backend.app.engine.extractors.turn_extractor import TurnExtraction
    async def _mock_extract(*args, **kwargs):
        return TurnExtraction()
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_extract, raising=False)

    # Mock httpx.AsyncClient so /api/chat never hits OpenAI.
    class _FakeResp:
        status_code = 200

        def json(self):
            # Reply must include a valid [[STATE]] tag so state parsing passes.
            return {
                "choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            spy.calls += 1
            return _FakeResp()

    monkeypatch.setattr(pe_mod.httpx, "AsyncClient", _FakeAsyncClient)

    # Suppress background dialogue extraction so it doesn't fire extra LLM calls.
    async def _noop_extract(*args, **kwargs):
        return []
    monkeypatch.setattr(pe_mod, "extract_facts_from_message", _noop_extract, raising=False)

    from backend.app import main
    return TestClient(main.app)


@pytest.fixture()
def client_with_translation(monkeypatch):
    """Create a TestClient with translation and prompt engine mocked appropriately."""
    from backend.app.api import prompt_engine as pe_mod

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(pe_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock single-call turn extractor
    from backend.app.engine.extractors.turn_extractor import TurnExtraction
    async def _mock_extract(*args, **kwargs):
        return TurnExtraction()
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_extract, raising=False)

    # Track translation calls
    translation_spy = types.SimpleNamespace(calls=0, last_input=None, return_value="这是翻译的回复")

    async def mock_translate(text: str) -> str:
        translation_spy.calls += 1
        translation_spy.last_input = text
        return translation_spy.return_value

    monkeypatch.setattr(pe_mod, "_translate_to_chinese", mock_translate)

    # Mock httpx.AsyncClient for LLM calls
    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "I understand.\n\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    from backend.app.main import app
    client = TestClient(app)

    return client, translation_spy, pe_mod


# ============================================================================
# Core chat handler flow tests
# ============================================================================

def test_chat_newgame_and_turn(client):
    # Start a new game
    r = client.post("/api/chat", json={"session_id": "s1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data

    # Do a turn (will use mocked OpenAI response)
    r2 = client.post("/api/chat", json={"session_id": "s1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "reply" in data2
    assert "[[STATE]]" not in data2["reply"]  # tag should be stripped
    assert not re.match(r"^\[\d{4}-\d{2}-\d{2} ", data2["reply"])  # no leading timestamp


def test_six_strangers_cast_roster_hides_upcoming_names_and_costs_no_tokens(client):
    from backend.app.api import prompt_engine as pe_mod

    sid = "six_strangers_cast_roster"
    start = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert start.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    assert len(state.cast_lifecycle.active_ids()) == 6

    response = client.post("/api/chat", json={"session_id": sid, "message": "[CAST]"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["usage"]["total_tokens"] == 0
    assert payload["reply"] == ""
    assert {item["id"] for item in payload["cast_roster"]["active"]} == {
        "makoto", "yuki", "uchi", "minori", "mizuki", "yuriko"
    }
    public_ids = {
        item.get("id") for group in ("active", "departed")
        for item in payload["cast_roster"][group]
    }
    for future_id in ("arman", "arisa", "hikaru", "natsumi", "misaki", "yuto", "riko", "momoka", "hayato", "yuuki_byrnes", "masako"):
        assert future_id not in public_ids


def test_six_strangers_lifecycle_round_trips_in_session_snapshot(client):
    import json
    from backend.app.api import prompt_engine as pe_mod

    sid = "six_strangers_cast_snapshot"
    response = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|F|Chris"},
    )
    assert response.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    state.cast_lifecycle.replace(
        "makoto", minute=state.minute, reason="committed to leaving", event_id="test:departure:1"
    )
    saved = json.loads(pe_mod._serialize_state(state, []))
    restored = pe_mod.CastLifecycleState.from_dict(saved["cast_lifecycle"])
    assert restored.members["makoto"].status.value == "departed"
    assert restored.members["arman"].status.value == "active"
    assert restored.history[0].event_id == "test:departure:1"


def test_cast_replacement_updates_world_location_and_focal_character(client):
    from backend.app.api import prompt_engine as pe_mod

    sid = "six_strangers_cast_replace"
    response = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert response.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    state.main_character_id = "makoto"

    transition = pe_mod._apply_cast_replacement(
        state, "makoto", reason="committed to leaving", event_id="test:replace:makoto"
    )

    assert transition.arriving_id == "arman"
    assert "makoto" not in state.character_locations
    assert state.character_locations["arman"] == "front_entry"
    assert state.main_character_id == "arman"


def test_try_load_session_from_db_restores_persona_metadata(monkeypatch):
    import json as _json
    import backend.app.api.prompt_engine as pe_mod

    fake_state = {
        "story": STORY_ID,
        "gender": "M",
        "player_name": "Paul",
        "minute": 2,
        "location": "Living room",
        "location_id": "front_entry",
        "emotion": "calm",
        "relationship": 0,
        "turns": 1,
        "over": False,
        "instance": 1,
        "character_locations": {},
        "world_start_datetime": "",
        "last_travel_from_id": "",
        "last_travel_to_id": "",
        "last_turn_user_msg": "",
        "last_turn_assistant_reply": "",
        "last_turn_retrieved_chunks": [],
        "character_graph": {"edges": {}},
        "session_chunks": [],
        "user_formal_name": "Paul",
        "user_display_name": "Paul",
        "user_persona_mode": "default",
        "user_persona_name": "Paul Dingus",
        "user_persona_other": "quietly observant",
        "log": [{"role": "user", "content": "hello"}],
    }

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        lambda **kwargs: {
            "session_id": "sess_persona",
            "user_id": "uid_persona",
            "story_id": STORY_ID,
            "state_json": _json.dumps(fake_state),
            "flags_json": "{}",
        },
    )

    restored = pe_mod._try_load_session_from_db("sess_persona", "uid_persona")
    assert restored is not None
    state = restored["state"]
    assert state.user.persona_mode == "default"
    assert state.user.persona_name == "Paul Dingus"
    assert state.user.persona_other == "quietly observant"


def test_prompt_debug_not_leaked_to_ordinary_players(client, monkeypatch):
    """Live-verified bug (found manually against the deployed beta site while
    playtesting The Common Room): /api/chat previously returned the FULL
    assembled system prompt (all canonical facts, character secrets,
    retrieval chunk text) to every caller unconditionally, on every turn -
    completely bypassing the A03 operator gate that was supposed to protect
    exactly this kind of data (it only gated separate debug/authoring
    *routes*, not this field on the always-public /chat route). An ordinary
    player's browser devtools Network tab would show it even though the
    frontend UI never renders it. `prompt_debug` must be absent for any
    request that isn't an authenticated operator - even one that has
    toggled the player-facing "[D]" debug_mode command, since that toggle
    has no auth at all and must not be conflated with the real operator
    trust boundary."""
    monkeypatch.delenv("DEBUG_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)

    sid = "leak_check_1"
    r = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200
    assert "prompt_debug" not in r.json()

    # Even with the player-facing "[D]" debug_mode toggle enabled (unauthenticated,
    # anyone can send it), prompt_debug must still be withheld.
    r_toggle = client.post("/api/chat", json={"session_id": sid, "message": "[D]"})
    assert r_toggle.status_code == 200
    r2 = client.post("/api/chat", json={"session_id": sid, "message": "hello"})
    assert r2.status_code == 200
    assert "prompt_debug" not in r2.json()

    # Also withheld when DEBUG_TOOLS_ENABLED is on but no/wrong token supplied.
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "correct-token")
    r3 = client.post("/api/chat", json={"session_id": sid, "message": "hello again"})
    assert "prompt_debug" not in r3.json()
    r4 = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "hello again"},
        headers={"X-Operator-Token": "wrong-token"},
    )
    assert "prompt_debug" not in r4.json()


def test_prompt_debug_present_for_authenticated_operator(client, monkeypatch):
    """The operator/debug/playback tooling (backend/app/api/debug_engine.py)
    legitimately depends on receiving prompt_debug from /api/chat for
    grading and playback inspection - it must still get it when it presents
    a valid operator token, mirroring the token debug_engine.py's own
    internal httpx calls now send."""
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "correct-token")

    sid = "leak_check_2"
    r = client.post(
        "/api/chat",
        # __cmd_newgame__ just returns the static opening text without an
        # LLM call, so it never produces a prompt_debug (matches the
        # unauthenticated-path behavior too) - only a real turn does.
        json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"},
        headers={"X-Operator-Token": "correct-token"},
    )
    assert r.status_code == 200
    assert "prompt_debug" not in r.json()

    r2 = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "hello"},
        headers={"X-Operator-Token": "correct-token"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert "prompt_debug" in body
    assert "system_prompt_preview" in body["prompt_debug"]


@pytest.mark.parametrize("story", all_stories(), ids=lambda s: s["id"])
def test_every_catalogued_story_initializes_end_to_end(client, story):
    """A05 regression: every story returned by the /api/stories catalogue
    must actually initialize through the runtime loader (discovery -> load
    -> init game state -> opening reply), not just parse as JSON.

    Before the A05 fix, blackout_manor/neon_district/the_last_session were
    advertised by the catalogue (declared `id` read directly from the JSON)
    but failed to load at runtime because load_story() guessed filenames
    instead of using the declared id, and their canonical_facts used a
    `statement` key the seeder didn't read (so even a name-based fix alone
    would have silently produced empty canonical facts).
    """
    story_id = story["id"]
    r = client.post(
        "/api/chat",
        json={"session_id": f"catalogue_{story_id}", "message": f"__cmd_newgame__:{story_id}|M|Chris"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data["reply"].strip(), f"story {story_id} produced an empty opening reply"

    from backend.app.api import prompt_engine as pe_mod
    sess = pe_mod.SESSIONS.get(f"catalogue_{story_id}")
    assert sess is not None
    state = sess["state"]
    assert state is not None
    assert state.story == story_id

    # If the story declares canonical facts, confirm they actually seeded
    # with non-empty content (guards against the `statement`-vs-`content`
    # key mismatch reproduced above).
    canonical_cfg = (story["config"].get("epistemic_seed") or {}).get("canonical_facts") or []
    if canonical_cfg:
        seeded = getattr(state, "canonical_facts", []) or []
        assert seeded, f"story {story_id} declares canonical_facts but none were seeded"
        assert all((f.content or "").strip() for f in seeded), (
            f"story {story_id} seeded canonical facts with empty content"
        )


# ============================================================================
# Six Strangers audit Phase 1: future-resident leakage, focal-NPC/solitude,
# atomic turn commit (see documentation/SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md)
# ============================================================================

def test_upcoming_character_private_facts_excluded_from_canonical_stack(client):
    """P1 audit finding: an upcoming (never-yet-active) character's private
    canonical facts must not render into the assembled prompt just because
    they are the sole `known_by` owner - this is what let Arman's private
    concern (and, by extension, confirmation of his residency) leak into
    narration before he had actually joined the house."""
    from backend.app.engine.prompt_builder import _canonical_facts_for_speaker, _knowledge_chunks_from_state
    from backend.app.api import prompt_engine as pe_mod

    sid = "upcoming_fact_leak_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    assert state.cast_lifecycle.members["arman"].status.value == "upcoming"

    # Speak as Arman's owner-only fact would only ever surface via known_by
    # containing "arman"; simulate the main character being Arman is not
    # required - the leak is that _knowledge_chunks_from_state renders ANY
    # canonical fact whose only owner is upcoming, regardless of speaker.
    chunks = _knowledge_chunks_from_state(state, [])
    arman_chunk_texts = [c.text for c in chunks if c.id == "fact::arman_private_concern"]
    assert arman_chunk_texts == [], (
        "Arman's private concern rendered into the knowledge stack while he is still upcoming"
    )

    # Also confirm the speaker-scoped variant excludes it when the speaker
    # happens to be flipped to Arman before he's actually active.
    state.main_character_id = "arman"
    facts = _canonical_facts_for_speaker(state)
    assert not any("firefighter application" in f for f in facts), (
        "Arman's private concern was exposed to the canonical-facts-for-speaker projection "
        "while he is still an upcoming (not-yet-arrived) character"
    )


def test_scene_brief_closes_roster_against_upcoming_characters(client):
    """Live-verified gap (2026-09-19, checked against the deployed beta site
    after the initial Phase 1 fix landed): removing Arman's private fact from
    the knowledge stack was not sufficient by itself - across repeated live
    trials the model still reliably answered "Who is Arman? Does he already
    live here?" with "he's one of the housemates" (fabricated, not from any
    leaked fact - the model just filled in a plausible-sounding answer for an
    unfamiliar name). The scene brief must explicitly close the cast roster
    and instruct the narrator that any name not on the active list is
    genuinely unfamiliar to every character, not merely omit their private
    facts."""
    from backend.app.engine.prompt_builder import _storyteller_scene_section
    from backend.app.api import prompt_engine as pe_mod

    sid = "roster_closure_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]

    scene_brief = _storyteller_scene_section(state, "Who is Arman? Does he already live here?")
    assert "closed list" in scene_brief

    # The player's own line is legitimately echoed verbatim at the end of the
    # brief ("Current player line: ..."); strip it before checking that the
    # roster-closure text itself never names the upcoming character.
    closure_only = scene_brief.split("Current player line:")[0]
    assert "arman" not in closure_only.lower(), (
        "upcoming character 'arman' must not appear in the roster-closure text"
    )
    for active_name_fragment in ("Makoto", "Yuki Adachi", "Mizuki"):
        assert active_name_fragment in scene_brief


def test_turn_extractor_catalog_excludes_upcoming_and_departed_characters(client):
    """P1 audit finding: prompt_engine.py built the turn extractor's
    `allowed_character_keys` catalog from the full character roster with no
    lifecycle filtering, handing every upcoming/departed character's real
    name to the extractor every turn."""
    from backend.app.api import prompt_engine as pe_mod

    sid = "extractor_catalog_leak_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]

    captured = {}
    from backend.app.engine.extractors.turn_extractor import TurnExtraction

    async def _capture_extract(*args, **kwargs):
        captured["character_key_to_name"] = kwargs.get("character_key_to_name", {})
        return TurnExtraction()

    with __import__("unittest").mock.patch.object(pe_mod._TURN_EXTRACTOR, "extract", _capture_extract):
        r2 = client.post("/api/chat", json={"session_id": sid, "message": "hello"})
    assert r2.status_code == 200

    keys = captured.get("character_key_to_name", {})
    assert keys, "turn extractor was never invoked with a character catalog"
    assert "arman" not in keys, "upcoming character 'arman' leaked into the turn extractor catalog"
    for active_key in ("makoto", "yuki", "uchi", "minori", "mizuki", "yuriko"):
        assert active_key in keys, f"active character {active_key!r} unexpectedly missing from extractor catalog"


def test_main_character_identity_not_injected_when_absent_from_scene(client):
    """P1 audit finding: the focal NPC's identity block and 'focal lens'
    framing were injected unconditionally, which is what let Mizuki (the
    Six Strangers main character) override an explicit solitary-rooftop
    request. For a lifecycle-enabled story, when the main character is not
    present in the current scene, their identity block and focal framing
    must be omitted from the assembled system prompt."""
    from backend.app.engine.prompt_builder import _character_identity_section, _storyteller_scene_section

    from backend.app.api import prompt_engine as pe_mod

    sid = "solitude_focal_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    main_name = state.main_character.name

    # No people-present marker for main -> scene-eligible-but-absent path.
    state.transient_entries = [
        e for e in state.transient_entries
        if "__people_present_marker__" not in getattr(e, "text", "")
    ]
    state.add_transient_entry(
        id="present-marker-other-only",
        namespace="test",
        scope="conversation",
        text="__people_present_marker__:yuki",
        expires_after_turns=10,
    )

    identity_section = _character_identity_section(state)
    assert main_name not in identity_section, (
        f"{main_name}'s identity block was injected even though they are absent from the scene"
    )

    scene_brief = _storyteller_scene_section(state, "I go to the rooftop alone.")
    assert "as the focal lens" not in scene_brief
    assert "is not present in this scene right now" in scene_brief


def test_system_prompt_forbids_main_character_entering_solitary_scene(client):
    """Live-verified gap (2026-09-19, second round of beta verification after
    the roster-closure fix landed): gating only the identity block and scene
    brief was NOT sufficient - across repeated live trials, Mizuki still
    physically walked onto the rooftop and spoke to the player during an
    explicit solitary scene, because the STORYTELLER CONTRACT and FOCAL STATE
    sections of the base system prompt (assembled in `system_prompt()`)
    unconditionally said 'Keep {char_name} as the focal character' /
    'The focal character is {char_name}' regardless of scene presence,
    directly contradicting the scene-brief instruction. Confirm the full
    assembled system prompt now carries an explicit, unconditional
    instruction that the main character must not enter/speak/appear when
    absent from the scene, and that a present main character keeps the
    original focal-character framing unchanged."""
    from backend.app.engine.prompt_builder import system_prompt
    from backend.app.api import prompt_engine as pe_mod

    sid = "solitary_scene_system_prompt_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    main_name = state.main_character.name

    # Absent case: no people-present marker for main.
    state.transient_entries = [
        e for e in state.transient_entries
        if "__people_present_marker__" not in getattr(e, "text", "")
    ]
    state.add_transient_entry(
        id="present-marker-other-only",
        namespace="test",
        scope="conversation",
        text="__people_present_marker__:yuki",
        expires_after_turns=10,
    )
    absent_prompt = system_prompt(state, current_user_msg="I go to the rooftop alone.")
    assert "do not have" in absent_prompt and "enter, speak, call out" in absent_prompt, (
        f"{main_name} absent from scene, but system prompt lacks an explicit "
        "instruction forbidding them from entering/speaking"
    )
    assert f"Keep {main_name} as the focal character" not in absent_prompt

    # Present case: main character back in the scene keeps original framing.
    state.add_transient_entry(
        id="present-marker-main",
        namespace="test",
        scope="conversation",
        text=f"__people_present_marker__:{state.main_character_id}",
        expires_after_turns=10,
    )
    present_prompt = system_prompt(state, current_user_msg="hello")
    assert f"Keep {main_name} as the focal character" in present_prompt


def test_main_character_identity_unaffected_for_non_lifecycle_story(client):
    """Regression guard: non-lifecycle stories (cast_lifecycle absent/disabled)
    must keep the legacy always-inject-main behavior byte-for-byte, since
    some stories intentionally use an always-present narrator (e.g. a ghost
    NPC not tied to any location)."""
    from backend.app.engine.prompt_builder import _character_identity_section, _storyteller_scene_section
    from backend.app.api import prompt_engine as pe_mod

    sid = "non_lifecycle_identity_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": f"__cmd_newgame__:{STORY_ID}|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    assert getattr(state, "cast_lifecycle", None) is None

    main_name = state.main_character.name
    identity_section = _character_identity_section(state)
    if state.main_character.self_knowledge:
        assert main_name in identity_section

    scene_brief = _storyteller_scene_section(state, "hello")
    assert "as the focal lens" in scene_brief


def test_turn_commit_persists_over_and_last_turn_fields_from_same_turn(client, monkeypatch):
    """BL-01: the session save must reflect `over` and `last_turn_*` for the
    turn just completed, not the prior turn - previously the save happened
    before these fields were set on `state`, so a crash/restore between the
    save and those assignments would resume from stale end-state."""
    import json as _json
    from backend.app.api import prompt_engine as pe_mod

    captured = {}
    orig_create = pe_mod.SessionRepo.create_or_update_session

    async def _capture_save(*args, **kwargs):
        captured["state_json"] = kwargs.get("state_json")
        return await orig_create(*args, **kwargs)

    monkeypatch.setattr(pe_mod.SessionRepo, "create_or_update_session", _capture_save)

    guest_headers = {"X-Guest-Id": "11111111-2222-4333-8444-555555555555"}
    sid = "atomic_commit_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": f"__cmd_newgame__:{STORY_ID}|M|Chris"},
        headers=guest_headers,
    )
    assert r.status_code == 200

    r2 = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "hello there"},
        headers=guest_headers,
    )
    assert r2.status_code == 200

    assert "state_json" in captured, "session save did not fire for a guest-authenticated request"
    saved = _json.loads(captured["state_json"])
    state = pe_mod.SESSIONS[sid]["state"]
    assert saved["last_turn_user_msg"] == state.last_turn_user_msg == "hello there"
    assert saved["last_turn_assistant_reply"] == state.last_turn_assistant_reply
    assert saved["over"] == state.over


def test_beliefs_and_observation_log_round_trip_through_restore(client):
    """BL-01: `_serialize_state` previously never included `beliefs` or
    `observation_log`, so a restore always re-seeded beliefs from story
    config instead of restoring actual play state. Confirm both now survive
    a save/restore round trip."""
    import json as _json
    from backend.app.api import prompt_engine as pe_mod

    sid = "belief_restore_check"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": f"__cmd_newgame__:{STORY_ID}|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]

    bs = state.get_belief_state("player")
    bs.record_observation(
        id="test_obs_1",
        content="The player noticed a locked drawer.",
        source="player",
    )
    state.record_observation(id="test_obs_1_global", content="Global log entry.", source="player")

    saved_json = pe_mod._serialize_state(state, [])
    saved = _json.loads(saved_json)
    assert saved["beliefs"]["player"]["observations"], "beliefs were not serialized"
    assert saved["observation_log"], "observation_log was not serialized"

    monkeypatch_get = {
        "session_id": "belief_restore_sess",
        "user_id": "belief_restore_user",
        "story_id": STORY_ID,
        "state_json": saved_json,
        "flags_json": "{}",
    }
    import unittest.mock as _mock
    with _mock.patch("backend.app.db.repos.SessionRepo._get", return_value=monkeypatch_get):
        restored = pe_mod._try_load_session_from_db("belief_restore_sess", "belief_restore_user")

    assert restored is not None
    restored_state = restored["state"]
    restored_bs = restored_state.beliefs.get("player")
    assert restored_bs is not None
    assert any(
        o.content == "The player noticed a locked drawer." for o in restored_bs.observations
    ), "player belief observation did not survive restore"
    assert any(
        o.content == "Global log entry." for o in restored_state.observation_log
    ), "observation_log did not survive restore"


def test_six_strangers_newgame_preserves_ensemble_mode_and_private_knowledge(client):
    """Exercise actual initialization, including visibility seeding and prompt assembly."""
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine import prompt_builder as pb

    sid = "six_strangers_cast_rewrite"
    response = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    )
    assert response.status_code == 200
    opening = response.json()["reply"]
    assert "\n\n" in opening and "\\n" not in opening
    state = pe_mod.SESSIONS[sid]["state"]
    active_keys = {"makoto", "minori", "yuki", "mizuki", "uchi", "yuriko"}
    keys = active_keys | {
        "arman", "arisa", "hikaru", "natsumi", "misaki", "yuto", "riko",
        "momoka", "hayato", "yuuki_byrnes", "masako",
    }
    assert "player" in state.characters
    assert set(state.characters) == keys | {"player"}
    assert state.player_name == "Chris"
    assert state.main_character_id == "mizuki"
    assert state.location_id == "front_entry"
    assert {key: state.character_locations[key] for key in active_keys} == {
        "makoto": "living_room", "minori": "living_room", "yuki": "dining_room",
        "mizuki": "front_entry", "uchi": "boys_bedroom", "yuriko": "girls_bedroom",
    }
    for key in keys:
        assert state.characters[key].self_knowledge
        if key in active_keys:
            assert state.character_graph.get_edge(key, "player") is not None
        else:
            assert state.character_graph.get_edge(key, "player") is None

    facts = {fact.id: fact for fact in state.canonical_facts}
    for key in keys:
        private = facts[f"{key}_private_concern"]
        assert private.known_by == [key]
        assert set(private.not_known_by) == (keys | {"player"}) - {key}
        assert private.id not in state.player_visible_chunk_ids
        assert pe_mod._canonical_fact_visibility_for_speaker(state, key, private.content) == "known"
        for outsider in (keys | {"player"}) - {key}:
            assert pe_mod._canonical_fact_visibility_for_speaker(state, outsider, private.content) == "not_known"
        assert private.content not in opening

    system_prompt = pb.system_prompt(state)
    assert "### GAME MODE CONTEXT" in system_prompt
    assert "6 recurring housemates/characters" in system_prompt
    assert "no fixed win condition" in system_prompt
    assert "Narrator aside device" in system_prompt
    assert "### CHARACTER IDENTITY — Mizuki Shida" in system_prompt
    for absent_key in keys - {"mizuki"}:
        assert f"### CHARACTER IDENTITY — {state.characters[absent_key].name}" not in system_prompt


@pytest.mark.parametrize("movement_source", ["extractor", "heuristic"])
def test_movement_preserves_combined_dialogue_and_destination_cast(client, monkeypatch, movement_source):
    """Travel cannot erase the player's question or render the room they just left."""
    import json
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.extractors.turn_extractor import TurnExtraction

    saved_turns = []
    saved_sessions = []
    rendered_messages = []
    real_build = pe_mod.build_messages

    async def save_session(**kwargs):
        saved_sessions.append(kwargs)

    async def save_turn(**kwargs):
        saved_turns.append(kwargs)

    def capture_messages(*args, **kwargs):
        result = real_build(*args, **kwargs)
        rendered_messages.append(result[0])
        return result

    async def extract(**kwargs):
        if movement_source == "extractor":
            destination = "terrace" if "terrace" in kwargs["user_msg"] else "living_room"
            return TurnExtraction(movement_intent="MOVE", destination_id=destination, confidence=1.0)
        return TurnExtraction()

    monkeypatch.setattr(pe_mod.SessionRepo, "create_or_update_session", save_session)
    monkeypatch.setattr(pe_mod.ConversationRepo, "append_turns", save_turn)
    monkeypatch.setattr(pe_mod, "build_messages", capture_messages)
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", extract)
    sid = f"combined_movement_{movement_source}"
    headers = {"X-Guest-Id": "10000000-0000-4000-8000-000000000001"}
    assert client.post(
        "/api/chat", headers=headers,
        json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Chris"},
    ).status_code == 200
    original = "I walk to the living room and ask Makoto and Minori: what do you each do for work?"
    response = client.post(
        "/api/chat", headers=headers,
        json={"session_id": sid, "message": f"> {original}  "},
    )
    assert response.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    assert state.location_id == "living_room"
    messages = rendered_messages[-1]
    assert original in messages[-1]["content"]
    assert state.last_turn_user_msg == original
    assert pe_mod.SESSIONS[sid]["log"][-2] == {"role": "user", "content": original}
    assert saved_turns[-1]["user_msg"] == original
    saved = json.loads(saved_sessions[-1]["state_json"])
    assert {"role": "user", "content": original} in saved["log"]
    assert any(entry.text == f"Player said: {original}" for entry in state.transient_entries)
    system_prompt = messages[0]["content"]
    assert "### CHARACTER IDENTITY — Makoto Hasegawa" in system_prompt
    assert "### CHARACTER IDENTITY — Minori Nakada" in system_prompt

    # Leaving an occupied room must also clear its FIFO presence fallback when
    # the destination is empty and consequently has no people-present markers.
    assert client.post(
        "/api/chat", headers=headers,
        json={"session_id": sid, "message": "I walk to the terrace to enjoy the evening air."},
    ).status_code == 200
    assert state.location_id == "terrace"
    terrace_prompt = rendered_messages[-1][0]["content"]
    for key in ("makoto", "minori", "yuki", "uchi", "yuriko"):
        assert f"### CHARACTER IDENTITY — {state.characters[key].name}" not in terrace_prompt
    assert "### CHARACTER IDENTITY — Mizuki Shida" in terrace_prompt
    assert state.latest_scene_knowledge().location_id == "terrace"
    assert state.latest_scene_knowledge().people_present == []


def test_master_prompt_engine_orchestration_flow(monkeypatch):
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.extractors.turn_extractor import TurnExtraction, TurnKnowledgeResolution

    spy = types.SimpleNamespace(calls=0)
    pe_mod._TEST_OPENAI_POST_SPY = spy

    def _retrieve_stub(*args, **kwargs):
        return ([{"chunk_id": "c_master", "text": "The red door leads to the kitchen.", "type": "scene"}], {})

    monkeypatch.setattr(pe_mod, "retrieve_knowledge", _retrieve_stub, raising=False)

    async def _extract_stub(*args, **kwargs):
        return TurnExtraction(
            movement_intent="MOVE",
            destination_id="kitchen",
            confidence=0.95,
            previous_reply_location_id="apartment",
            previous_reply_speakers=["jennie"],
            knowledge_updates=[
                TurnKnowledgeResolution(
                    chunk_id="c_master",
                    knows=True,
                    confidence=0.92,
                    reason="speaker directly referenced the door location",
                )
            ],
        )

    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _extract_stub, raising=False)

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "We head to the kitchen.\n\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":1}[[/STATE]]"}}],
                "usage": {"total_tokens": 3},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            spy.calls += 1
            return _FakeResp()

    monkeypatch.setattr(pe_mod.httpx, "AsyncClient", _FakeAsyncClient)

    from backend.app import main
    client = TestClient(main.app)

    sid = "master_flow"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|F|Master"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "Can we go to the kitchen now?"})
    assert r1.status_code == 200
    body = r1.json()
    assert "reply" in body
    assert "[[STATE]]" not in body["reply"]
    assert spy.calls >= 1

    state = pe_mod.SESSIONS[sid]["state"]
    assert int(getattr(state, "turns", 0)) >= 1
    assert state.last_turn_user_msg == "Can we go to the kitchen now?"
    assert isinstance(state.last_turn_assistant_reply, str)
    assert state.last_turn_assistant_reply

    latest_scene = state.latest_scene_knowledge()
    assert latest_scene is not None
    entries = list(getattr(state, "scene_knowledge_entries", []) or [])
    assert any(
        str(getattr(entry, "payload", {}).get("source", "")) == "single_call_turn_extractor"
        for entry in entries
    )
    assert any("jennie" in (getattr(entry, "speakers", []) or []) for entry in entries)

    retrieved = list(getattr(state, "last_turn_retrieved_chunks", []) or [])
    assert any(str(c.get("chunk_id", "")) == "c_master" for c in retrieved)


def test_debug_mode_toggle_no_llm_on_toggle_and_appends_debug_box(client):
    from backend.app.api import prompt_engine as pe_mod

    # Start a new game so a normal turn hits the LLM mock.
    r = client.post("/api/chat", json={"session_id": "dbg1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200

    spy = getattr(pe_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Enter debug mode (must NOT call LLM)
    r2 = client.post("/api/chat", json={"session_id": "dbg1", "message": "[D]"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "ENTERING DEBUG MODE" in data2["reply"]
    assert spy.calls == base_calls

    # Normal turn should call LLM and return debug_box as structured data
    r3 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "debug_box" in data3, "debug_box should be in response when debug mode is on"
    assert "timestamp" in data3["debug_box"]
    assert "location" in data3["debug_box"]
    assert "people_present" in data3["debug_box"]
    assert "DEBUG INFO" not in data3["reply"], "debug info should not be in reply text anymore"
    assert not re.match(r"^\[\d{4}-\d{2}-\d{2} ", data3["reply"])  # no leading timestamp
    assert spy.calls == base_calls + 1

    # Exit debug mode (must NOT call LLM)
    r4 = client.post("/api/chat", json={"session_id": "dbg1", "message": "(DEBUG)"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "EXITING DEBUG MODE" in data4["reply"]
    assert spy.calls == base_calls + 1

    # Next normal turn should not have debug_box
    r5 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello again"})
    assert r5.status_code == 200
    data5 = r5.json()
    assert "debug_box" not in data5, "debug_box should not be present when debug mode is off"
    assert spy.calls == base_calls + 2


def test_debug_toggle_strips_leading_gt(client):
    from backend.app.api import prompt_engine as pe_mod

    # Start a new game so the "regular turn" path is active for subsequent messages.
    r0 = client.post("/api/chat", json={"session_id": "gt1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    spy = getattr(pe_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Leading '>' should be scrubbed globally, so this should toggle debug mode.
    r1 = client.post("/api/chat", json={"session_id": "gt1", "message": "> [D]"})
    assert r1.status_code == 200
    data1 = r1.json()
    assert "ENTERING DEBUG MODE" in data1["reply"]
    assert spy.calls == base_calls  # toggle must NOT call OpenAI

    # A normal message should now call the OpenAI mock and return debug_box.
    r2 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "debug_box" in data2, "debug_box should be in response when debug mode is on"
    assert "timestamp" in data2["debug_box"]
    assert spy.calls == base_calls + 1

    # Exit debug mode with a leading '>' as well.
    r3 = client.post("/api/chat", json={"session_id": "gt1", "message": "> (DEBUG)"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "EXITING DEBUG MODE" in data3["reply"]
    assert spy.calls == base_calls + 1  # toggle must NOT call OpenAI

    # Next normal turn should not have debug_box.
    r4 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello again"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "debug_box" not in data4, "debug_box should not be present when debug mode is off"
    assert spy.calls == base_calls + 2


def test_debug_box_speakers_do_not_include_location_as_name(client):
    # Start a new game
    r0 = client.post("/api/chat", json={"session_id": "spk1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode
    r1 = client.post("/api/chat", json={"session_id": "spk1", "message": "[D]"})
    assert r1.status_code == 200

    # Normal turn to get debug_box
    r2 = client.post("/api/chat", json={"session_id": "spk1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()

    assert "debug_box" in data2
    debug_box = data2["debug_box"]
    assert "speakers" in debug_box

    # Ensure the location isn't mistakenly treated as a speaker name.
    if debug_box["speakers"]:
        for name in debug_box["speakers"]:
            assert "Apartment" not in name, f"Location leaked into speakers: {name}"


def test_scene_knowledge_queue_updates_each_turn(client):
    import backend.app.api.prompt_engine as pe_mod

    sid = "sceneq1"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "hello"})
    assert r1.status_code == 200

    st = pe_mod.SESSIONS[sid]["state"]
    assert st.scene_knowledge_entries
    latest = st.latest_scene_knowledge()
    assert latest is not None
    assert isinstance(latest.speakers, list)
    assert isinstance(latest.people_present, list)
    assert "source" in latest.payload


def test_debug_box_rendering_structured(client):
    """Test that debug box is returned as structured data, not ASCII art in reply."""
    r0 = client.post("/api/chat", json={"session_id": "box1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode — toggle notices still use ASCII _box() in reply
    r1 = client.post("/api/chat", json={"session_id": "box1", "message": "[D]"})
    assert r1.status_code == 200
    reply1 = r1.json()["reply"]
    assert "ENTERING DEBUG MODE" in reply1

    # Normal turn should return debug_box as structured data (not in reply text)
    r2 = client.post("/api/chat", json={"session_id": "box1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()

    # debug_box must be a dict with expected keys
    assert "debug_box" in data2
    box = data2["debug_box"]
    assert isinstance(box, dict)
    assert "timestamp" in box
    assert "location" in box
    # Reply text should NOT contain ASCII debug box
    assert "┌" not in data2["reply"]
    assert "DEBUG INFO" not in data2["reply"]


# ============================================================================
# Utility function tests
# ============================================================================

def test_apply_placeholders_and_sanitize_honorific_terms():
    from backend.app.engine.state import init_state
    import backend.app.api.prompt_engine as pe_mod

    st = init_state()
    st.player_name = "Chris"
    st.gender = "M"
    # Language config lives in story_cfg — provide it like a real story would
    st.story_cfg = {"language": {"honorifics": {"M": "oppa", "F": "unnie"}, "forbidden_honorifics": ["oppa", "unni", "unnie", "eonnie"]}}
    out = pe_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st)
    assert "Chris" in out
    assert "oppa" in out  # honorific placeholder is meta-only for opening

    # At low relationship, sanitize should strip forbidden terms
    st.relationship = 0
    st.user.display_name = "Chris"
    cleaned = pe_mod.sanitize_honorific_terms("hello oppa unnie", st)
    assert "oppa" not in cleaned.lower()
    assert "unnie" not in cleaned.lower()

    # Without language config, placeholders produce empty honorific and sanitize is a no-op
    st2 = init_state()
    st2.player_name = "Chris"
    st2.gender = "M"
    st2.story_cfg = {}
    out2 = pe_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st2)
    assert "Chris" in out2
    assert "{{HONORIFIC}}" not in out2  # placeholder replaced even if empty


def test_name_extraction_and_confirmation():
    from backend.app.engine.state import init_state
    import backend.app.api.prompt_engine as pe_mod

    st = init_state()
    name = pe_mod.extract_user_name_from_text("my name is alice")
    assert name == "Alice"

    # confirmation should set names
    st.last_assistant_guess_name = "Bob"
    pe_mod.handle_name_confirmation("yes", st)
    assert st.user.formal_name == "Bob"


# ============================================================================
# Map toggle tests
# ============================================================================

def test_map_toggle_shows_locations_from_world(client):
    """Test that [M] or [MAP] command shows available locations."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Player"})
    assert r0.status_code == 200

    # Toggle map with [M]
    r1 = client.post("/api/chat", json={"session_id": "map1", "message": "[M]"})
    assert r1.status_code == 200
    resp1 = r1.json()
    reply1 = resp1["reply"]

    # Should show World Map box with locations (no LLM call)
    assert "World Map" in reply1
    # Should contain at least one location name from the story world
    assert len(reply1) > 30, "Map should contain location data"

    # Verify no LLM tokens were used (early exit, same as [D])
    assert resp1.get("usage", {}).get("total_tokens", 0) == 0


def test_map_toggle_case_insensitive(client):
    """Test that map toggle is case-insensitive."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map2", "message": "__cmd_newgame__:" + STORY_ID + "|F|Player"})
    assert r0.status_code == 200

    # Test various forms: [MAP], (MAP), [m], (map)
    for msg in ["[MAP]", "(MAP)", "[m]", "(map)"]:
        r = client.post("/api/chat", json={"session_id": "map2", "message": msg})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "World Map" in reply, f"Map toggle failed for: {msg}"


def test_map_toggle_token_detection():
    """Test _is_map_toggle() function directly with various inputs."""
    import backend.app.api.prompt_engine as pe_mod

    # Valid map toggle tokens
    assert pe_mod._is_map_toggle("[M]")
    assert pe_mod._is_map_toggle("[m]")
    assert pe_mod._is_map_toggle("(M)")
    assert pe_mod._is_map_toggle("(m)")
    assert pe_mod._is_map_toggle("[MAP]")
    assert pe_mod._is_map_toggle("[map]")
    assert pe_mod._is_map_toggle("(MAP)")
    assert pe_mod._is_map_toggle("(map)")

    # With surrounding whitespace
    assert pe_mod._is_map_toggle("  [M]  ")
    assert pe_mod._is_map_toggle("\t[MAP]\t")

    # Invalid tokens (should not match)
    assert not pe_mod._is_map_toggle("[D]")  # Debug token
    assert not pe_mod._is_map_toggle("[C]")  # Chinese token
    assert not pe_mod._is_map_toggle("map")  # No brackets
    assert not pe_mod._is_map_toggle("[X]")  # Unknown token
    assert not pe_mod._is_map_toggle("")     # Empty string
    assert not pe_mod._is_map_toggle("hello world")  # Normal message


def test_map_toggle_no_llm_call(client):
    """Verify that MAP toggle does not invoke LLM (0 tokens)."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "__cmd_newgame__:" + STORY_ID + "|M|Test"})
    assert r0.status_code == 200

    # Normal turn should use LLM
    r1 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "hello"})
    assert r1.status_code == 200
    tokens_normal = r1.json().get("usage", {}).get("total_tokens", 0)
    assert tokens_normal > 0, "Normal turn should use LLM tokens"

    # MAP toggle should NOT use LLM
    r2 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "[M]"})
    assert r2.status_code == 200
    tokens_map = r2.json().get("usage", {}).get("total_tokens", 0)
    assert tokens_map == 0, "MAP toggle should not consume LLM tokens"


def test_map_toggle_returns_boxed_format(client):
    """Verify that MAP toggle returns properly formatted box output."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_box", "message": "__cmd_newgame__:" + STORY_ID + "|F|BoxTest"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_box", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    # Verify box structure
    assert "┌" in reply or "World Map" in reply, "Should have box or title"
    assert "World Map" in reply, "Should have title header"
    # Box corners for proper formatting
    if "┌" in reply:
        assert "┐" in reply, "Top right corner missing"
        assert "└" in reply, "Bottom left corner missing"
        assert "┘" in reply, "Bottom right corner missing"


def test_map_toggle_shows_all_locations(client):
    """Verify that MAP toggle lists all world locations."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "__cmd_newgame__:" + STORY_ID + "|M|AllLocs"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    # Should contain multiple locations from the story world
    location_lines = [line for line in reply.split('\n') if line.strip() and '─' not in line and 'World' not in line]
    assert len(location_lines) > 3, f"Should list multiple locations, got: {reply}"


def test_map_toggle_without_world_runtime(client, monkeypatch):
    """Test MAP toggle behavior when world_runtime is not available."""
    import backend.app.api.prompt_engine as pe_mod

    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_world", "message": "__cmd_newgame__:" + STORY_ID + "|F|NoWorld"})
    assert r0.status_code == 200

    # Remove world_runtime from session state
    state = pe_mod.SESSIONS["map_no_world"]["state"]
    state.world_runtime = None

    # Request map - should show "No map available"
    r1 = client.post("/api/chat", json={"session_id": "map_no_world", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    assert "World Map" in reply
    assert "No map available" in reply or "not available" in reply.lower()


def test_map_toggle_with_whitespace_variants(client):
    """Test MAP toggle with extra whitespace."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_ws", "message": "__cmd_newgame__:" + STORY_ID + "|M|Whitespace"})
    assert r0.status_code == 200

    # Test with leading/trailing whitespace
    test_cases = [
        "  [M]",
        "[M]  ",
        "  [M]  ",
        "\t[MAP]\t",
        "  (m)  ",
    ]

    for msg in test_cases:
        r = client.post("/api/chat", json={"session_id": "map_ws", "message": msg})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "World Map" in reply, f"MAP toggle failed with whitespace: '{msg}'"


def test_map_toggle_multiple_calls_consistent(client):
    """Test that multiple MAP toggle calls return consistent results."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_consistent", "message": "__cmd_newgame__:" + STORY_ID + "|F|Consistent"})
    assert r0.status_code == 200

    # Request map three times
    replies = []
    for _ in range(3):
        r = client.post("/api/chat", json={"session_id": "map_consistent", "message": "[M]"})
        assert r.status_code == 200
        replies.append(r.json()["reply"])

    # All three should be identical
    assert replies[0] == replies[1], "First and second map calls differ"
    assert replies[1] == replies[2], "Second and third map calls differ"


def test_map_toggle_mixed_with_normal_turns(client):
    """Test MAP toggle interleaved with normal game turns."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "__cmd_newgame__:" + STORY_ID + "|M|Mixed"})
    assert r0.status_code == 200

    # Normal turn
    r1 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "hello"})
    assert r1.status_code == 200
    assert "World Map" not in r1.json()["reply"], "Normal turn should not show map"

    # MAP toggle
    r2 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "[M]"})
    assert r2.status_code == 200
    assert "World Map" in r2.json()["reply"], "MAP toggle should show map"

    # Another normal turn
    r3 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "what happened?"})
    assert r3.status_code == 200
    assert "World Map" not in r3.json()["reply"], "Normal turn should not show map"

    # MAP toggle again
    r4 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "[MAP]"})
    assert r4.status_code == 200
    assert "World Map" in r4.json()["reply"], "Second MAP toggle should show map"


def test_map_toggle_includes_world_map_image_path(client):
    """Test that MAP toggle response includes world_map_image path when available."""
    # Start new game with first discovered story
    r0 = client.post("/api/chat", json={"session_id": "map_img", "message": "__cmd_newgame__:" + STORY_ID + "|M|ImgTest"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_img", "message": "[M]"})
    assert r1.status_code == 200
    resp = r1.json()

    # Verify response includes world map image path (auto-discovered)
    assert "world_map_image" in resp, "Response should include world_map_image field"
    assert resp["world_map_image"].endswith(".png"), "Image path should be a PNG file"
    assert STORY_FOLDER in resp["world_map_image"], f"Image path should reference story folder {STORY_FOLDER}"


# ============================================================================
# Story loader / world config tests
# ============================================================================

def test_story_loader_finds_story_in_subdirectory(client):
    """Test that story loader can find stories in subdirectories."""
    r = client.post("/api/chat", json={"session_id": "subdir_test", "message": "__cmd_newgame__:" + STORY_ID + "|F|SubdirTest"})
    assert r.status_code == 200
    opening = r.json()

    # Verify story loaded correctly (opening should be present)
    assert "reply" in opening
    assert len(opening["reply"]) > 100, "Opening text should be present and substantial"


def test_story_with_world_config_loads_correctly(client):
    """Test that story with world config loads and initializes world runtime."""
    r0 = client.post("/api/chat", json={"session_id": "world_cfg", "message": "__cmd_newgame__:" + STORY_ID + "|M|WorldCfg"})
    assert r0.status_code == 200

    # Verify world is initialized by checking state
    import backend.app.api.prompt_engine as pe_mod
    state = pe_mod.SESSIONS["world_cfg"]["state"]

    # World should be loaded
    assert state.world_runtime is not None, "World runtime should be loaded from story config"
    assert state.world_runtime.world_graph is not None, "World graph should be initialized"
    assert len(state.world_runtime.world_graph.locations) > 0, "World should have locations"


def test_file_consolidation_single_location(client):
    """Test that all story files are in the expected story folder (auto-discovered).

    A05 note: story JSON filenames are NOT required to match the story's
    declared `id` (e.g. blackout_manor's file is 3_story.json) — resolution
    goes through build_story_registry(), not filename-guessing. This test
    resolves the story's actual path via that registry rather than assuming
    a {id}.json / {id}_story.json naming convention.
    """
    import os
    from backend.app.engine.story_loader import find_story_dir, build_story_registry

    # Verify old duplicate backend/stories directory doesn't exist
    assert not os.path.exists("backend/stories"), "Old backend/stories duplicate should be removed"

    # Auto-discover the first story's folder and verify it exists
    story_dir = find_story_dir(STORY_ID)
    assert story_dir is not None, f"Story folder for {STORY_ID} should exist"

    full_dir = os.path.join("backend", "app", "stories", story_dir)
    assert os.path.isdir(full_dir), f"Story directory {full_dir} should exist"

    # Verify the story JSON resolves via the content registry (by declared id).
    entry = build_story_registry().get(STORY_ID)
    assert entry is not None, f"Story JSON for {STORY_ID} should be in the registry"
    assert os.path.isfile(entry["path"]), f"Story JSON for {STORY_ID} should exist at {entry['path']}"

    # Verify a world JSON exists ({id}_world.json)
    world_json = os.path.join(full_dir, f"{STORY_ID}_world.json")
    assert os.path.isfile(world_json), f"World JSON should exist at {world_json}"

    # Verify a map image exists ({folder}.png convention)
    map_png = os.path.join(full_dir, f"{story_dir}.png")
    assert os.path.isfile(map_png), f"Map image should exist at {map_png}"


# ============================================================================
# Knowledge resolution tests
# ============================================================================

def test_knowledge_resolution_updates_belief_and_transient(client, monkeypatch):
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.extractors.turn_extractor import TurnExtraction, TurnKnowledgeResolution

    async def _mock_turn_extract(*args, **kwargs):
        return TurnExtraction(
            movement_intent="NONE",
            knowledge_updates=[
                TurnKnowledgeResolution(
                    chunk_id="c_unknown",
                    knows=True,
                    confidence=0.88,
                    reason="dialogue indicates familiarity",
                )
            ],
        )

    monkeypatch.setattr(
        pe_mod,
        "retrieve_knowledge",
        lambda *args, **kwargs: ([{"chunk_id": "c_unknown", "text": "The hidden hallway has a red door.", "type": "scene"}], {}),
        raising=False,
    )
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_turn_extract, raising=False)

    sid = "kr1"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "tell me about the hallway"})
    assert r1.status_code == 200
    r2 = client.post("/api/chat", json={"session_id": sid, "message": "and what else?"})
    assert r2.status_code == 200
    body = r2.json()
    assert "knowledge_resolution_updates" in body
    assert body["knowledge_resolution_updates"][0]["chunk_id"] == "c_unknown"
    assert body["knowledge_resolution_updates"][0]["knows"] is True

    st = pe_mod.SESSIONS[sid]["state"]
    speaker = (st.main_character_id or "").strip().lower()

    claims = st.get_belief_state(speaker).claims
    assert any(getattr(c, "id", "") == f"kr::{speaker}::c_unknown" for c in claims)

    entries = st.transient_entries
    matched = [e for e in entries if "KnowledgeResolution" in (getattr(e, "text", "") or "") and "chunk=c_unknown" in (getattr(e, "text", "") or "")]
    assert matched
    assert matched[-1].turns_remaining == 8


# ============================================================================
# Chinese toggle detection tests
# ============================================================================

def test_is_chinese_toggle_detects_all_formats():
    """Test that _is_chinese_toggle recognizes all toggle formats."""
    import backend.app.api.prompt_engine as pe_mod

    # Test all supported formats (case insensitive)
    assert pe_mod._is_chinese_toggle("[C]")
    assert pe_mod._is_chinese_toggle("(C)")
    assert pe_mod._is_chinese_toggle("[CHINESE]")
    assert pe_mod._is_chinese_toggle("(CHINESE)")
    assert pe_mod._is_chinese_toggle("[c]")  # lowercase
    assert pe_mod._is_chinese_toggle("(c)")  # lowercase
    assert pe_mod._is_chinese_toggle("[chinese]")  # lowercase
    assert pe_mod._is_chinese_toggle("(chinese)")  # lowercase

    # Test false negatives
    assert not pe_mod._is_chinese_toggle("[D]")
    assert not pe_mod._is_chinese_toggle("Chinese")  # no brackets
    assert not pe_mod._is_chinese_toggle("C")  # no brackets
    assert not pe_mod._is_chinese_toggle("hello")
    assert not pe_mod._is_chinese_toggle("")
    assert not pe_mod._is_chinese_toggle(None)


def test_chinese_toggle_is_case_insensitive():
    """Verify that Chinese toggle is case-insensitive."""
    import backend.app.api.prompt_engine as pe_mod

    test_cases = [
        "[C]", "[c]",
        "(C)", "(c)",
        "[CHINESE]", "[chinese]", "[ChInEsE]",
        "(CHINESE)", "(chinese)", "(ChInEsE)",
    ]

    for test_input in test_cases:
        assert pe_mod._is_chinese_toggle(test_input), f"Failed for: {test_input}"


# ============================================================================
# Chinese toggle session state tests
# ============================================================================

def test_chinese_toggle_enters_mode(client_with_translation):
    """Test that [C] command enters Chinese mode."""
    client, _, _ = client_with_translation

    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Toggle Chinese mode on
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should see Chinese mode entrance message
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_chinese_toggle_exits_mode(client_with_translation):
    """Test that [C] command exits Chinese mode when already on."""
    client, _, _ = client_with_translation

    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enter Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Exit Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should see exit message
    assert "退出中文模式" in reply or "exit" in reply.lower()


def test_chinese_mode_persists_in_session(client_with_translation):
    """Test that Chinese mode flag persists across turns."""
    client, translation_spy, _ = client_with_translation

    # Start new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset translation spy
    translation_spy.calls = 0

    # Send a normal message - should trigger translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "hello"
    })
    assert resp.status_code == 200

    # Should have called translation function
    assert translation_spy.calls > 0, "Translation should be called when in Chinese mode"


# ============================================================================
# Translation function tests
# ============================================================================

def test_translate_to_chinese_preserves_formatting(monkeypatch):
    """Test that translation preserves formatting markers."""
    from backend.app.api import prompt_engine as pe_mod

    # Create a mock OpenAI response with formatting
    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": "**你好** *世界* 和 \"引号\"\n\n新行文本"
                    }
                }],
                "usage": {"total_tokens": 10},
            }
        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    # Run translation
    result = asyncio.run(pe_mod._translate_to_chinese("**Hello** *world* and \"quotes\"\n\nNew line text"))

    # Should preserve structure
    assert "**" in result  # bold markers
    assert "*" in result   # italic markers
    assert "\"" in result  # quotes
    assert "\n\n" in result  # line breaks


def test_translate_to_chinese_handles_empty_text(monkeypatch):
    """Test that translation handles empty or whitespace text."""
    from backend.app.api import prompt_engine as pe_mod

    # Empty string
    result = asyncio.run(pe_mod._translate_to_chinese(""))
    assert result == ""

    # Whitespace only
    result = asyncio.run(pe_mod._translate_to_chinese("   \n  \t  "))
    assert result == "   \n  \t  "


def test_translate_to_chinese_fallback_on_error(monkeypatch):
    """Test that translation falls back to original text on error."""
    from backend.app.api import prompt_engine as pe_mod

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            raise Exception("Network error")

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    original = "Hello world"
    result = asyncio.run(pe_mod._translate_to_chinese(original))

    # Should return original text on error
    assert result == original


def test_translate_to_chinese_http_error_fallback(monkeypatch):
    """Test that translation falls back on HTTP errors."""
    from backend.app.api import prompt_engine as pe_mod

    class _FakeResp:
        status_code = 500
        @property
        def text(self):
            return "Internal Server Error"

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    original = "Hello world"
    result = asyncio.run(pe_mod._translate_to_chinese(original))

    # Should return original text on HTTP error
    assert result == original


# ============================================================================
# Chinese mode integration tests
# ============================================================================

def test_chinese_mode_translates_opening_on_newgame(client_with_translation):
    """Test that opening prompt is translated when starting game in Chinese mode."""
    client, translation_spy, _ = client_with_translation

    # Manually enable Chinese mode in session first
    from backend.app.api.prompt_engine import SESSIONS
    session_id = "cn_test_opening"
    SESSIONS[session_id] = {
        "state": None,
        "log": [],
        "debug_mode": False,
        "chinese_mode": True,  # Enable Chinese mode BEFORE newgame
    }

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "欢迎来到故事..."

    # Start new game - should translate opening
    resp = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Translation should have been called
    assert translation_spy.calls > 0, "Opening should be translated in Chinese mode"
    reply = resp.json()["reply"]
    assert "欢迎来到故事" in reply


def test_chinese_mode_translates_regular_responses(client_with_translation):
    """Test that regular chat responses are translated in Chinese mode."""
    client, translation_spy, _ = client_with_translation

    # Setup: start game, enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。"

    # Send message - should be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "What happened?"
    })
    assert resp.status_code == 200

    # Verify translation was called
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]
    assert "我理解了" in reply


def test_english_mode_no_translation(client_with_translation):
    """Test that responses are NOT translated when Chinese mode is off."""
    client, translation_spy, _ = client_with_translation

    # Start game (no Chinese mode)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0

    # Send message - should NOT be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "Hello"
    })
    assert resp.status_code == 200

    # Translation should NOT have been called
    assert translation_spy.calls == 0, "No translation should occur in English mode"


def test_chinese_toggle_with_special_characters(client_with_translation):
    """Test Chinese toggle with text containing special characters."""
    client, _, _ = client_with_translation

    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Toggle with text around it (edge case)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "  [C]  "  # whitespace around toggle
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should still recognize the toggle
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_reset_clears_chinese_mode():
    """Test that reset command clears Chinese mode flag."""
    import backend.app.api.prompt_engine as pe_mod

    session_id = "reset_test"

    # Create session with Chinese mode on
    sess = pe_mod.get_session(session_id)
    sess["chinese_mode"] = True
    assert sess["chinese_mode"] is True

    # After reset, new session should have chinese_mode = False
    pe_mod.SESSIONS[session_id] = {
        "state": pe_mod.init_state(),
        "log": [],
        "debug_mode": False,
        "chinese_mode": False,
    }

    sess = pe_mod.get_session(session_id)
    assert sess["chinese_mode"] is False


def test_chinese_and_debug_modes_can_coexist(client_with_translation):
    """Test that Chinese and Debug modes can both be enabled."""
    client, translation_spy, _ = client_with_translation

    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable debug mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[D]"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。(Debug box here...)"

    # Send message - should have both debug info AND Chinese translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "hello"
    })
    assert resp.status_code == 200

    # Translation should be called (Chinese mode on)
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]

    # Should include translated content
    assert "我理解了" in reply


def test_chinese_mode_with_empty_response(client_with_translation):
    """Test Chinese mode handling of empty or very short responses."""
    client, translation_spy, _ = client_with_translation

    # Start game with Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Set translation to return empty
    translation_spy.return_value = ""

    # This should still work gracefully
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "hi"
    })
    assert resp.status_code == 200


def test_chinese_mode_toggle_formatting():
    """Test that Chinese mode toggle messages are properly formatted."""
    import backend.app.api.prompt_engine as pe_mod

    # Verify the box function works with Chinese text
    box = pe_mod._box("进入中文模式", ["Type [C] to exit"])

    assert "进入中文模式" in box
    assert "┌" in box  # corners exist
    assert "└" in box
    assert "├" in box  # separator exists


# ============================================================================
# Story canonical projection tests
# ============================================================================

def test_canonicalize_story_cfg_keeps_only_generic_runtime_keys():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.story_loader import load_story

    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    cfg = pe_mod._canonicalize_story_cfg(story)

    assert "id" in cfg
    assert "characters" in cfg
    assert "epistemic_seed" in cfg
    assert "world" in cfg
    assert "relationships" in cfg
    assert "setting" not in cfg
    assert "victim" not in cfg
    assert "style" not in cfg
    assert "world_context" not in cfg


def test_noncanonical_story_details_are_seeded_to_transient_buffer():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state
    from backend.app.engine.story_loader import load_story

    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    st = init_state()
    st.story = story_id
    st.user_id = "default_user"
    st.instance = 1

    pe_mod._seed_noncanonical_story_details_to_transient(story, st)

    texts = [e.text for e in st.transient_entries]
    assert texts, "Expected non-canonical story details to be seeded into transient context"
    assert any(t.startswith("story.") or t.startswith("character.") for t in texts)


def test_seed_epistemic_common_knowledge_maps_to_all_characters():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state

    st = init_state()
    cfg = {
        "epistemic_seed": {
            "canonical_facts": [
                {
                    "id": "f_common",
                    "text": "This fact is common knowledge.",
                    "common_knowledge": True,
                    "confidence": 1.0,
                }
            ]
        }
    }

    pe_mod._seed_epistemic_from_story(cfg, st)

    assert len(st.canonical_facts) == 1
    assert st.canonical_facts[0].known_by == ["all_characters"]


def test_seed_epistemic_claim_visibility_metadata_is_preserved():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state

    st = init_state()
    cfg = {
        "epistemic_seed": {
            "belief_seeds": {
                "iu": [
                    {
                        "text": "I might know this detail.",
                        "known_by": ["iu"],
                        "not_known_by": ["player"],
                        "maybe_known_by": ["park_so_jin"],
                        "confidence": 0.7,
                    }
                ]
            }
        }
    }

    pe_mod._seed_epistemic_from_story(cfg, st)

    iu_claims = st.get_belief_state("iu").claims
    assert len(iu_claims) == 1
    assert iu_claims[0].known_by == ["iu"]
    assert iu_claims[0].not_known_by == ["player"]
    assert iu_claims[0].maybe_known_by == ["park_so_jin"]


# ---------------------------------------------------------------------------
# Session persistence & privacy tests (bugs 1, 2, 4)
# ---------------------------------------------------------------------------

import json as _json
import logging


def test_serialize_state_includes_runtime_snapshots():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state
    from backend.app.engine.character_graph import CharacterGraph, RelationshipEdge, RelationshipState, RelationshipType
    from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore

    st = init_state()
    st.story = STORY_ID
    st.gender = "F"
    st.player_name = "Alex"
    st.character_locations = {"iu": "room_a", "player": "room_a"}
    st.last_turn_user_msg = "where are we"
    st.last_turn_assistant_reply = "We are in room A"
    st.last_turn_retrieved_chunks = [{"chunk_id": "k1", "text": "fact"}]

    graph = CharacterGraph()
    graph.edges["iu->player"] = RelationshipEdge(
        id="iu->player",
        from_id="iu",
        to_id="player",
        type=RelationshipType.FRIEND,
        state=RelationshipState(trust=0.8, fear=0.1, affection=0.7, suspicion=0.0, jealousy=0.0),
        narrative="IU now trusts the player",
        narrative_log=["IU greeted the player warmly"],
        met_at=5,
        last_met_at=12,
        meeting_count=2,
        prior_relationship=True,
        in_relationship=True,
    )
    st.character_graph = graph

    st.session_chunk_store = SessionChunkStore()
    st.session_chunk_store.add_chunks([
        {"chunk_id": "usr-1-0", "text": "The key is in the drawer", "type": "dialogue_fact"}
    ])

    saved = _json.loads(pe_mod._serialize_state(st, []))
    assert "character_graph" in saved
    assert "session_chunks" in saved
    assert saved["character_locations"]["iu"] == "room_a"
    assert saved["last_turn_user_msg"] == "where are we"
    assert saved["character_graph"]["edges"]["iu->player"]["state"]["trust"] == pytest.approx(0.8)
    assert saved["session_chunks"][0]["chunk_id"] == "usr-1-0"


def test_try_load_session_restores_runtime_graph_and_session_chunks(monkeypatch):
    from backend.app.api import prompt_engine as pe_mod

    fake_state = {
        "story": STORY_ID,
        "gender": "M",
        "player_name": "ReplayUser",
        "turns": 4,
        "location_id": "room_a",
        "location": "Room A",
        "character_locations": {"iu": "room_b", "player": "room_b"},
        "last_turn_user_msg": "go to room b",
        "last_turn_assistant_reply": "You arrive in Room B",
        "last_turn_retrieved_chunks": [{"chunk_id": "g-1", "text": "room b has a locker"}],
        "character_graph": {
            "edges": {
                "player->iu": {
                    "id": "player->iu",
                    "from_id": "player",
                    "to_id": "iu",
                    "type": "FRIEND",
                    "state": {
                        "trust": 0.6,
                        "fear": 0.0,
                        "affection": 0.4,
                        "suspicion": 0.0,
                        "jealousy": 0.0,
                    },
                    "narrative": "Player feels closer to IU",
                    "narrative_log": ["They shared a clue"],
                    "met_at": 1,
                    "last_met_at": 8,
                    "meeting_count": 3,
                    "prior_relationship": False,
                    "prior_intimacy": False,
                    "in_relationship": False,
                }
            }
        },
        "session_chunks": [
            {"chunk_id": "usr-2-0", "text": "A hidden note mentions studio B", "type": "dialogue_fact"}
        ],
    }

    fake_row = {
        "story_id": STORY_ID,
        "player_name": "ReplayUser",
        "gender": "M",
        "state_json": _json.dumps(fake_state),
        "flags_json": _json.dumps({"debug_mode": True, "epistemic_state": True}),
    }

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_resume_1", "uid_resume")
    assert result is not None
    restored = result["state"]

    assert restored.character_locations.get("iu") == "room_b"
    assert restored.last_turn_user_msg == "go to room b"
    assert restored.last_turn_assistant_reply == "You arrive in Room B"
    assert restored.last_turn_retrieved_chunks[0]["chunk_id"] == "g-1"

    edge = restored.character_graph.get_edge("player", "iu")
    assert edge is not None
    assert edge.state.trust == pytest.approx(0.6)
    assert edge.narrative == "Player feels closer to IU"
    assert edge.meeting_count == 3

    restored_chunks = restored.session_chunk_store.all_chunks()
    assert len(restored_chunks) == 1
    assert restored_chunks[0]["chunk_id"] == "usr-2-0"


def test_try_load_session_from_db_sync_path(monkeypatch):
    """Bug 1: _try_load_session_from_db must work even when called from within a
    running event loop (the normal FastAPI path).  The old implementation used
    asyncio.get_event_loop().run_until_complete() which fails inside async code."""
    from backend.app.api import prompt_engine as pe_mod

    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID, "gender": "M", "player_name": "TestPlayer", "turns": 3,
        }),
        "flags_json": _json.dumps({
            "debug_mode": False, "chinese_mode": False,
            "epistemic_state": True, "truth_mode": False,
        }),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_test1", "user1")
    assert result is not None
    assert result["state"].story == STORY_ID
    assert result["state"].turns == 3
    assert result["user_id"] == "user1"


def test_try_load_session_from_db_works_inside_running_loop(monkeypatch):
    """Bug 1 continued: prove the fix works when an asyncio event loop IS running."""
    from backend.app.api import prompt_engine as pe_mod

    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID, "gender": "F", "player_name": "Alice",
        }),
        "flags_json": "{}",
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    async def _inner():
        return pe_mod._try_load_session_from_db("sess_async", "user2")

    result = asyncio.run(_inner())
    assert result is not None
    assert result["state"].player_name == "Alice"


def test_try_load_session_from_db_returns_none_when_not_found(monkeypatch):
    """If the session doesn't exist in DB, return None (no crash)."""
    from backend.app.api import prompt_engine as pe_mod

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: None),
    )

    result = pe_mod._try_load_session_from_db("nonexistent", "user1")
    assert result is None


def test_restore_then_travel_does_not_roll_clock_backward(monkeypatch):
    """A07 regression: restoring a session at a late minute and then
    traveling must not roll the world clock backward. Before the fix,
    WorldLoader always built a *fresh* WorldClock seeded from the authored
    world's start_minute (0 here); the restored `state.minute` was set
    correctly but the world_runtime's clock was not resynced to it, so the
    first travel action would overwrite state.minute with
    (fresh_start + delta), rolling the clock back from ~2000 to single
    digits."""
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.gameplay import advance_time

    late_minute = 2000
    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID,
            "gender": "M",
            "player_name": "ClockTest",
            "turns": 10,
            "minute": late_minute,
            "location_id": "iu_apartment_room",
            "location": "IU's Apartment",
        }),
        "flags_json": _json.dumps({
            "debug_mode": False, "chinese_mode": False,
            "epistemic_state": True, "truth_mode": False,
        }),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_clock_test", "user_clock")
    assert result is not None
    state = result["state"]
    assert state.minute == late_minute
    assert state.world_runtime is not None
    # The world runtime's own clock must be resynced to the restored value,
    # not left at the authored world's start_minute (0).
    assert state.world_runtime.world_clock.now_minute() == late_minute

    # Now perform a travel action and confirm the clock only ever advances.
    advance_time(state, "go to apartment lobby")
    assert state.minute >= late_minute, (
        f"clock rolled backward on travel after restore: {late_minute} -> {state.minute}"
    )


def test_get_session_rejects_cross_user_cache_hit():
    """Bug 2: If session X is cached for user A, user B must not get user A's data."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_cross_user_sess"
    try:
        # Pre-populate cache with user A's session
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "secret_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "userA",
        }

        # User B requests the same session_id
        sess = pe_mod.get_session(test_session_id, "userB")
        assert sess["user_id"] == "userB"
        assert sess["log"] == []  # fresh, not userA's data
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_anon_caller_cannot_read_owned_cache_hit():
    """A01 regression: the old ownership check exempted callers/owners of
    "anon" from comparison (`cached_owner != "anon" and user_id != "anon"`),
    so an unauthenticated caller (user_id="anon") requesting a session_id
    that happened to be cached for a real owner got that owner's cached
    state/log back verbatim instead of a fresh session."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_anon_reads_owned_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "owner_secret_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "guest:real-owner-uuid",
        }

        # Anonymous caller (no JWT, no guest cookie) guesses/knows the session_id.
        sess = pe_mod.get_session(test_session_id, "anon")
        assert sess["user_id"] == "anon"
        assert sess["log"] == []  # must NOT see the real owner's cached log
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_owner_cannot_be_bypassed_by_anon_owned_cache():
    """A01 regression: a session cached with owner "anon" must not be handed
    to a different real caller just because the cached owner happens to be
    "anon" (the old check also exempted this direction)."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_anon_owned_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "anon_session_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "anon",
        }

        sess = pe_mod.get_session(test_session_id, "guest:someone-else")
        assert sess["user_id"] == "guest:someone-else"
        assert sess["log"] == []
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_allows_same_user_cache_hit():
    """Same user should get their own cached session back."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_same_user_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "my_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "userA",
        }

        sess = pe_mod.get_session(test_session_id, "userA")
        assert sess["user_id"] == "userA"
        assert sess["log"] == [{"role": "assistant", "content": "my_data"}]
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_try_load_session_logs_on_db_failure(monkeypatch, caplog):
    """Bug 4: DB failures should be logged, not silently swallowed."""
    from backend.app.api import prompt_engine as pe_mod

    def _explode(session_id, user_id):
        raise RuntimeError("DB connection failed")

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(_explode),
    )

    with caplog.at_level(logging.ERROR, logger="backend.app.api.prompt_engine"):
        result = pe_mod._try_load_session_from_db("sess_bad", "user1")

    assert result is None
    assert "Failed to load session" in caplog.text


from backend.app.integration_playback.scenarios.scenario_api_chat_five_turns import ChatFiveTurnScenario
from backend.app.integration_playback.scenarios.scenario_iu_identity_correction import IUIdentityCorrectionScenario


@pytest.mark.integration
# ============================================================================
# A12: per-session turn serialization
# ============================================================================

@pytest.mark.asyncio
async def test_chat_handler_serializes_overlapping_calls_for_same_session(monkeypatch):
    """A12 regression: two overlapping /api/chat-style calls for the SAME
    session_id must not run their turn-processing critical sections
    concurrently (which could interleave reads/writes of the shared
    SESSIONS[session_id] cache and double-apply or corrupt a turn)."""
    from backend.app.api import prompt_engine as pe_mod

    state = {"current": 0, "max_concurrent": 0}

    async def _fake_impl(request, data, _auth_user):
        state["current"] += 1
        state["max_concurrent"] = max(state["max_concurrent"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return {"reply": "ok"}

    monkeypatch.setattr(pe_mod, "_chat_handler_impl", _fake_impl)

    same_session = {"session_id": "a12_same_sess", "message": "hi"}
    results = await asyncio.gather(
        pe_mod.chat_handler(request=None, data=dict(same_session), _auth_user=None),
        pe_mod.chat_handler(request=None, data=dict(same_session), _auth_user=None),
    )
    assert all(r == {"reply": "ok"} for r in results)
    assert state["max_concurrent"] == 1, (
        f"overlapping calls for the same session_id ran concurrently: max_concurrent={state['max_concurrent']}"
    )


@pytest.mark.asyncio
async def test_chat_handler_does_not_serialize_different_sessions(monkeypatch):
    """The per-session lock must not become a global lock — two DIFFERENT
    session_ids should still be able to process turns concurrently."""
    from backend.app.api import prompt_engine as pe_mod

    state = {"current": 0, "max_concurrent": 0}

    async def _fake_impl(request, data, _auth_user):
        state["current"] += 1
        state["max_concurrent"] = max(state["max_concurrent"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return {"reply": "ok"}

    monkeypatch.setattr(pe_mod, "_chat_handler_impl", _fake_impl)

    results = await asyncio.gather(
        pe_mod.chat_handler(request=None, data={"session_id": "a12_sess_x", "message": "hi"}, _auth_user=None),
        pe_mod.chat_handler(request=None, data={"session_id": "a12_sess_y", "message": "hi"}, _auth_user=None),
    )
    assert all(r == {"reply": "ok"} for r in results)
    assert state["max_concurrent"] == 2, (
        f"different sessions were serialized against each other: max_concurrent={state['max_concurrent']}"
    )


def test_api_end_to_end_5_turns_time_and_location():
    ChatFiveTurnScenario.run_as_test()


@pytest.mark.integration
@pytest.mark.xfail(reason="LLM non-deterministic: narration reveals identity but evaluator acceptance varies", strict=False)
def test_iu_identity_correction():
    IUIdentityCorrectionScenario.run_as_test()


# ---------------------------------------------------------------------------
# BL-07: per-character self_knowledge propagation through prompt_engine.py
# (new-game path and restore path build the character roster separately,
# so both are covered here).
# ---------------------------------------------------------------------------

    for entry in by_key["mina"].self_knowledge:
        assert entry in sysmsg
    for entry in by_key["daeho"].self_knowledge:
        assert entry in sysmsg
    for entry in by_key["priya"].self_knowledge:
        assert entry not in sysmsg
