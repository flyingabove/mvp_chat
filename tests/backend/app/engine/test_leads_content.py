"""BL-39 phase J (O05): every authored lead must unlock something the player can act on.

Leads that name nothing executable make the investigation promise progress it
cannot deliver. This check reports them by id; the known IU gaps are tracked
in BL-41 until their record/interview content is authored.
"""
from backend.app.engine.story_loader import build_story_registry, get_active_story_ids

KNOWN_UNAUTHORED = {  # BL-41: owner-authored content needed; remove entries as they are authored
    "iu_murder_mystery": {"manager_interview", "sojin_schedule", "aster_meeting", "han_pressure_call", "driver_log"},
}


def _executable_ids(story: dict) -> set[str]:
    ids = {str(lead.get("id")) for lead in story.get("leads") or []}
    ids |= {str(e.get("id")) for e in (story.get("world_model") or {}).get("entities") or []}
    return ids


def test_leads_only_unlock_actionable_content():
    for story_id in get_active_story_ids():
        story = build_story_registry()[story_id]["raw"]
        executable = _executable_ids(story)
        dangling = {u for lead in story.get("leads") or [] for u in lead.get("unlocks") or []} - executable
        assert dangling == KNOWN_UNAUTHORED.get(story_id, set()), (story_id, sorted(dangling))
