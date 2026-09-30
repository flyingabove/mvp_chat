# Full iOS/mobile UI overhaul

## BL-13 — Full iOS/mobile UI overhaul not actioned
- **Open:** the 2026-09-19 plan (keyboard-safe chat shell, typing-animation rework, map/locations sheet redesign, touch targets, composer text size) was deferred; many findings are likely stale (the portrait-404 finding did not reproduce). Shipped since: wrapped home header, safe-area standalone shell, larger map close and pinch zoom, 288px portraits, a distinct beta install manifest; the user confirmed a Beta Home Screen install works on an iPhone 14. On beta at 390px the `StoriesChat` logo was partly covered by the `Play as Guest` pill (2026-09-24, re-check).
- **Next:** re-run the audit fresh before any work, then treat the survivors as one multi-commit initiative through ship-and-verify.
- **Touches:** `frontend/index.html`.
