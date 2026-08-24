"""Unit tests for the league's own four-artefact schema (core/compat/league_report.py).

`game_id`/`game_uid` are checked against the league conformance kit's own
published vector (`vectors/game_uid.json` in copthief-league-protocol,
verified against its own `verify_vectors.py` before this test was written),
not just against ourselves — a self-consistent but wrong formula is exactly
what WARNINGS §2 in that kit warns burns a pairing.
"""

from __future__ import annotations

from core.compat.league_report import (
    build_result,
    build_sub_game_row,
    consensus_envelope,
    game_id,
    game_uid,
)

# The kit's own published vector — canonical order and swapped-order rows both
# resolve to this. https://github.com/Imreec/copthief-league-protocol
_TERMS = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
    "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
    "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
}
_EXPECTED_UID = "1e73c318-5b29-4a7b-1c60-ecb8286265f0"
_EXPECTED_ID = "team-aleph-vs-team-bet"


def test_game_id_matches_the_kits_published_vector() -> None:
    assert game_id("team-aleph", "team-bet") == _EXPECTED_ID
    assert game_id("team-bet", "team-aleph") == _EXPECTED_ID


def test_game_uid_matches_the_kits_published_vector() -> None:
    assert game_uid(_TERMS, "team-aleph", "team-bet") == _EXPECTED_UID
    # Swapped group order: identical uid, per the kit's own "canonical order" /
    # "groups swapped" pair — neither side has to be told which name goes first.
    assert game_uid(_TERMS, "team-bet", "team-aleph") == _EXPECTED_UID


def test_game_uid_changes_when_the_terms_do() -> None:
    other = {**_TERMS, "setting": "New York"}
    assert game_uid(_TERMS, "a", "b") != game_uid(other, "a", "b")


def test_a_label_distinguishes_a_replay_from_its_own_predecessor() -> None:
    """yanell11, 24/08: without a label, a voided series and its replay share
    one game_id, one game_uid, and one settlement hash if the score matches -
    the replay overwrites the first attempt in a grader's inbox view."""
    assert game_id("bestteam", "imreeyal", "counted-2") == "bestteam-vs-imreeyal-counted-2"
    assert game_uid(_TERMS, "a", "b", "x") != game_uid(_TERMS, "a", "b")


def test_a_labelled_game_uid_matches_yanell11s_own_independent_derivation() -> None:
    """Cross-checked byte-for-byte against yanell11's own computation, not just
    self-consistent with ours (22/08 taught us that lesson the hard way)."""
    terms = {
        "axis_origin_corner": "top-left", "axis_start_index": 0, "barriers_max": 14,
        "board_size": 7, "cop_start": [0, 0], "decay_per_step": 0.1, "emit_intensity": 0.9,
        "hint_max_words": 15, "max_steps": 35, "min_center_intensity": 0.5, "num_games": 6,
        "setting": "Haifa", "smell_grid_size": 5, "thief_start": [3, 3],
    }
    assert game_uid(terms, "bestteam", "yanell11", "counted-2") == (
        "106fb655-03e9-56ff-94d7-894efde40d16"
    )


def _row(number: int, result: str, winner: str, our_points: int, their_points: int) -> dict:
    return build_sub_game_row(
        number=number, our_group="bestteam", their_group="imreeyal",
        our_role="police", result=result, winner_group=winner, steps=20,
        our_commit="a" * 40, their_commit="b" * 40, our_tokens=0, their_tokens=0,
        our_points=our_points, their_points=their_points, log_filename="log.json",
        log_verified=True, tampered=False, started_at="t0", ended_at="t1",
    )


def _series(rows: list[dict]) -> dict:
    """The `build_result` keywords that are not the rows, for tests about rows."""
    return {
        "counted": True, "our_group": "bestteam", "their_group": "imreeyal",
        "sub_games": rows, "game_uid_value": "uid-1", "timezone": "Asia/Jerusalem",
        "repos": {}, "games_played": {"bestteam": 1, "imreeyal": None},
        "first_meeting": True,
    }


def test_mutual_agreement_confirmed_is_derived_not_asserted() -> None:
    """🐛 **It was the literal `True`**, and went out on 16/08 over a series in
    which three of six sub-games never exchanged a turn.

    `confirmed` is a claim about a mutual exchange that a grader byte-compares
    against the opponent's copy, so a hard-coded one is false the moment it is
    written. Derived from the audits: the opponent's reveal verifying is the
    only evidence we hold that both sides played the same sub-game.
    """
    played = [_row(1, "capture", "bestteam", 20, 5), _row(2, "survival", "imreeyal", 5, 10)]
    assert build_result(**_series(played))["mutual_agreement"]["confirmed"] is True

    never_engaged = build_sub_game_row(
        number=2, our_group="bestteam", their_group="imreeyal", our_role="thief",
        result="technical_loss", winner_group="", steps=0, our_commit="a" * 40,
        their_commit="b" * 40, our_tokens=0, their_tokens=0, our_points=0,
        their_points=0, log_filename="log.json", log_verified=False, tampered=False,
        started_at="t0", ended_at="t1",
    )
    mixed = build_result(**_series([played[0], never_engaged]))
    assert mixed["mutual_agreement"]["confirmed"] is False
    # ...and the hash is still produced: the signature covers what happened,
    # whatever it was. It is `confirmed` that must not lie, not the digest.
    assert mixed["mutual_agreement"]["sha256"]


def test_a_row_names_the_thief_as_the_opposite_role() -> None:
    row = _row(1, "capture", "bestteam", 20, 5)
    assert row["roles"] == {"bestteam": "police", "imreeyal": "thief"}
    assert row["score"] == {"bestteam": 20, "imreeyal": 5}
    assert row["audit"] == {"log_verified": True, "tampered": False}


def test_build_result_sums_scores_and_derives_the_winner() -> None:
    rows = [_row(1, "capture", "bestteam", 20, 5), _row(2, "survival", "imreeyal", 5, 10)]
    result = build_result(
        counted=True, our_group="bestteam", their_group="imreeyal", sub_games=rows,
        game_uid_value="uid-1", timezone="Asia/Jerusalem",
        repos={"bestteam": {}, "imreeyal": {}}, games_played={"bestteam": 1, "imreeyal": None},
        first_meeting=True,
    )
    final = result["final_result"]
    assert final["total_score"] == {"bestteam": 25, "imreeyal": 15}
    assert final["winner_group"] == "bestteam"
    assert final["series_tie"] is False
    # The reward is derived, not claimed: both files must mark the actual
    # winner true, whichever team it is (imreeyal §3.17).
    assert final["diversity_reward_applied"] == {"bestteam": True, "imreeyal": False}
    assert result["game_id"] == "bestteam-vs-imreeyal"
    assert result["groups"] == ["bestteam", "imreeyal"]


def test_a_tied_series_crowns_nobody_and_claims_no_reward() -> None:
    rows = [_row(1, "capture", "bestteam", 20, 5), _row(2, "capture", "imreeyal", 5, 20)]
    result = build_result(
        counted=True, our_group="bestteam", their_group="imreeyal", sub_games=rows,
        game_uid_value="uid-1", timezone="Asia/Jerusalem",
        repos={}, games_played={"bestteam": 1, "imreeyal": None}, first_meeting=True,
    )
    final = result["final_result"]
    assert final["series_tie"] is True
    assert final["winner_group"] is None
    assert final["diversity_reward_applied"] == {"bestteam": False, "imreeyal": False}


def test_a_friendly_never_claims_the_diversity_reward_even_when_won() -> None:
    """SPEC §6.2's counted derivation does not apply to a game that does not count."""
    rows = [_row(1, "capture", "bestteam", 20, 5)]
    result = build_result(
        counted=False, our_group="bestteam", their_group="imreeyal", sub_games=rows,
        game_uid_value="uid-1", timezone="Asia/Jerusalem",
        repos={}, games_played={"bestteam": 1, "imreeyal": None}, first_meeting=True,
    )
    assert result["final_result"]["diversity_reward_applied"] == {
        "bestteam": False, "imreeyal": False,
    }
    assert result["league"] == {"counted": False, "reason": "friendly"}


def test_a_counted_series_also_carries_a_league_block_now() -> None:
    """🐛 Used to be friendly-only, omitted on a counted file to avoid an
    unexplained diff (imreeyal, 16/08) - but yanell11's own counted reports
    carry this block too (24/08), so omitting it became the unexplained diff."""
    rows = [_row(1, "capture", "bestteam", 20, 5)]
    result = build_result(
        counted=True, our_group="bestteam", their_group="imreeyal", sub_games=rows,
        game_uid_value="uid-1", timezone="Asia/Jerusalem",
        repos={}, games_played={"bestteam": 1, "imreeyal": None}, first_meeting=True,
    )
    assert result["league"] == {"counted": True, "reason": "counted"}
    assert result["schema_version"] == "1.1"
    assert "_schema" not in result


def test_consensus_envelope_carries_no_records_and_names_its_own_claim() -> None:
    """yanell11, 22/08: a real reveal and this envelope share one tool, so the
    envelope must be shaped nothing like one — empty records, its own
    `result_claim`, and the settlement hash it exists to carry."""
    envelope = consensus_envelope("thief", "a" * 64)
    assert envelope == {
        "sender": "thief", "records": [],
        "result_claim": "series_consensus", "consensus_sha": "a" * 64,
    }
