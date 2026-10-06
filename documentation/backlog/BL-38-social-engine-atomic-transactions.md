# Social engine: atomic turns and correctness (tracker)

## BL-38 — Social-engine correctness and atomic transactions (tracker)
- **Bucket:** C (engine)
- **Open:** durable turn/reply atomicity is only partly done. Built: request receipts in the same transaction as the state compare-and-swap (replay of the latest 200 requests, 409 on a reused id with different text, new-game receipts). Not done: the JSONL transcript (`ConversationRepo.append_turns`) and the fact-extraction outbox enqueue happen after the commit, so a crash between loses transcript or extraction work (never state or reply); early-return command paths write no receipt; scoped testimony/beliefs, single-writer relationships, old-save migration.
- **Next:** implement as part of the master design ([design/SOCIAL_ENGINE.md](../design/SOCIAL_ENGINE.md) sections 3-6, 8, 10), not as a second architecture. Keep one social-state writer, at most two LLM calls, no hidden-state leakage, no fabricated consent.
- **Touches:** `prompt_engine.py`, `world_model/{turn,model,character,epistemics,agreements,projection}.py`, `character_graph.py`, session persistence.
