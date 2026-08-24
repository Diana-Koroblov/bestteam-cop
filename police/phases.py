"""When to herd, when to seal, when to squeeze (TODO 8.1.9, 8.1.10; §3.4).

Barrier timing is **not a schedule**. It follows from one fact: a barrier is
only lethal when the Thief's exit count is already small, and exit count only
falls when the Thief is edge- or corner-bound. Spending a wall on an open board
removes 1/49 of the Thief's room and gifts it a free step — a trade that loses.

So every transition here is driven by something measured on the board (A1.11):
belief entropy, the believed Thief's exit count, the size of the region it can
still reach. Never by turn number.

The one turn number in the file, and why it is not a trigger
------------------------------------------------------------
`[strategy] barrier_hold_until_turn` ships in both configs and A1.11 forbids
turn-driven transitions. The two are reconciled by making the key **suppressive
only**: below that turn it can hold us in HERD, and it can never by itself cause
a placement. A guard that only ever makes us more conservative does not drive
anything.

It is also overridable by measurement, which matters because A1.12 requires
spending barriers *earlier* against an orbiting Thief — so an ORBITER
classification lifts the floor. Recorded in `docs/CONTRADICTIONS.md` as C-015.

Profiling from the belief peak, not from sight
----------------------------------------------
The Cop never sees the Thief (M#8), so `core/domain/opponent_model.py` — which
takes an observed position — cannot be used here. What we have instead is the
trajectory of our own belief peak, which is an estimate and is sometimes wrong.
That is acceptable for a *coarse* trait and would not be for a fine one, which
is why this reads one gated category rather than a model (TODO 8.3.2).

**The measurement moved out of this file in 8.3.** It lived here as a local
`ThiefProfile` while the Cop was the only role that profiled anything. The
Thief needs the same trait — a Cop that never walls cannot catch us, so its
movement and its barrier rate change how much risk is worth taking — and a
module in `police/` does not exist in the Thief's repository. So the traits are
now `core/domain/opponent_profile.py` and this file only *reads* them, which is
also what keeps the count inside A3.6's cap of four: flee and orbit are two
thresholds on one measured quantity, not two traits (CONTRADICTIONS C-016).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.domain.belief import entropy
from core.domain.brain_base import Observation
from core.domain.connectivity import exit_count, region_size
from core.domain.opponent_profile import MovementStyle, OpponentProfile

__all__ = ["Phase", "PhaseSettings", "classify"]


class Phase(str, Enum):
    """Which of the three plans is in force."""

    HERD = "HERD"
    SEAL = "SEAL"
    SQUEEZE = "SQUEEZE"


@dataclass(frozen=True)
class PhaseSettings:
    """Measured thresholds for the transitions. Ours alone, never negotiated.

    Attributes:
        confident_bits: Entropy at or below which the belief is trusted enough
            to build against. A uniform 7x7 is ~5.6 bits; 3.5 is roughly mass
            concentrated into a dozen cells.
        seal_exits: Believed Thief exit count at or below which it counts as
            edge-committed and sealing begins.
        squeeze_cells: Region size at or below which we stop cutting and start
            closing.
        hold_until_turn: Suppressive floor only — see the module docstring.
        flee_rate: Above this, the Thief is a greedy fleer that the board's own
            edges will corner for free.
        orbit_rate: Above this, the belief peak keeps returning to cells it has
            already occupied, which is what circling looks like from here.
    """

    confident_bits: float = 3.5
    seal_exits: int = 3
    squeeze_cells: int = 12
    hold_until_turn: int = 0
    flee_rate: float = 0.65
    orbit_rate: float = 0.35

    @classmethod
    def from_config(cls, config: Any) -> PhaseSettings:
        """Read the shipped `[strategy]` keys, defaulting to the values above."""
        if config is None:
            return cls()
        return cls(
            confident_bits=float(config.get("strategy.confident_bits", cls.confident_bits)),
            seal_exits=int(config.get("strategy.seal_exits", cls.seal_exits)),
            squeeze_cells=int(config.get("strategy.squeeze_cells", cls.squeeze_cells)),
            hold_until_turn=int(config.get("strategy.barrier_hold_until_turn", 0)),
            flee_rate=float(config.get("strategy.flee_rate_threshold", cls.flee_rate)),
            orbit_rate=float(config.get("strategy.orbit_rate_threshold", cls.orbit_rate)),
        )


def classify(
    observation: Observation, profile: OpponentProfile, settings: PhaseSettings
) -> Phase:
    """Return the plan in force this turn.

    Args:
        observation: This turn's local truth.
        profile: What we have inferred about the opponent so far.
        settings: Measured thresholds.

    Returns:
        HERD while the belief is too diffuse to build against or the Thief still
        holds open ground; SEAL once it is edge-committed; SQUEEZE once its
        region is small enough to close.
    """
    target = observation.most_likely_opponent()
    if target is None or entropy(observation.belief) > settings.confident_bits:
        return Phase.HERD

    style = profile.style(settings.flee_rate, settings.orbit_rate)
    if observation.step < settings.hold_until_turn and style is not MovementStyle.ORBITER:
        return Phase.HERD

    barriers, board = observation.barriers, observation.board
    if region_size(target, barriers, board) <= settings.squeeze_cells:
        return Phase.SQUEEZE

    # A greedy fleer corners itself against the board's own edges, so we wait
    # for a stricter sign before paying for a wall it was going to walk into
    # anyway (A1.12). An orbiter never corners itself and the chase never
    # converges, so against it the barriers have to come out early.
    strict = style is MovementStyle.FLEE_GREEDY
    threshold = settings.seal_exits - 1 if strict else settings.seal_exits
    if style is MovementStyle.ORBITER or exit_count(target, barriers, board) <= threshold:
        return Phase.SEAL
    return Phase.HERD
