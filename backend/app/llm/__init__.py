# backend/app/llm/
"""All provider I/O lives here.

Per documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §2: `engine/`
defines decisions as pure data (backend/app/engine/extractors/
decision_registry.py) and assembles results; this package performs the
actual network calls. `engine/` must never import from this package —
providers/resolvers are injected into engine consumers (e.g.
TurnExtractor.__init__), never imported directly.

Step 2 of the Jev implementation order (see that doc §12): this package is
built now as a self-contained skeleton. Nothing outside this package imports
it yet — no call site changes until step 3 wires TurnExtractor to it.
"""
