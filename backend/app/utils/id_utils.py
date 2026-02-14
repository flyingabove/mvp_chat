# app/utils/id_utils.py
import re
from backend.app.config.settings import DEFAULT_USER_ID, DEFAULT_INSTANCE


_non_alnum_dash_underscore = re.compile(r"[^a-z0-9_-]+")


def slug_token(value: str, *, allow_dash: bool = True) -> str:
    """Normalize a token to lowercase alnum with separators.

    Returns an empty string if nothing remains after cleaning.
    """
    if not value:
        return ""
    v = value.strip().lower()
    # Convert whitespace to underscores first to preserve word boundaries
    v = re.sub(r"\s+", "_", v)
    v = _non_alnum_dash_underscore.sub("-" if allow_dash else "_", v)
    # Collapse runs separately to keep underscores distinct from dashes
    v = re.sub(r"-+", "-" if allow_dash else "_", v)
    v = re.sub(r"_+", "_", v)
    v = v.strip("-_")
    return v[:128]


def build_deterministic_uuid(*, user_id: str = DEFAULT_USER_ID, story_id: str = "", instance: int = DEFAULT_INSTANCE, entity_id: str = "") -> str:
    """Build a stable, human-readable UUID using the configured scheme.

    Format: <user>-<story>-<instance>-<entity>
    All parts are slugged; instance is clamped to >=1.
    """
    user = slug_token(user_id) or DEFAULT_USER_ID
    story = slug_token(story_id) or "unknown_story"
    try:
        inst_val = int(instance)
    except Exception:
        inst_val = DEFAULT_INSTANCE
    if inst_val < 1:
        inst_val = 1
    inst = str(inst_val)
    entity = slug_token(entity_id) or "entity"
    return f"{user}-{story}-{inst}-{entity}"
