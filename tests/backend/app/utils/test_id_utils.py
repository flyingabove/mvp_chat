import pytest

from backend.app.utils.id_utils import slug_token, build_deterministic_uuid, build_namespace_key


def test_slug_token_preserves_underscores_and_lowercases():
    assert slug_token("User Name_X") == "user_name_x"


def test_build_deterministic_uuid_composes_parts_and_clamps_instance():
    uid = build_deterministic_uuid(user_id="User X", story_id="Story Y", instance=2, entity_id="Main Hero")
    assert uid == "user_x-story_y-2-main_hero"

    # defaults when missing pieces
    fallback = build_deterministic_uuid(entity_id="")
    assert fallback.startswith("default_user-unknown_story-1-")
    assert fallback.endswith("entity")

    # instance clamped to >=1
    assert build_deterministic_uuid(instance=0, story_id="s", entity_id="e") == "default_user-s-1-e"


def test_build_namespace_key_slugs_and_clamps():
    ns = build_namespace_key(user_id="User X", story_id="Story Y", instance=0)
    assert ns == "user_x-story_y-1"

    fallback = build_namespace_key(story_id="", instance="not-an-int")
    assert fallback == "default_user-unknown_story-1"
