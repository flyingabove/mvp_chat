from backend.app.engine.state import init_state
from backend.app.engine.gameplay import advance_time
from backend.app.engine.transient_buffer import TransientEntry, prune_expired


def test_prune_expired_by_turns():
    e1 = TransientEntry(
        id="a",
        namespace="default_user-story-1",
        scope="conversation",
        text="hello",
        created_turn=1,
        created_minute=0,
        expires_after_turns=2,
    )
    e2 = TransientEntry(
        id="b",
        namespace="default_user-story-1",
        scope="conversation",
        text="fresh",
        created_turn=3,
        created_minute=0,
        expires_after_turns=2,
    )

    kept = prune_expired([e1, e2], current_turn=4, current_minute=0)
    ids = [e.id for e in kept]
    assert "a" not in ids
    assert "b" in ids


def test_state_purge_transient_entries():
    st = init_state()
    st.story = "demo"
    st.turns = 0
    st.minute = 0

    st.add_transient_entry(
        id="t1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="Player said hi",
        expires_after_turns=1,
    )
    assert len(st.transient_entries) == 1

    st.turns = 1
    st.purge_transient_entries()
    assert len(st.transient_entries) == 0


def test_location_transient_clears_on_travel():
    st = init_state()
    st.story_cfg = {}
    st.location = "Hospital"

    st.add_transient_entry(
        id="loc1",
        namespace="default_user-demo-1",
        scope="location",
        text="Coffee cup on table",
        expires_after_turns=10,
    )
    st.add_transient_entry(
        id="conv1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="Asked about coffee",
        expires_after_turns=10,
    )

    advance_time(st, "go to Work")

    scopes = [e.scope for e in st.transient_entries]
    assert "location" not in scopes
    assert "conversation" in scopes
