"""Epistemic feature toggles (single source of truth).

EPISTEMIC_MASTER gates all epistemic behaviors. Sub-flags gate each layer:
- TRUTH: canonical facts / truth graph mutations
- BELIEF: claims/beliefs/observations/epistemic log
- NARRATIVE: transcript/log emission for epistemic playback
- RETRIEVAL: retrieval-style snippets for epistemic memory

Use `set_epistemic_flags` as a context manager to flip flags in tests.
"""
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class EpistemicSwitches:
    master: bool = True
    truth: bool = True
    belief: bool = True
    narrative: bool = True
    retrieval: bool = True


# Global switches (single location to change)
FLAGS = EpistemicSwitches()


def is_enabled() -> bool:
    return FLAGS.master


def truth_enabled() -> bool:
    return FLAGS.master and FLAGS.truth


def belief_enabled() -> bool:
    return FLAGS.master and FLAGS.belief


def narrative_enabled() -> bool:
    return FLAGS.master and FLAGS.narrative


def retrieval_enabled() -> bool:
    return FLAGS.master and FLAGS.retrieval


def set_master(enabled: bool) -> None:
    FLAGS.master = bool(enabled)


def snapshot() -> EpistemicSwitches:
    return EpistemicSwitches(**FLAGS.__dict__)


@contextmanager
def set_epistemic_flags(*, master=None, truth=None, belief=None, narrative=None, retrieval=None):
    prev = EpistemicSwitches(**FLAGS.__dict__)
    try:
        if master is not None:
            FLAGS.master = bool(master)
        if truth is not None:
            FLAGS.truth = bool(truth)
        if belief is not None:
            FLAGS.belief = bool(belief)
        if narrative is not None:
            FLAGS.narrative = bool(narrative)
        if retrieval is not None:
            FLAGS.retrieval = bool(retrieval)
        yield
    finally:
        FLAGS.master = prev.master
        FLAGS.truth = prev.truth
        FLAGS.belief = prev.belief
        FLAGS.narrative = prev.narrative
        FLAGS.retrieval = prev.retrieval
