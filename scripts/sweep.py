"""Parameter sensitivity sweep (TODO 10.1.1-10.1.4). One parameter at a time.

    uv run python scripts/sweep.py --param pheromones.pheromone_decay \
        --values 0.05,0.10,0.15,0.20,0.30 --games 40

No network, no LLM — built on `core.runtime.selfplay.play_sub_game`, the same
harness 3.5 uses, so a sweep number and a selfplay number are directly
comparable. The **negotiated config on disk is never touched**: each value is
applied to an in-memory copy of the loaded `Config`, so a sweep can run in the
middle of a live opponent negotiation without disturbing it.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.domain.board import Board  # noqa: E402
from core.domain.game_state import GameState  # noqa: E402
from core.domain.rules import Rules, Verdict  # noqa: E402
from core.domain.scoring import ScoreTable, score  # noqa: E402
from core.runtime.brain_loader import load_brain  # noqa: E402
from core.runtime.selfplay import play_sub_game  # noqa: E402
from core.shared.config_manager import Config, load_config  # noqa: E402

__all__ = ["main", "run_sweep", "with_override"]


def with_override(base: Config, param: str, value: Any) -> Config:
    """Return a copy of *base* with one dotted key replaced in `merged`."""
    merged = deepcopy(base.merged)
    node = merged
    keys = param.split(".")
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    return replace(base, merged=merged)


def _role() -> str:
    for role in ("police", "thief"):
        if (ROOT / "config" / role / "game.json").is_file():
            return role
    raise SystemExit("no config/<role>/game.json in this repository")


def run_sweep(
    param: str, values: list[Any], games: int, cop_spec: str = "", thief_spec: str = ""
) -> list[dict[str, Any]]:
    """Play *games* sub-games at each of *values* and return one summary row each."""
    base = load_config(ROOT / "config" / _role())
    rows = []
    for value in values:
        config = with_override(base, param, value)
        board = Board(
            grid_size=config.require("board_and_agents.grid_size"),
            origin_index=config.require("board_and_agents.axis_start_index"),
        )
        rules = Rules.from_config(config, board)
        start = GameState(
            cop=tuple(config.require("board_and_agents.cop_start")),
            thief=tuple(config.require("board_and_agents.thief_start")),
        )
        quota = config.require("movement_and_barriers.max_barriers")
        table = ScoreTable.from_config(config)
        results = [
            play_sub_game(load_brain(cop_spec, "cop", config),
                           load_brain(thief_spec, "thief", config), rules, quota, start)
            for _ in range(games)
        ]
        captures = sum(1 for r in results if r.outcome.verdict is Verdict.CAPTURE)
        points = [score(r.outcome, table) for r in results]
        rows.append({
            "param": param, "value": value, "games": games,
            "cop_win_rate": captures / games,
            "mean_steps": sum(r.steps for r in results) / games,
            "mean_barriers_placed": sum(r.barriers_placed for r in results) / games,
            "cop_points": sum(p[0] for p in points), "thief_points": sum(p[1] for p in points),
        })
        print(f"  {param}={value!r:<8} win_rate={rows[-1]['cop_win_rate']:.3f} "
              f"mean_steps={rows[-1]['mean_steps']:.1f}")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-parameter sensitivity sweep.")
    parser.add_argument("--param", required=True, help="Dotted config key, e.g. "
                         "pheromones.pheromone_decay")
    parser.add_argument("--values", required=True, help="Comma-separated values.")
    parser.add_argument("--games", type=int, default=40, help="Sub-games per value.")
    parser.add_argument("--float", action="store_true", help="Parse values as float.")
    parser.add_argument("--int", action="store_true", help="Parse values as int.")
    parser.add_argument("--cop", default="", help="Cop strategy, package.module:Class.")
    parser.add_argument("--thief", default="", help="Thief strategy.")
    parser.add_argument("--tag", default="", help="Suffix for the output filename.")
    args = parser.parse_args(argv)

    cast = float if args.float else int if args.int else str
    values = [cast(v) for v in args.values.split(",")]

    print(f"sweeping {args.param} over {values} ({args.games} games each)\n")
    rows = run_sweep(args.param, values, args.games, args.cop, args.thief)

    name = args.param.split(".")[-1] + (f"_{args.tag}" if args.tag else "")
    out = ROOT / "results" / f"sweep_{name}.json"
    out.write_text(json.dumps({
        "param": args.param, "generated_utc": datetime.now(UTC).isoformat(),
        "cop": args.cop, "thief": args.thief, "rows": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
