"""Which wall, and whether to build one at all (TODO 8.1.2, 8.1.4-8.1.7, 8.1.12).

A barrier is the only permanent act in the game and the only way the Cop can
win, which makes this the file where a bug is most expensive. Placements are
filtered before they are scored, because three of the rules below are not
preferences — they are refusals, and a refusal that had merely been given a poor
score would still be taken on a turn when everything else scored worse.

The four refusals
-----------------
* **Uncertainty** (A1.15, TODO 8.1.12). No wall while the belief is diffuse. A
  barrier placed where the Thief probably is not can open a route *for* it, and
  unlike a bad move it cannot be walked back. Uncertainty is a reason to look,
  not to build. The phase machine already holds us in HERD here; this is a
  second, independent guard, and permanence earns the redundancy.
* **Separation** (A1.5, TODO 8.1.2 and 8.1.4). Reject anything that strands
  believed Thief mass outside our own component. This *is* the wall-behind-
  yourself rule: a wall between Cop and Thief strands mass by construction, and
  a wall behind the Cop cannot. Expressing it as a mass comparison rather than a
  geometric test means it also catches the subtle cases — a wall that looks
  behind us but closes the last corridor round a region.
* **Futility.** Reject a wall that changes neither the Thief's reachable set nor
  its exit count. It cost a turn and bought nothing.
* **Unfinishable cuts** (A1.10, TODO 8.1.7). Sealing a cell means blocking every
  exit it has, so its exit count after this placement is a lower bound on the
  walls still needed. If that exceeds the quota we would have left, the seal
  leaks — and a leaking seal is worse than no seal, because we paid turns for it
  and the Thief walked out through the gap.

Scoring the survivors
---------------------
Everything that passes is valued with the **same** expectimax the movement
search uses, on the position the placement produces. That is deliberate: it is
the only way the Cop can compare "place here" against "step there" honestly,
since the two are alternatives on the same turn. A separate placement score on
its own scale would have made the comparison arbitrary.

One heuristic rides on top. A diagonal cut pays off over four or more moves and
is therefore invisible past a 3-ply horizon, so `cut_bonus` supplies a prior the
search cannot see. It is weighted modestly on purpose — a prior that outvoted
the search would be a prior making the decisions.
"""

from __future__ import annotations

from core.domain.belief import entropy, mask, predict
from core.domain.board import Position
from core.domain.brain_base import Observation
from core.domain.connectivity import exit_count
from core.domain.cuts import diagonal_support, k_step_reach, region_has_cycle
from core.domain.movement import is_immobilised
from police.evaluation import CAPTURE_VALUE, CopWeights, separation_mass
from police.phases import PhaseSettings
from police.search import expectimax

__all__ = ["candidates", "rejection_for", "placement_value", "best_barrier", "REACH_HORIZON"]

# How far ahead the Thief's reachable set is measured when valuing a cut. Five
# steps is about how long a seal takes to matter; cells it could only reach in
# twelve turns are not part of this fight (`cuts.k_step_reach`).
REACH_HORIZON = 5

# Mass differences below this are float noise, not stranding.
EPSILON = 1e-9


def candidates(observation: Observation) -> list[Position]:
    """Return the cells this Cop could legally wall this turn.

    Ch. 3.4 allows the Cop's own cell or an orthogonal neighbour, and no more —
    so the Cop cannot cut at a distance and must **walk to** every wall it wants.
    That constraint is what makes the three-phase plan necessary rather than
    decorative: the herding is how the Cop gets to where the cut has to go.

    Own-cell placements are included. A barrier blocks entry, not exit, so the
    Cop can wall the cell it stands on and step off it next turn — which is the
    cheapest way to close a corridor behind yourself.
    """
    board, barriers = observation.board, observation.barriers
    reachable_cells = [observation.own_position]
    reachable_cells.extend(cell for _, cell in board.neighbours(observation.own_position))
    return [
        cell
        for cell in reachable_cells
        if board.in_bounds(cell) and cell not in barriers
    ]


def rejection_for(cell: Position, observation: Observation, settings: PhaseSettings) -> str:
    """Return why *cell* must not be walled, or ``""`` when it may be.

    Ordered as a reviewer would ask them, so the reason names the first thing
    actually wrong. The string is carried into the `Decision.reason` and into
    the match log, which is what lets a replay explain a turn the Cop spent
    moving when a wall looked available.
    """
    target = observation.most_likely_opponent()
    if target is None or entropy(observation.belief) > settings.confident_bits:
        return "belief too diffuse to build against"
    if observation.barriers_remaining <= 0:
        return "barrier quota is spent"

    after = observation.barriers | {cell}
    board, belief = observation.board, observation.belief
    # Stranding is judged on the mass that *survives* the placement. Mass this
    # wall captures cannot be stranded — the sub-game is over for it — and an
    # earlier version of this check refused the winning move for exactly that
    # reason: sealing the Thief's last exit strands a Thief that is no longer
    # there to be stranded.
    before_mass = separation_mass(observation.own_position, belief, observation.barriers, board)
    survivors = _surviving_belief(cell, observation)
    if separation_mass(observation.own_position, survivors, after, board) > before_mass + EPSILON:
        return f"{cell} would strand believed thief mass outside our own component"

    exits = exit_count(target, after, board)
    reach_before = k_step_reach(target, observation.barriers, board, REACH_HORIZON)
    if exits == exit_count(target, observation.barriers, board) and k_step_reach(
        target, after, board, REACH_HORIZON
    ) == reach_before:
        return f"{cell} changes neither the thief's exits nor its reach"
    if exits > observation.barriers_remaining - 1:
        return f"sealing {target} needs {exits} more walls and only {observation.barriers_remaining - 1} remain"
    return ""


def cut_bonus(cell: Position, observation: Observation, weights: CopWeights) -> float:
    """Reward cuts whose payoff sits beyond the search horizon (A1.8, A1.9).

    Two terms, both about geometry the expectimax cannot reach in three plies:

    * **Diagonal support.** Barriers touching corner to corner form a wall with
      no gap, because movement is orthogonal only — so the diagonal is the
      cheapest cut on this grid, and a placement extending one continues work
      already paid for. Board edges count as support; they are free wall.
    * **Cycle removal.** A region the Thief can circle is a region it survives
      in for all 35 steps however small it is, so converting a cyclic region
      into a cycle-free one is worth more than the cells it removes.
    """
    target = observation.most_likely_opponent()
    after = observation.barriers | {cell}
    board = observation.board
    bonus = weights.diagonal * diagonal_support(cell, observation.barriers, board)
    if target is None:
        return bonus
    removed = len(k_step_reach(target, observation.barriers, board, REACH_HORIZON)) - len(
        k_step_reach(target, after, board, REACH_HORIZON)
    )
    broke_cycle = region_has_cycle(target, observation.barriers, board) and not region_has_cycle(
        target, after, board
    )
    return bonus + weights.reach * removed + (weights.cycle * broke_cycle)


def _is_caught(occupied: Position, cell: Position, after: frozenset[Position], board) -> bool:
    """Whether a Thief on *occupied* is captured by a wall on *cell*.

    Both capture rules, because the Cop placing against a belief cannot tell
    which one fired: the wall may land **on** the Thief (M#46), or it may seal
    the last exit of a cell the Thief occupies (M#47).
    """
    return occupied == cell or is_immobilised(occupied, after, board)


def _surviving_belief(cell: Position, observation: Observation) -> dict[Position, float]:
    """Return the belief with every captured cell removed. Not renormalised.

    Kept unnormalised on purpose: the caller needs the *absolute* mass that
    survives, because a placement capturing 90% of the posterior and stranding
    the rest is a good wall, and renormalising would report the stranded 10% as
    100% and refuse it.
    """
    after = observation.barriers | {cell}
    board = observation.board
    return {
        occupied: mass
        for occupied, mass in observation.belief.items()
        if not _is_caught(occupied, cell, after, board)
    }


def _captured_mass(cell: Position, observation: Observation) -> float:
    """Return the believed mass this placement captures outright."""
    survived = sum(_surviving_belief(cell, observation).values())
    return sum(observation.belief.values()) - survived


def placement_value(
    cell: Position, observation: Observation, weights: CopWeights, depth: int
) -> float:
    """Return the expected value of walling *cell*, comparable with a move.

    The Cop forgoes its move to place, so it stays put and the Thief still gets
    its step — which is exactly why a wall that buys nothing is a real loss and
    not merely a wasted resource.
    """
    after = observation.barriers | {cell}
    board, cop = observation.board, observation.own_position
    caught = _captured_mass(cell, observation)
    survivors = mask(observation.belief, after, cop)
    if not survivors or caught >= 1.0:
        return CAPTURE_VALUE
    ahead = expectimax(
        cop, predict(survivors, board, after), after, board, depth - 1, weights
    )
    return caught * CAPTURE_VALUE + (1.0 - caught) * ahead + cut_bonus(cell, observation, weights)


def best_barrier(
    observation: Observation, weights: CopWeights, settings: PhaseSettings, depth: int
) -> tuple[Position, float, str] | None:
    """Return the best legal placement as ``(cell, value, reason)``, or None.

    None means *every* candidate was refused, and the Cop moves instead. That is
    the common case and the safe one: on any turn where the walls available are
    all bad walls, not building is strictly better than building the least bad.
    """
    scored = [
        (placement_value(cell, observation, weights, depth), cell)
        for cell in candidates(observation)
        if not rejection_for(cell, observation, settings)
    ]
    if not scored:
        return None
    value, cell = max(scored, key=lambda entry: (entry[0], entry[1]))
    target = observation.most_likely_opponent()
    return cell, value, f"wall {cell}: cuts {target} to {exit_count(target, observation.barriers | {cell}, observation.board)} exits"
