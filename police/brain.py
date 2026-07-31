"""The Cop's baseline: walk the shortest legal path toward the belief peak.

Deliberately simple. Its job is to be a **measurable floor** — every later
tactic from ``PRD_strategy_advanced.md`` gets A/B'd against this, so it has to
be honest and boring rather than clever.

What it does *not* do, on purpose:

* **It places no barriers.** A wall is permanent and can strand the Cop on the
  wrong side of it, losing the sub-game outright (see ``connectivity.py``).
  A baseline that placed them badly would make every A/B comparison against it
  meaningless — we would be measuring "better than a self-trapping cop", which
  is not a useful floor. Barrier strategy arrives in Phase 4 with the belief
  filter that makes it safe.
* **It never consults a language model.** Movement is algorithmic (Ch. 6, M#25).
"""

from __future__ import annotations

from core.domain.actions import Direction
from core.domain.brain_base import BrainBase, Decision, Observation
from core.domain.connectivity import are_connected
from core.domain.pathfinding import first_step_towards

__all__ = ["PoliceBrain"]


class PoliceBrain(BrainBase):
    """Pursues the most likely opponent cell by shortest path."""

    def _pick_move(self, observation: Observation) -> Decision:
        """Step toward the belief peak, or hold position when there is no target.

        Three cases, and the last two are the ones worth having:

        * a reachable target — take the first step of a shortest path;
        * **no belief at all** — hold. Wandering would be worse than useless: it
          spreads our own scent over cells that carry no information and makes
          the trail we leave harder for us to reason about later;
        * a target we cannot reach — hold, and say so. Barriers are permanent,
          so an unreachable thief means the sub-game is already lost; walking
          into the wall repeatedly would hide that in the log.
        """
        target = observation.most_likely_opponent()
        if target is None:
            return Decision(Direction.STAY, reason="no belief yet - holding position")

        if not are_connected(
            observation.own_position, target, observation.barriers, observation.board
        ):
            return Decision(
                Direction.STAY,
                reason=f"{target} is not reachable from {observation.own_position}",
            )

        move = first_step_towards(
            observation.own_position, target, observation.barriers, observation.board
        )
        return Decision(move, reason=f"shortest path toward {target}")
