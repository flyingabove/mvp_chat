"""Generic character & world model (documentation/model_output_docs/CHARACTER_WORLD_MODEL_REDESIGN.md).

Pure, deterministic engine code: no LLM calls and no I/O. Story JSON supplies the
differences between games (routines, threads, evidence, homes). `turn.py` is
the only module the API layer calls.
"""
