"""Generic character & world model (documentation/design/WORLD_MODEL.md).

Pure, deterministic engine code: no LLM calls and no I/O. Story JSON supplies the
differences between games (routines, threads, evidence, homes). `turn.py` is
the only module the API layer calls.
"""
