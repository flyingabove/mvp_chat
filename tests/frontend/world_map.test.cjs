const test = require("node:test");
const assert = require("node:assert/strict");
const {
  routeBetween,
  regionalArea,
  project,
} = require("../../frontend/world-map.js");

test("route planner uses time, blocked edges and unreachable destinations", () => {
  const edges = [
    { from: "a", to: "b", minutes: 90 },
    { from: "a", to: "c", minutes: 5 },
    { from: "c", to: "b", minutes: 5 },
    { from: "b", to: "d", minutes: 1, blocked: true },
  ];
  assert.equal(routeBetween(edges, "a", "b").minutes, 10);
  assert.equal(routeBetween(edges, "a", "d"), null);
  assert.equal(routeBetween(edges, "a", "a").minutes, 0);
});
test("scene rooms inherit their venue regional group", () => {
  const atlas = {
    areas: [
      { id: "region", position: { x: 5, y: 5 } },
      { id: "venue", parent_id: "region" },
    ],
  };
  assert.equal(regionalArea(atlas, "venue").id, "region");
  assert.equal(regionalArea(atlas, "unknown"), undefined);
});
test("projection preserves north, east, and equal geographic scale", () => {
  const bounds = { minX: -50, maxX: 50, minY: -50, maxY: 50 };
  const a = project({ x: 0, y: 0 }, bounds),
    east = project({ x: 10, y: 0 }, bounds),
    north = project({ x: 0, y: 10 }, bounds);
  assert.ok(east.x > a.x);
  assert.ok(north.y < a.y);
  assert.equal(east.x - a.x, a.y - north.y);
});
