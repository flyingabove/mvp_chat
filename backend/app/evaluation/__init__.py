# backend/app/evaluation/
"""Jev game arena: paired beta-vs-prod play, blinded Jev judging,
deterministic correctness checks and Elo-equivalent reporting.

Design: documentation/model_output_docs/JEV_GAME_ARENA_DESIGN.md.

Layout (pure core, I/O only at the edges):
  contracts.py    frozen data contracts shared by every stage
  rubric.py       judged dimensions, weights, criteria, rubric hash
  knowledge.py    GameKnowledgeBundle built from authored story/world JSON
  evidence.py     blinded, fenced, token-bounded judge evidence packets
  judge.py        PairwiseJudge protocol + JevPairwiseJudge (fail-closed)
  checks.py       deterministic correctness checks (independent of engine)
  aggregate.py    pure statistics: episode votes, Elo delta, bootstrap CI
  targets.py      TargetAdapter protocol + HostedTargetAdapter (/api/chat)
  players.py      PlayerPolicy protocol + LLMPlayer / ScriptedPlayer
  store.py        atomic, resumable experiment artifact store
  runner.py       ArenaRunner: paired games under a pinned manifest
  pipeline.py     judge pipeline: arms -> windows -> verdicts -> outcomes
  calibration.py  mutation sensitivity + A/A checks for the judge
  report.py       JSON + self-contained HTML report
  fakes.py        deterministic fakes (targets/players/judge) for tests

Nothing in engine/ or api/ imports this package; it only consumes the public
game API and the authored content files.
"""
