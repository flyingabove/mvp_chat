from backend.app.engine.state import init_state
from backend.app.engine.transient_buffer import TransientKnowledge, prune_expired
from backend.app.config.settings import TRANSIENT_KNOWLEDGE_TURNS


def test_prune_expired_by_turns():
    e1 = TransientKnowledge(text="hello", turns_remaining=1)
    e2 = TransientKnowledge(text="fresh", turns_remaining=2)

    kept = prune_expired([e1, e2], current_turn=4, current_minute=0)
    texts = [e.text for e in kept]
    assert "hello" not in texts
    assert "fresh" in texts
    assert kept[0].turns_remaining == 1


def test_state_purge_transient_entries():
    st = init_state()
    st.story = "demo"
    st.turns = 0
    st.minute = 0

    # BUG-01 fix: expires_after_turns=1 must result in TTL=1, not TRANSIENT_KNOWLEDGE_TURNS.
    st.add_transient_entry(
        id="t1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="Player said hi",
        expires_after_turns=1,
    )
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].turns_remaining == 1  # BUG-01 fixed: respects caller TTL

    # A single purge call should expire the 1-turn entry.
    st.turns = 1
    st.purge_transient_entries()

    assert len(st.transient_entries) == 0


def test_transient_entries_use_default_ttl_of_eight():
    st = init_state()
    st.story = "demo"

    st.add_transient_entry(
        id="t1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="One",
    )
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].turns_remaining == TRANSIENT_KNOWLEDGE_TURNS
