import pytest


def test_load_character_indexes_never_attribute_errors(monkeypatch, tmp_path):
    """
    Regression test: env vars are strings; loader must convert to Path
    and never call .exists() on a str.
    """
    from backend.app.knowledge.runtime import load_indexes as li

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KNOWLEDGE_PERSIST_ROOT", str(tmp_path / "persist"))

    # We don't care what error it raises here (artifacts may be missing),
    # only that it is NOT AttributeError about .exists/.iterdir/etc.
    try:
        li.load_character_indexes("1_iu")
    except Exception as e:
        assert not isinstance(e, AttributeError), f"Unexpected AttributeError: {e!r}"
