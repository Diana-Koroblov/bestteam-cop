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
is why there are two traits with a sample gate rather than a model (TODO 8.3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.domain.belief import entropy
from core.domain.board import Position
from core.domain.brain_base import Observation
from core.domain.connectivity import exit_count, region_size

__all__ = ["Phase", "ThiefKind", "ThiefProfile", "PhaseSettings", "classify"]

# Below this many observed steps we decline to classify. Six is one sub-game's
# worth of peaks: enough to separate a fleer from an orbiter, nowhere near
# enough to fit anything subtle, which is the point (TODO 8.3.2).
MIN_SAMPLES = 6


class Phase(str, Enum):
    """Which of the three plans is in force."""

    HERD = "HERD"
    SEAL = "SEAL"
    SQUEEZE = "SQUEEZE"


class ThiefKind(str, Enum):
    """The coarse opponent trait the phasing is gated on (A1.12)."""

    UNKNOWN = "UNKNOWN"
    FLEE_GREEDY = "FLEE_GREEDY"
    ORBITER = "ORBITER"


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


@dataclass
class ThiefProfile:
    """Two coarse traits, estimated from where we believe the Thief has been.

    Attributes:
        peaks: The believed Thief cell at each observed step, in order.
        away: How many of those steps increased its distance from us.
    """

    peaks: list[Position] = field(default_factory=list)
    away: int = 0

    def observe(self, peak: Position | None, cop: Position) -> None:
        """Record this turn's belief peak. Free, so it happens every turn.

        A None peak — no belief at all — is skipped rather than recorded as a
        stationary Thief, which would drag the flee rate toward zero and
        misclassify a fleer as an orbiter on exactly the turns we know least.
        """
        if peak is None:
            return
        if self.peaks and _distance(peak, cop) > _distance(self.peaks[-1], cop):
            self.away += 1
        self.peaks.append(peak)

    @property
    def samples(self) -> int:
        """Steps that produced a usable transition."""
        return max(len(self.peaks) - 1, 0)

    @property
    def flee_fraction(self) -> float:
        """Fraction of observed steps that opened the distance."""
        return self.away / self.samples if self.samples else 0.0

    @property
    def orbit_fraction(self) -> float:
        """Fraction of observed steps that returned to an already-visited cell.

        Revisiting is what circling looks like when all you have is a sequence
        of estimated positions. A fleer on a finite board eventually revisits
        too, which is why this is compared against a threshold rather than used
        as a boolean, and why `kind` prefers the fleer reading when both fire.
        """
        if not self.peaks:
            return 0.0
        seen: set[Position] = set()
        revisits = 0
        for cell in self.peaks:
            revisits += cell in seen
            seen.add(cell)
        return revisits / len(self.peaks)

    def kind(self, settings: PhaseSettings) -> ThiefKind:
        """Classify, or decline to (TODO 8.3.2).

        Below `MIN_SAMPLES` the answer is UNKNOWN and the phasing falls back to
        pure board measurement. Adapting to a phantom read from three noisy
        peaks is worse than not adapting at all.
        """
        if self.samples < MIN_SAMPLES:
            return ThiefKind.UNKNOWN
        if self.flee_fraction >= settings.flee_rate:
            return ThiefKind.FLEE_GREEDY
        if self.orbit_fraction >= settings.orbit_rate:
            return ThiefKind.ORBITER
        return ThiefKind.UNKNOWN


def _distance(first: Position, second: Position) -> int:
    """Manhattan distance. Walls are irrelevant to *which way they went*."""
    return abs(first[0] - second[0]) + abs(first[1] - second[1])


def classify(observation: Observation, profile: ThiefProfile, settings: PhaseSettings) -> Phase:
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

    kind = profile.kind(settings)
    if observation.step < settings.hold_until_turn and kind is not ThiefKind.ORBITER:
        return Phase.HERD

    barriers, board = observation.barriers, observation.board
    if region_size(target, barriers, board) <= settings.squeeze_cells:
        return Phase.SQUEEZE

    # A greedy fleer corners itself against the board's own edges, so we wait
    # for a stricter sign before paying for a wall it was going to walk into
    # anyway (A1.12). An orbiter never corners itself and the chase never
    # converges, so against it the barriers have to come out early.
    threshold = settings.seal_exits - 1 if kind is ThiefKind.FLEE_GREEDY else settings.seal_exits
    if kind is ThiefKind.ORBITER or exit_count(target, barriers, board) <= threshold:
        return Phase.SEAL
    return Phase.HERD
