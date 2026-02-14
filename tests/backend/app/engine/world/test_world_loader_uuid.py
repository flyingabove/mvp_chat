import json

from backend.app.engine.world.world_loader import WorldLoader


def test_world_loader_sets_location_uuid(tmp_path):
    data = {
        "world_id": "demo_world",
        "version": 1,
        "time": {"start_minute": 0},
        "locations": {
            "loc_one": {
                "name": "Loc One",
                "description": "desc",
                "tags": ["t1"],
                "allows_phone": True
            }
        },
        "edges": []
    }
    p = tmp_path / "world.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    loaded = WorldLoader.load_from_file(
        str(p),
        user_id="user_demo",
        story_id="story_demo",
        instance=3,
    )

    loc = loaded.world_graph.get_location("loc_one")
    assert loc.uuid == "user_demo-story_demo-3-loc_one"
