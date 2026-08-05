"""Expectimax over the belief map (TODO 8.1.1, 8.1.11; PRD advanced §3.1).

Expectimax rather than minimax, for a reason that is about this game rather
than about search: **we do not know the opponent's policy.** Minimax assumes the
worst case, and the worst case here is an evader that plays perfectly against
our exact position — an assumption that throws away the whole posterior we spent
Phase 4 building and produces a Cop that hedges against a Thief nobody fielded.
Chance nodes weight successors by the mass we actually believe (A1.2).

Why there is no "information-gathering" move
--------------------------------------------
An earlier reading of A1.13 had this module scoring moves by how much they would
reduce expected entropy after the next observation. **That term would always be
zero.** Our sensor is the opponent's transmitted scent field, which arrives
whole and is identical whichever cell we are standing on — moving somewhere does
not let us see more. There is nothing to gather.

What multimodality actually changes is which move is *cheapest*, and the
distinction still matters enormously. A peak that is a peak only because ties
break on coordinates can sit six steps away while three quarters of the
probability sits two steps away, and the argmax chase walks past all of it.
Because `_expected_distance` is mass-weighted over every cell rather than the
peak, the search goes to the mass without needing a separate term, and
`tests/unit/test_cop_search.py` asserts exactly that against the baseline.
A1.14's "revert to direct pursuit when unimodal" then falls out for free: a
concentrated posterior makes the weighted objective and the argmax objective the
same objective.
"""

from __future__ import annotations

from core.domain.actions import Direction
from core.domain.belief import mask, predict
from core.domain.board import Board, Position
from core.domain.brain_base import Observation
from police.evaluation import CAPTURE_VALUE, CopWeights, evaluate

__all__ = ["best_move", "expectimax", "options"]

# Depth used when nothing configures one. 3 plies is ~125 leaves on a 5-way
# branch and completes in milliseconds, which is comfortably inside the 30 s
# step deadline (A1.3) even on Diana's machine.
DEFAULT_DEPTH = 3


def options(cop: Position, barriers: frozenset[Position], board: Board) -> list[tuple[Direction, Position]]:
    """Return every ``(direction, destination)`` the Cop may legally take.

    STAY is always available and always first, so a Cop with no legal step still
    has a decision to return rather than raising inside a search. It also keeps
    the ordering stable, which is what makes an unbroken tie resolve identically
    on both machines replaying the same log.
    """
    moves = [(Direction.STAY, cop)]
    moves.extend(
        (direction, cell)
        for direction, cell in board.neighbours(cop)
        if board.is_passable(cell, barriers)
    )
    return moves


def _value_of(
    destination: Position,
    belief: dict[Position, float],
    barriers: frozenset[Position],
    board: Board,
    depth: int,
    weights: CopWeights,
) -> float:
    """Return the expected value of stepping onto *destination*.

    Two things happen at once and the split is the whole point of a chance node:

    * With probability ``belief[destination]`` the Thief is standing there and
      the sub-game **ends in a capture** — worth more than any position.
    * Otherwise the Thief is somewhere else, and the posterior conditioned on
      *not* having been caught is exactly the masked, renormalised belief. That
      conditioning is free information, and a search that skipped it would keep
      chasing mass it has already ruled out.

    The Thief then moves, so the belief is widened by the same `predict` step
    the live filter uses. Using a different transition model here would search a
    game the filter is not playing.
    """
    caught = belief.get(destination, 0.0)
    survivors = mask(belief, barriers, destination)
    if not survivors:
        return CAPTURE_VALUE
    ahead = expectimax(
        destination, predict(survivors, board, barriers), barriers, board, depth - 1, weights
    )
    return caught * CAPTURE_VALUE + (1.0 - caught) * ahead


def expectimax(
    cop: Position,
    belief: dict[Position, float],
    barriers: frozenset[Position],
    board: Board,
    depth: int,
    weights: CopWeights,
) -> float:
    """Return the value of a position to the Cop, searching *depth* plies.

    Args:
        cop: Where the Cop stands.
        belief: Posterior over the Thief's cell at this node.
        barriers: Walls in force. **Constant through the search** — placements
            are chosen by `barrier_policy`, not searched over, because a
            placement costs the move and would double the branching factor to
            buy a decision the phase machine makes better on measured state.
        board: Geometry.
        depth: Plies remaining. 0 evaluates immediately.
        weights: Relative worth of each evaluation term.

    Returns:
        The Cop's expected value. Higher is better.
    """
    if depth <= 0 or not belief:
        return evaluate(cop, belief, barriers, board, weights)
    return max(
        _value_of(destination, belief, barriers, board, depth, weights)
        for _, destination in options(cop, barriers, board)
    )


def best_move(
    observation: Observation, weights: CopWeights, depth: int = DEFAULT_DEPTH
) -> tuple[Direction, float]:
    """Return the Cop's best action and its value.

    Ties break on the fixed ordering from `options` rather than on whichever
    float happened to compare larger, so two peers replaying one log reach the
    same move. Near-ties are broken deliberately and unexploitably elsewhere
    (TODO 8.3.1); a *search* that wobbled would make the log unverifiable, which
    is a different and much worse problem.
    """
    scored = [
        (
            _value_of(
                destination, observation.belief, observation.barriers, observation.board, depth, weights
            ),
            index,
            direction,
        )
        for index, (direction, destination) in enumerate(
            options(observation.own_position, observation.barriers, observation.board)
        )
    ]
    value, _, direction = max(scored, key=lambda entry: (entry[0], -entry[1]))
    return direction, value
