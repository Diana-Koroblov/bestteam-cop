"""The advanced Cop (TODO 8.1; PRD advanced §3). Where the league grade lives.

Between two competent teams every sub-game ends in survival, the series ties and
each side takes 2. The Cop carries a 15-point spread against the Thief's 5 and is
the **only role that can win outright**, so this is the file that decides where
we finish.

Four decisions, in this order, every turn:

1. **Watch.** Fold this turn's belief peak into the opponent profile. Free, and
   it is the only way to tell a greedy fleer from an orbiter without ever seeing
   the Thief (M#8).
2. **Phase.** Ask `phases.classify` which plan is in force. Measured state only
   — entropy, exit count, region size — never the turn number.
3. **Wall?** Outside HERD, ask `barrier_policy` for the best legal placement.
   It returns None whenever every candidate is refused, which is most turns.
4. **Move.** Ask the expectimax for the best step, then take whichever of the
   two actions is worth more. They are comparable because both are valued by the
   same search on the position they produce.

`decide` is overridden rather than `_pick_move` because a placement **replaces**
the move rather than accompanying it (Ch. 3.4) — the choice is between them, not
after one of them.

This does not replace `police/brain.py`. The baseline stays exactly as it is,
because every claim made here is an A/B result against it (TODO 8.QG.4) and a
floor you have edited is not a floor.
"""

from __future__ import annotations

from typing import Any

from core.domain.actions import Direction
from core.domain.brain_base import BrainBase, Decision, Observation
from police.barrier_policy import best_barrier
from police.evaluation import CopWeights
from police.phases import Phase, PhaseSettings, ThiefProfile, classify
from police.search import DEFAULT_DEPTH, best_move

__all__ = ["AdvancedCop"]


class AdvancedCop(BrainBase):
    """Expectimax pursuit with connectivity-safe cutting."""

    def __init__(self, name: str = "", depth: int = DEFAULT_DEPTH) -> None:
        """Build a Cop that plays competently with no configuration at all.

        Args:
            name: Display name for logs and the A/B table.
            depth: Search plies. Overridden by `configure` when a config is
                available, because A1.3 makes depth config-driven — but a
                default lives here so a fresh clone plays a real game.
        """
        super().__init__(name)
        self.depth = depth
        self.weights = CopWeights()
        self.settings = PhaseSettings()
        self.profile = ThiefProfile()
        self.phase = Phase.HERD
        self._last_step = -1

    def configure(self, config: Any) -> None:
        """Adopt the `[strategy]` section (A1.3).

        Called at startup by the brain loader, where a bad value costs an error
        message. Reading config lazily on the first turn would surface a typo
        thirty seconds into a graded match, and a peer that crashes mid-turn
        takes a technical loss worth 0 to both teams.
        """
        self.depth = int(config.get("strategy.search_depth", self.depth))
        self.weights = CopWeights.from_config(config)
        self.settings = PhaseSettings.from_config(config)

    def _pick_move(self, observation: Observation) -> Decision:
        """Return the best step. Present because `BrainBase` requires it.

        `decide` is what runs in a match; this exists so the movement half can
        be exercised on its own, and so a caller that only wants a move is not
        forced through the barrier machinery.
        """
        direction, _ = best_move(observation, self.weights, self.depth)
        return Decision(direction, reason=f"expectimax d{self.depth} -> {direction.value}")

    def decide(self, observation: Observation) -> Decision:
        """Choose between the best wall and the best step, and say why.

        The reason string carries the phase and the placement verdict into the
        match log, so a replay can explain a turn the Cop spent walking past a
        wall it could have built (TODO 7.5.1).
        """
        self._track(observation)
        self.phase = classify(observation, self.profile, self.settings)
        direction, move_value = best_move(observation, self.weights, self.depth)

        placement = None
        if self.phase is not Phase.HERD and observation.barriers_remaining > 0:
            placement = best_barrier(observation, self.weights, self.settings, self.depth)

        if placement is not None and placement[1] > move_value:
            cell, _, why = placement
            return Decision(Direction.STAY, barrier=cell, reason=f"{self.phase.value}: {why}")
        return Decision(direction, reason=f"{self.phase.value}: expectimax -> {direction.value}")

    def _track(self, observation: Observation) -> None:
        """Record the belief peak, restarting the trajectory on a new sub-game.

        A sub-game boundary shows up as the step counter failing to advance. The
        peak *list* must not survive it — a cell "revisited" across two different
        sub-games says nothing about whether this opponent circles — while the
        traits themselves legitimately accumulate over the six games of a series.
        Banking them across sub-games is TODO 8.3.3 and is not done here.
        """
        if observation.step <= self._last_step:
            self.profile = ThiefProfile()
        self._last_step = observation.step
        self.profile.observe(observation.most_likely_opponent(), observation.own_position)
