# Reusable world atlas

The atlas is a view of the same locations and routes the game uses. Artwork is
an illustrated overview; typed data remains the authority for relative distances,
place identity, grouping, provenance, and travel costs.

## Model and integration

- `world/map_model.py`: immutable `MapPoint`, `PlaceResearch`, `MapArea`, and
  `WorldMap`. Areas are non-visitable containers with optional parent areas.
  Locations remain atomic `Location` graph nodes and retain their existing IDs.
- Regional positions are schematic kilometers east (+x) and north (+y) from an
  authored origin. They are deliberately not latitude/longitude or private
  addresses. Interior positions use separate 0–100 layout coordinates per area.
- Distance bands and positions are validated together. The loader rejects
  duplicate areas, parent cycles, missing parents, invalid interior positions,
  unknown location areas, and non-finite coordinates.
- Both `WorldLoader` and `WorldDefinitionLoader` parse the same optional metadata.
  Worlds without it retain their original routing and image-only map behavior.
- `world_map_payload()` serializes the graph for both `/api/story/{id}` and
  in-session `[MAP]` responses. `PathEdge` carries travel mode and estimate status.
- `route_policy: shortest_time` opts into deterministic Dijkstra routing by
  minutes. Blocked and disconnected routes are rejected; no random short trip is
  fabricated to bridge an island. Legacy worlds keep their original policy.
- `frontend/world-map.js` renders artwork, regional and nearby views, per-area
  interiors, searchable locations, evidence status, and route previews. It has
  no Six Strangers venue list or hard-coded story IDs. SVG coordinates preserve
  equal scale on both axes; numbered markers avoid overlapping labels.
- The backend explicitly serves the component's JS/CSS at root and `/beta/`.
  Image URLs use an asset revision from metadata to refresh replaced artwork.

## Six Strangers research decisions

`documentation/research/terrace_house_bgitc_places.md` and the accompanying chart
are preserved user research. `scripts/build_six_strangers_world.py` reproducibly
compiles this inventory into the world JSON; it does not execute document text.

The distance table takes precedence over overlapping chart labels. Its cluster
directions and distance bands are retained as approximate local offsets. No
uncertain venue is assigned an invented address. Nakameguro and the salon's
regional placement are explicitly approximate; unnamed venues have no map point.

The world contains 103 visitable places, 25 region/venue containers, and 270
directed edges (135 bidirectional links). All H01–H18, E01–E67 and O01–O15
inventory IDs are represented. O13 points to H15, the house swimming pool, so it
does not create a duplicate location. Four existing game additions remain: the
gender-matched shared bedrooms, neighborhood streets, Gotanda Station and fictional local cafe.
Existing location IDs, including `terrace`, `salon`, and `dance_studio`, stay
stable for character positions and saved sessions.

The functional house layout adds playroom, washitsu, separate bath/vanity/toilet/
laundry, hallway, pool, barbecue and driveway. `terrace` now means the pool deck
beside the living/dining glazing, not a rooftop. Related story prose is aligned.

Travel times are explicitly **gameplay estimates**, separate from researched
straight-line distances. Regional arrivals go to individual venues; interior
areas such as museum workshops, backstage rooms and the mountain summit are
reached through their associated front/public area. Unknown venues use labeled
estimated transit connections, not claims of proximity. The travel engine still
adds its configured departure cost to the route's transit minutes.

Historical names and episode evidence are research labels, not claims of current
business operation or a script that automatically reenacts future episodes.
O14/O15 and similar broad scene types remain generic placeholders because the
supplied research cannot identify every distinct establishment or private room.

## Artwork and verification

The redesigned Japanese RPG-style regional atlas is stored at the game's existing
`7_six_strangers.png` path. It has an enlarged house inset and an off-map Nagatoro
inset. Regional illustration distances are compressed; the data views provide the
faithful equal-scale relationships. Native generated resolution is 1536×1024;
two requests for higher native resolution did not change the generator's output.
No interpolated upscale is represented as additional detail. The generation
prompt is preserved in `documentation/research/six_strangers_artwork_prompt.md`.

Regression tests cover research coverage/deduplication, distance bands and
directions, reachability, blocked/shortest routes, both loaders, legacy IU loading,
API payloads, asset serving and frontend wiring. The location extractor no longer
truncates its destination list at 80 nodes.

`scripts/verify_world_map_browser.py --url <site> --output <artifact-directory>`
exercises the actual game UI with Chromium desktop and iPhone 13 WebKit, including
onboarding, artwork loading, region filtering, search, route details, interior
selection, enlargement, closing/reopening, JS errors and API request hosts.
Install optional Playwright tooling in the `storieschat` environment to run it.

## Player-facing map presentation (2026-09-24)

Startup and resume display only the clickable artwork. Tapping it opens the
full-screen image; double-tapping zooms it. The map menu or `[M]`/`[MAP]` command
opens the optional location browser. Descriptions are brief room/venue purposes;
research status, episode references and internal geometry notes stay out of the
player UI. Source research remains available in authored metadata. The world
builder generates the same short descriptions as the committed world JSON.
