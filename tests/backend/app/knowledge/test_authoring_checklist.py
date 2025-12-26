
def test_authoring_checklist_structure():
    from backend.app.knowledge.authoring_checklist import AUTHORING_CHECKLIST

    assert isinstance(AUTHORING_CHECKLIST, list)
    assert len(AUTHORING_CHECKLIST) >= 3
    for rule in AUTHORING_CHECKLIST:
        assert "rule_id" in rule
        assert "description" in rule