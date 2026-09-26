# North Star Gap Audit (2026-02-20)

Scope: compare current implementation to `documentation/human_north_star_docs/*` principles.

## Summary
The engine now has stronger epistemic layering and post-reply knowledge resolution, but several north-star gaps remain around strict two-call architecture, authority hardening, and deterministic mutation boundaries.

## Confirmed Alignments
1. **State-first authority**
   - Canonical facts and world movement are still state-driven, not transcript-driven.
2. **Namespace isolation**
   - Retrieval continues to use `<user>-<story>-<instance>` namespace keys.
3. **Epistemic layering**
   - Prompt stack explicitly orders canonical -> least canonical.
4. **Short-lived scene memory**
   - Transient buffer expiration is active; knowledge-resolution objects expire after 8 turns.

## Gaps / Logical Flaws

### 1) Two-call architecture is still partial
- North star prefers a strict structured pass then renderer pass.
- Current implementation has:
  - location extractor pre-render,
  - renderer,
  - knowledge-resolution extractor post-render.
- This is effectively **2+ passes**, not a clean deterministic two-call loop.

### 2) Knowledge resolution relies on free-form LLM judgment
- Unknown chunk ownership is inferred by LLM after each turn.
- There is no deterministic verifier step enforcing confidence thresholds or contradiction checks before belief writes.
- Risk: overfitting to style rather than evidence.

### 3) No promotion governance from transient/belief to canonical truth
- Resolved knowledge lives in belief + transient TTL objects.
- There is no audited promotion pipeline for when repeated, high-confidence claims should become canonical facts.

### 4) Retrieval artifacts are static during runtime
- User decision suggested dynamic update to FAISS/BM25 or graph.
- Current implementation updates graph-side belief state only (no runtime artifact rewrite).
- This is safer operationally but means recall depends on prompt/transient layering, not index mutation.

### 5) Invariant checks are not centralized
- There is still no single invariant validator ensuring:
  - canonical truths never overwritten by lower tiers,
  - not_known_by vs known_by conflicts are blocked,
  - cross-turn epistemic contradictions are explicitly marked.

### 6) Prompt budget control is heuristic, not contract-enforced
- Stack ordering exists, but token budget partitioning per layer is not hard-enforced.
- Lower-tier text can still crowd higher-tier context in long conversations.

### 7) Post-reply extractor write order may hide causal provenance
- Resolution writes occur after renderer output.
- If replay tooling inspects only final state, causality requires careful event logs to reconstruct why a belief changed.

## Recommended Next Actions (Prioritized)
1. Add deterministic post-extractor validator (`confidence`, contradiction, duplicate guards) before belief write.
2. Add optional promotion queue for repeated high-confidence claims (belief -> candidate canonical review).
3. Introduce fixed prompt token caps per stack layer.
4. Formalize multi-pass contract in docs and runner (pre-extract, render, post-extract as explicit phases).
5. Add invariant checker utility run at end of each turn in debug mode.

## Practical Decision Note
Given current architecture, graph-side updates are the safest interpretation of “update Faiss/BM25 or graph.”
Direct FAISS/BM25 mutation per turn is intentionally avoided to prevent index corruption, cross-session bleed, and non-deterministic retrieval drift.
