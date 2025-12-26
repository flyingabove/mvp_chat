from backend.app.engine.state import init_state


def test_apply_placeholders_and_sanitize_korean_terms():
    import backend.app.api.chat as chat_mod

    st = init_state()
    st.player_name = "Chris"
    st.gender = "M"
    out = chat_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st)
    assert "Chris" in out
    assert "oppa" in out  # honorific placeholder is meta-only for opening

    # At low relationship, sanitize should strip forbidden terms
    st.relationship = 0
    st.user.display_name = "Chris"
    cleaned = chat_mod.sanitize_korean_terms("hello oppa unnie", st)
    assert "oppa" not in cleaned.lower()
    assert "unnie" not in cleaned.lower()


def test_name_extraction_and_confirmation():
    import backend.app.api.chat as chat_mod

    st = init_state()
    name = chat_mod.extract_user_name_from_text("my name is alice")
    assert name == "Alice"

    # confirmation should set names
    st.last_assistant_guess_name = "Bob"
    chat_mod.handle_name_confirmation("yes", st)
    assert st.user.formal_name == "Bob"