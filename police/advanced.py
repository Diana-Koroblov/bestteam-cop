"""The advanced Cop (TODO 8.1, 8.3; PRD advanced §3, §5). Where the league grade lives.

Between two competent teams every sub-game ends in survival, the series ties and
each side takes 2. The Cop carries a 15-point spread against the Thief's 5 and is
the **only role that can win outright**, so this is the file that decides where
we finish.

Six decisions, in this order, every turn:

1. **Listen.** Fold their hint into the posterior, scaled by what their record
   says it is worth, and fold this turn into the four profiled traits — free,
   and it is the only way to tell a greedy fleer from a circler without ever
   seeing the Thief (M#8).
2. **Phase.** Ask `phases.classify` which plan is in force. Measured state only
   — entropy, exit count, region size — never the turn number.
3. **Wall?** Outside HERD, ask `barrier_policy` for the best legal placement.
   It returns None whenever every candidate is refused, which is most turns.
4. **Move.** Score every legal step with the expectimax, then break near-ties on
   a seeded draw so a balanced position does not produce a readable move
   (8.3.1).
5. **Compare.** Take whichever of wall and step is worth more. They are
   comparable because both are valued by the same search on the position they
   produce.
6. **Speak.** Decide truth or lie and which bearing to claim. In HERD a lie has
   a job — A3.10 spends credibility to steer a fleeing Thief into the region we
   picked — so the phase is passed to the policy rather than inferred by it.

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
from core.domain.bluff import BluffPolicy, BluffSettings
from core.domain.brain_base import BrainBase, Decision, Observation
from core.domain.tiebreak import DEFAULT_EPSILON, Tiebreaker
from core.domain.trail import TrailTracker
from core.domain.verbal import VerbalLayer
from police.barrier_policy import best_barrier
from police.evaluation import CopWeights
from police.phases import Phase, PhaseSettings, classify
from police.search import DEFAULT_DEPTH, scored_moves

__all__ = ["AdvancedCop"]


class AdvancedCop(BrainBase):
    """Expectimax pursuit with connectivity-safe cutting and a verbal game."""

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
        self.verbal = VerbalLayer()
        self.ties = Tiebreaker(epsilon=DEFAULT_EPSILON)
        self.phase = Phase.HERD
        self._last_step = -1
        self._sub_game = 0

    def configure(self, config: Any) -> None:
        """Adopt the `[strategy]`, `[game]` and `[pheromones]` sections (A1.3).

        Called at startup by the brain loader, where a bad value costs an error
        message. Reading config lazily on the first turn would surface a typo
        thirty seconds into a graded match, and a peer that crashes mid-turn
        takes a technical loss worth 0 to both teams.

        The decay rate and model come from the **negotiated** pheromone section
        rather than our own preferences: the trail we reconstruct is priced
        against what the engine is really emitting, and C-007 means either decay
        model may have been signed.
        """
        self.depth = int(config.get("strategy.search_depth", self.depth))
        self.weights = CopWeights.from_config(config)
        self.settings = PhaseSettings.from_config(config)
        self.ties = Tiebreaker(
            seed=int(config.get("game.seed", 0)),
            epsilon=float(config.get("strategy.tie_epsilon", DEFAULT_EPSILON)),
        )
        self.verbal = VerbalLayer(
            bluff=BluffPolicy(settings=BluffSettings.from_config(config)),
            trail=TrailTracker(
                rate=float(config.get("pheromones.pheromone_decay", 0.10)),
                model=str(config.get("pheromones.decay_model", "multiplicative")),
            ),
        )

    def meets(self, team: str) -> None:
        """Clear the profile if this is a different opponent (A3.5, TODO 8.3.3).

        **The opponent boundary is normally the process boundary.** One process
        plays one role against exactly one peer (M#1, M#4), so a fresh match is
        a fresh brain and a fresh profile by construction — no team name crosses
        the wire for us to key on, and inventing one would be worse than the
        structure we already have.

        This exists for the case where that is not true: a self-play batch or a
        series runner that reuses one brain against several opponents. Calling
        it with the same name twice does nothing, so it is safe on every path.
        """
        self.verbal.profile.for_opponent(team)

    def restart_sub_game(self, sub_game: int) -> None:
        """Bank the profile and drop the board state (TODO 9.5).

        Nothing else needs clearing: `self.phase` is recomputed from scratch by
        `classify` on every turn, and the barrier quota belongs to the
        `BarrierManager` the driver builds per sub-game rather than to us.
        """
        self.verbal.restart(sub_game)

    def _pick_move(self, observation: Observation) -> Decision:
        """Return the best step. Present because `BrainBase` requires it.

        `decide` is what runs in a match; this exists so the movement half can
        be exercised on its own, and so a caller that only wants a move is not
        forced through the barrier machinery.
        """
        direction, _ = self._step(observation, observation.belief)
        return Decision(direction, reason=f"expectimax d{self.depth} -> {direction.value}")

    def decide(self, observation: Observation) -> Decision:
        """Choose between the best wall and the best step, and say why.

        The reason string carries the phase and the placement verdict into the
        match log, so a replay can explain a turn the Cop spent walking past a
        wall it could have built (TODO 7.5.1).
        """
        self._track(observation)
        belief = self.verbal.observe(observation)
        self.phase = classify(observation, self.verbal.profile, self.settings)
        direction, move_value = self._step(observation, belief)

        placement = None
        if self.phase is not Phase.HERD and observation.barriers_remaining > 0:
            placement = best_barrier(observation, self.weights, self.settings, self.depth)

        if placement is not None and placement[1] > move_value:
            cell, _, why = placement
            return self._spoken(Direction.STAY, observation, f"{self.phase.value}: {why}", cell)
        return self._spoken(
            direction, observation, f"{self.phase.value}: expectimax -> {direction.value}"
        )

    def _step(self, observation: Observation, belief) -> tuple[Direction, float]:
        """Return the chosen step and its value, near-ties drawn (8.3.1)."""
        scored = scored_moves(observation, self.weights, self.depth, belief)
        direction = self.ties.choose(scored)
        return direction, next(value for value, move in scored if move is direction)

    def _spoken(
        self,
        move: Direction,
        observation: Observation,
        reason: str,
        barrier=None,
    ) -> Decision:
        """Attach this turn's hint decision to a chosen action.

        The claim describes *movement*, so a turn spent placing a wall claims
        the bearing of the move we did not make — which is truthful about
        nothing and is therefore refused: `STAY` yields no claim at all.
        """
        intent, claim = self.verbal.speak(move, observation, herding=self.phase is Phase.HERD)
        said = f", says {claim.value} ({intent.value})" if claim else ", says nothing"
        return Decision(move, barrier=barrier, reason=reason + said, claim=claim, intent=intent)

    def _track(self, observation: Observation) -> None:
        """Cross a sub-game boundary, which shows up as the step counter resetting.

        Traits are **banked** across the six sub-games of a series and cleared
        only for a new opponent (A3.5, TODO 8.3.3); the per-sub-game trajectory,
        our trail and the tie-break stream all restart here. A cell "revisited"
        across two different sub-games says nothing about whether this opponent
        circles.
        """
        if observation.step <= self._last_step:
            self._sub_game += 1
            self.verbal.restart(self._sub_game)
            self.ties.restart(self._sub_game)
        self._last_step = observation.step
