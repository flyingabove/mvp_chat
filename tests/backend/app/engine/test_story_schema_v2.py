# tests/backend/app/engine/test_story_schema_v2.py
"""Tests for story_schema_v2 — enums, dataclasses, from_dict parsing."""
import pytest

from backend.app.engine.story_schema_v2 import (
    AccessPolicy,
    CanonTier,
    CharacterAnchors,
    CharacterHistory,
    CharacterModel,
    CharacterTraits,
    ChunkType,
    Content,
    EpistemicProfile,
    GameConfig,
    Identity,
    KnowledgeBase,
    KnowledgeChunk,
    LocationModel,
    MemoryRules,
    MemoryTrigger,
    Metadata,
    MotivationModel,
    MovementEdge,
    MovementGraph,
    Objective,
    ObjectiveState,
    ObjectiveType,
    OutputPolicy,
    Provenance,
    RelationshipEdge,
    RelationshipGraph,
    RelationshipState,
    RelationshipType,
    RetrievalIndexSpec,
    StoryPackageV2,
    TimeModel,
    UnlockRules,
    Visibility,
    WinConditions,
    WinRule,
    WorldModel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_v2_dict():
    """Smallest valid v2 package dict."""
    return {
        "story_id": "test_story",
        "version": 2,
        "knowledge": {
            "chunks": {
                "anchor_identity": {
                    "type": "IDENTITY",
                    "canon_tier": "ANCHOR",
                    "access": {"inject_every_turn": True, "speaker_must_not_deny": True},
                    "content": {"text": "You are IU.", "entities": ["IU"]},
                },
                "fact_closet": {
                    "type": "FACT",
                    "canon_tier": "CANON",
                    "content": {"text": "The closet binds you to this apartment."},
                },
                "secret_killer": {
                    "type": "FACT",
                    "canon_tier": "SECRET_CANON",
                    "access": {"visibility": "RESTRICTED", "allowed_character_ids": ["iu"]},
                    "content": {"text": "Manager-nim ordered the killing."},
                },
            },
        },
        "characters": {
            "iu": {
                "identity": {"display_name": "IU", "archetype": "ghost", "tags": ["female"]},
                "anchors": {"anchor_chunk_ids": ["anchor_identity"]},
                "epistemic": {
                    "known_chunk_ids": ["fact_closet"],
                    "believed_chunk_ids": [],
                    "forgotten_chunk_ids": [],
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

def test_canon_tier_values():
    assert CanonTier.ANCHOR.value == "ANCHOR"
    assert CanonTier.SECRET_CANON.value == "SECRET_CANON"


def test_chunk_type_values():
    assert ChunkType.IDENTITY.value == "IDENTITY"
    assert ChunkType.EVIDENCE.value == "EVIDENCE"


def test_visibility_values():
    assert Visibility.ENGINE_ONLY.value == "ENGINE_ONLY"


# ---------------------------------------------------------------------------
# Content / Provenance / UnlockRules
# ---------------------------------------------------------------------------

def test_content_from_dict():
    c = Content.from_dict({"text": "hello", "entities": ["A", "B"]})
    assert c.text == "hello"
    assert c.entities == ["A", "B"]


def test_content_from_dict_none():
    c = Content.from_dict(None)
    assert c.text == ""


def test_provenance_clamps_confidence():
    p = Provenance.from_dict({"confidence": 5.0})
    assert p.confidence == 1.0
    p2 = Provenance.from_dict({"confidence": -2.0})
    assert p2.confidence == 0.0


def test_unlock_rules_from_dict():
    ur = UnlockRules.from_dict({"required_chunk_ids": ["c1"], "min_world_minute": 60})
    assert ur.required_chunk_ids == ["c1"]
    assert ur.min_world_minute == 60


# ---------------------------------------------------------------------------
# AccessPolicy
# ---------------------------------------------------------------------------

def test_access_policy_defaults():
    ap = AccessPolicy.from_dict(None)
    assert ap.visibility == Visibility.PUBLIC
    assert ap.inject_every_turn is False


def test_access_policy_invalid_visibility_falls_back():
    ap = AccessPolicy.from_dict({"visibility": "NONSENSE"})
    assert ap.visibility == Visibility.PUBLIC


# ---------------------------------------------------------------------------
# KnowledgeChunk
# ---------------------------------------------------------------------------

def test_knowledge_chunk_from_dict():
    kc = KnowledgeChunk.from_dict("test_id", {
        "type": "IDENTITY",
        "canon_tier": "ANCHOR",
        "content": {"text": "You are IU."},
        "tags": ["female"],
    })
    assert kc.id == "test_id"
    assert kc.type == ChunkType.IDENTITY
    assert kc.canon_tier == CanonTier.ANCHOR
    assert kc.content.text == "You are IU."


def test_knowledge_chunk_invalid_enum_defaults():
    kc = KnowledgeChunk.from_dict("x", {"type": "INVALID", "canon_tier": "BOGUS"})
    assert kc.type == ChunkType.NOTE
    assert kc.canon_tier == CanonTier.CANON


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

def test_knowledge_base_from_dict():
    kb = KnowledgeBase.from_dict({
        "chunks": {
            "c1": {"type": "FACT", "canon_tier": "CANON", "content": {"text": "A fact."}},
        },
    })
    assert "c1" in kb.chunks
    assert kb.chunks["c1"].content.text == "A fact."


# ---------------------------------------------------------------------------
# Character system
# ---------------------------------------------------------------------------

def test_identity_from_dict():
    i = Identity.from_dict({"display_name": "IU", "archetype": "ghost"})
    assert i.display_name == "IU"
    assert i.archetype == "ghost"


def test_character_traits_from_dict():
    ct = CharacterTraits.from_dict({"tone": "melancholy", "speech_style": "poetic"})
    assert ct.tone == "melancholy"


def test_motivation_model_from_dict():
    mm = MotivationModel.from_dict({"primary": "survive", "fears": ["death", "forgetting"]})
    assert mm.primary == "survive"
    assert mm.fears == ["death", "forgetting"]


def test_memory_trigger_clamps_probability():
    mt = MemoryTrigger.from_dict({"id": "t1", "condition": "mentions:closet", "probability": 1.5})
    assert mt.probability == 1.0


def test_epistemic_profile_from_dict():
    ep = EpistemicProfile.from_dict({
        "known_chunk_ids": ["c1"],
        "forgotten_chunk_ids": ["c2"],
    })
    assert ep.known_chunk_ids == ["c1"]
    assert ep.forgotten_chunk_ids == ["c2"]


def test_character_history_is_mutable():
    """CharacterHistory must not be frozen — experienced_chunk_ids grows at runtime."""
    ch = CharacterHistory.from_dict({"experienced_chunk_ids": ["e1"]})
    ch.experienced_chunk_ids.append("e2")
    assert "e2" in ch.experienced_chunk_ids


def test_character_model_from_dict():
    cm = CharacterModel.from_dict("iu", {
        "identity": {"display_name": "IU"},
        "anchors": {"anchor_chunk_ids": ["a1"]},
    })
    assert cm.id == "iu"
    assert cm.identity.display_name == "IU"
    assert cm.anchors.anchor_chunk_ids == ["a1"]


# ---------------------------------------------------------------------------
# Relationship graph
# ---------------------------------------------------------------------------

def test_relationship_state_clamps():
    rs = RelationshipState(trust=5.0, fear=-1.0, affection=2.0, suspicion=-3.0)
    assert rs.trust == 1.0
    assert rs.fear == 0.0
    assert rs.affection == 1.0
    assert rs.suspicion == 0.0


def test_relationship_state_collapse():
    rs = RelationshipState(trust=0.5, fear=0.1, affection=0.8, suspicion=0.2)
    score = rs.collapse()
    assert -5 <= score <= 5


def test_relationship_state_apply_delta():
    rs = RelationshipState(trust=0.0)
    rs.apply_delta(trust=0.3, fear=0.1)
    assert abs(rs.trust - 0.3) < 0.001
    assert abs(rs.fear - 0.1) < 0.001


def test_relationship_edge_from_dict():
    re_ = RelationshipEdge.from_dict("e1", {
        "from": "iu",
        "to": "player",
        "type": "OTHER",
        "state": {"trust": 0.5},
    })
    assert re_.from_character_id == "iu"
    assert re_.to_character_id == "player"
    assert abs(re_.state.trust - 0.5) < 0.001


def test_relationship_graph_list_format():
    rg = RelationshipGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "a", "to": "b", "type": "FRIEND"},
            {"id": "e2", "from": "b", "to": "a", "type": "FRIEND", "symmetric": True},
        ],
    })
    assert len(rg.edges) == 2
    assert rg.get_edge("a", "b") is not None


def test_relationship_graph_get_edges_from():
    rg = RelationshipGraph.from_dict({
        "edges": {
            "e1": {"from": "a", "to": "b"},
            "e2": {"from": "a", "to": "c"},
            "e3": {"from": "b", "to": "a"},
        },
    })
    edges = rg.get_edges_from("a")
    assert len(edges) == 2


def test_relationship_graph_symmetric_lookup():
    rg = RelationshipGraph.from_dict({
        "edges": {
            "e1": {"from": "a", "to": "b", "symmetric": True},
        },
    })
    assert rg.get_edge("b", "a") is not None


# ---------------------------------------------------------------------------
# Objectives / WinConditions
# ---------------------------------------------------------------------------

def test_objective_from_dict():
    o = Objective.from_dict({"id": "obj1", "title": "Find the knife", "type": "DISCOVER_FACT"})
    assert o.type == ObjectiveType.DISCOVER_FACT
    assert o.state == ObjectiveState.LOCKED


def test_win_conditions_all_of():
    wc = WinConditions.from_dict({
        "objectives": [
            {"id": "o1", "title": "A", "state": "COMPLETE"},
            {"id": "o2", "title": "B", "state": "COMPLETE"},
        ],
        "win_rule": "ALL_OF",
    })
    assert wc.check_complete() is True


def test_win_conditions_any_of():
    wc = WinConditions.from_dict({
        "objectives": [
            {"id": "o1", "title": "A", "state": "COMPLETE"},
            {"id": "o2", "title": "B", "state": "ACTIVE"},
        ],
        "win_rule": "ANY_OF",
    })
    assert wc.check_complete() is True


def test_win_conditions_not_complete():
    wc = WinConditions.from_dict({
        "objectives": [
            {"id": "o1", "title": "A", "state": "ACTIVE"},
        ],
        "win_rule": "ALL_OF",
    })
    assert wc.check_complete() is False


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------

def test_location_model_speaker_ids():
    lm = LocationModel.from_dict("room_a", {
        "name": "Interview Room A",
        "speaker_character_ids": ["steve"],
    })
    assert lm.speaker_character_ids == ["steve"]


def test_location_model_speaker_ids_string():
    lm = LocationModel.from_dict("room_a", {
        "name": "Room A",
        "speaker_character_ids": "steve",
    })
    assert lm.speaker_character_ids == ["steve"]


def test_movement_edge_from_dict():
    me = MovementEdge.from_dict("m1", {"from": "a", "to": "b", "minutes": 5})
    assert me.from_location_id == "a"
    assert me.minutes_cost == 5


def test_movement_graph_list_format():
    mg = MovementGraph.from_dict({
        "edges": [
            {"from": "a", "to": "b", "minutes": 2},
            {"from": "b", "to": "a", "minutes": 2},
        ],
    })
    assert len(mg.edges) == 2


# ---------------------------------------------------------------------------
# Game config
# ---------------------------------------------------------------------------

def test_output_policy_no_allow_second_person():
    """OutputPolicy must NOT have allow_second_person (fix #2)."""
    op = OutputPolicy.from_dict({})
    assert not hasattr(op, "allow_second_person") or "allow_second_person" not in op.__dataclass_fields__


def test_output_policy_defaults():
    op = OutputPolicy.from_dict({})
    assert op.narration_style == "cinematic"
    assert op.allow_player_action_narration is False


def test_game_config_from_dict():
    gc = GameConfig.from_dict({"mode": "interrogation"})
    assert gc.mode == "interrogation"


# ---------------------------------------------------------------------------
# StoryPackageV2 (root)
# ---------------------------------------------------------------------------

def test_minimal_v2_loads():
    pkg = StoryPackageV2.from_dict(_minimal_v2_dict())
    assert pkg.story_id == "test_story"
    assert pkg.version == 2
    assert "iu" in pkg.characters
    assert "anchor_identity" in pkg.knowledge.chunks


def test_v2_from_dict_none_safe():
    pkg = StoryPackageV2.from_dict(None)
    assert pkg.story_id == ""
    assert pkg.version == 2


def test_v2_characters_list_format():
    """Characters can be a list of dicts with 'id' field instead of a dict."""
    data = {
        "story_id": "t",
        "version": 2,
        "characters": [
            {"id": "c1", "identity": {"display_name": "Alice"}},
            {"id": "c2", "identity": {"display_name": "Bob"}},
        ],
    }
    pkg = StoryPackageV2.from_dict(data)
    assert "c1" in pkg.characters
    assert pkg.characters["c1"].identity.display_name == "Alice"
