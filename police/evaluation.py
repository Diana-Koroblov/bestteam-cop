"""How good is this Cop position? (TODO 8.1.2, 8.1.3, 8.1.8; PRD advanced §3.2)

One function, `evaluate`, scoring a *hypothetical* position against a belief
rather than a known Thief. Everything the search does is stacked on it, so the
sign conventions matter: **higher is better for the Cop**, and every term is
either a reward for progress toward the win condition or a penalty for the one
mistake that cannot be undone.

The correction that shapes this file
------------------------------------
An earlier draft of the strategy PRD rejected any barrier that reduced the Cop's
own mobility. That was wrong, and it would have refused the winning move.
**Co-confinement is a win**: Cop and Thief sealed together in a small region
means the Cop sweeps it and the Thief has nowhere left to go. The failure mode is
not a small region, it is *separation* — walling yourself into region A while the
believed Thief mass sits in region B. Those two look almost identical on a board
and are opposite in value, which is why `separation_mass` is computed and
weighted rather than eyeballed.

So the region term is deliberately signed against size (§3.2 A1.6) while the
separation term is a hard penalty on mass we can no longer reach (A1.5). Shrink
the room you are both in; never build a room you are not in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.board import Board, Position
from core.domain.connectivity import reachable
from core.domain.cuts import region_has_cycle
from core.domain.pathfinding import distance_map

__all__ = ["CopWeights", "evaluate", "separation_mass", "endgame_mass"]

# Winning is not on the same scale as positional advantage. A capture pays 20
# against a survival's 5, and no arrangement of walls is worth declining one, so
# the terminal reward has to dominate every positional term combined.
CAPTURE_VALUE = 1000.0


@dataclass(frozen=True)
class CopWeights:
    """Relative worth of each term. Ours alone — never negotiated, never sent.

    Attributes:
        separation: Penalty per unit of believed mass outside our component
            (A1.5). Far larger than the others because stranding mass does not
            cost us position, it costs us the sub-game.
        shared_region: `β` in `−β·|component|` (A1.6). Small: shrinking the
            shared room is steady progress, not a decisive event.
        proximity: Penalty per expected step of distance to the Thief.
        endgame: Reward for mass sitting on a cell one wall from capture (A1.8,
            M#47). Large, because that state *is* the plan.
        cycle: Penalty for believed mass in a region that still contains a
            cycle — a region the Thief can circle indefinitely (§2.1).
        reach: Reward per cell removed from the Thief's near-term reachable set
            by a placement (A1.7). Used only by `barrier_policy`.
        diagonal: Reward per anchored corner a placement sits against (A1.8).
            Also placement-only, and deliberately modest — it is a prior on
            cuts, not a measurement.
    """

    separation: float = 400.0
    shared_region: float = 0.6
    proximity: float = 2.0
    endgame: float = 60.0
    cycle: float = 12.0
    reach: float = 1.5
    diagonal: float = 2.0

    @classmethod
    def from_config(cls, config: Any) -> CopWeights:
        """Read `[strategy] weight_*` keys, falling back to the defaults above.

        Defaults live in the dataclass rather than in config because a fresh
        clone must play a competent game with no tuning file, and because a
        weight silently defaulting to 0 in code would disable a whole term
        without any error to notice.
        """
        if config is None:
            return cls()
        defaults = cls()
        read = {
            field: float(config.get(f"strategy.weight_{field}", getattr(defaults, field)))
            for field in (
                "separation", "shared_region", "proximity", "endgame", "cycle", "reach", "diagonal"
            )
        }
        return cls(**read)


def separation_mass(
    cop: Position, belief: dict[Position, float], barriers: frozenset[Position], board: Board
) -> float:
    """Return the believed Thief mass we can no longer reach (A1.5).

    This is the number that must stay at zero. Any positive value means some
    fraction of where the Thief probably is has been walled away from us, and
    that fraction of our win probability is gone permanently.
    """
    component = reachable(cop, barriers, board)
    return sum(mass for cell, mass in belief.items() if cell not in component)


def endgame_mass(
    cop: Position, belief: dict[Position, float], barriers: frozenset[Position], board: Board
) -> float:
    """Return the mass sitting where one more wall would capture (TODO 8.1.8).

    The evaluation targets the win condition **explicitly** rather than trusting
    that generic region-shrinking arrives there. §2.2 is precise about what
    capture needs — *drive the exit count to 1 while standing next to that exit*
    — and a Cop rewarded only for smaller regions will happily shrink a region
    from the wrong side and never take the last step.

    A cell with no exits left counts fully: that is already a capture under M#47.
    """
    total = 0.0
    for cell, mass in belief.items():
        if mass <= 0.0:
            continue
        free = [n for _, n in board.neighbours(cell) if board.is_passable(n, barriers)]
        # Sealed already (M#47), or one wall from it with the gap in our reach
        # — the two halves of the win condition in §2.2.
        one_wall_away = len(free) == 1 and _placeable(cop, free[0])
        if not free or one_wall_away:
            total += mass
    return total


def _placeable(cop: Position, cell: Position) -> bool:
    """Return True when the Cop could wall *cell* on its next turn.

    Ch. 3.4 allows the Cop's own cell **or** an orthogonal neighbour, so a Cop
    standing on the Thief's last exit is one placement from capture just as
    surely as one standing beside it — and an adjacency-only test would miss
    exactly that position, which is the strongest one on the board.
    """
    return cop == cell or abs(cop[0] - cell[0]) + abs(cop[1] - cell[1]) == 1


def _expected_distance(
    cop: Position, belief: dict[Position, float], barriers: frozenset[Position], board: Board
) -> float:
    """Return the mass-weighted path distance to the Thief.

    Path distance, not Manhattan: once walls exist the two diverge sharply, and
    a Cop chasing the straight-line nearest cell will walk into its own barrier.
    Unreachable mass is charged the whole board width rather than skipped, so an
    evaluation cannot improve itself by making cells unreachable.
    """
    distances = distance_map(cop, barriers, board)
    far = float(board.grid_size * 2)
    return sum(mass * distances.get(cell, far) for cell, mass in belief.items())


def _cycle_mass(
    belief: dict[Position, float], barriers: frozenset[Position], board: Board
) -> float:
    """Return the believed mass sitting in regions that still hold a cycle.

    Computed per distinct region rather than per cell — cyclicity is a property
    of the region, so asking it 49 times would be 49 identical breadth-first
    searches. The whole region is labelled on first visit, which matters because
    this runs at every node of a depth-3 search.
    """
    cyclic: dict[Position, bool] = {}
    total = 0.0
    for cell, mass in belief.items():
        if mass <= 0.0 or not board.is_passable(cell, barriers):
            continue
        if cell not in cyclic:
            verdict = region_has_cycle(cell, barriers, board)
            for member in reachable(cell, barriers, board):
                cyclic[member] = verdict
        total += mass if cyclic[cell] else 0.0
    return total


def evaluate(
    cop: Position,
    belief: dict[Position, float],
    barriers: frozenset[Position],
    board: Board,
    weights: CopWeights,
) -> float:
    """Score a Cop position against a belief. Higher is better for the Cop.

    Args:
        cop: Where the Cop stands in the position being scored.
        belief: Posterior over the Thief's cell. Need not be normalised; every
            term is linear in mass, so an unnormalised belief scales the score
            rather than distorting the ordering.
        barriers: The walls in the position being scored, ours included.
        board: Geometry.
        weights: Relative worth of each term.

    Returns:
        A float with no absolute meaning. Only comparisons between candidate
        positions are used, so the scale is free.
    """
    component = reachable(cop, barriers, board)
    inside = sum(mass for cell, mass in belief.items() if cell in component)
    return (
        -weights.separation * separation_mass(cop, belief, barriers, board)
        - weights.shared_region * len(component) * inside
        - weights.proximity * _expected_distance(cop, belief, barriers, board)
        + weights.endgame * endgame_mass(cop, belief, barriers, board)
        - weights.cycle * _cycle_mass(belief, barriers, board)
    )
