from backend.app.engine.extractors.knowledge_resolution_extractor import KnowledgeResolutionExtractor


def test_parse_json_returns_updates():
    raw = '{"updates": [{"chunk_id": "c1", "knows": true, "confidence": 0.91, "reason": "explicit statement"}]}'
    out = KnowledgeResolutionExtractor._parse_json(raw)
    assert len(out) == 1
    assert out[0].chunk_id == "c1"
    assert out[0].knows is True
    assert out[0].confidence == 0.91


def test_parse_json_ignores_invalid_rows():
    raw = '{"updates": [{"chunk_id": "", "knows": false, "confidence": "x"}, {"chunk_id": "c2", "knows": false, "confidence": 2.5}]}'
    out = KnowledgeResolutionExtractor._parse_json(raw)
    assert len(out) == 1
    assert out[0].chunk_id == "c2"
    assert out[0].confidence == 1.0
