"""Unit tests for the conformance hardening added to core/compat/wire.py and
core/compat/sealing.py (imreeyal §3.3, §3.10 — timestamp validation, the
reference's police/cop vocabulary split, and live-commit audit binding).

Split out of test_compat_protocol.py to stay under the 150-line file cap.
"""

from __future__ import annotations

import pytest

from core.compat import sealing
from core.compat.wire import TurnMessage, peer_identity, wire_role

PAYLOAD = {"step": 3, "move": "N", "position": [1, 2]}


def test_an_empty_timestamp_is_refused_before_any_state_change() -> None:
    """Decorative-looking, load-bearing in practice (league kit turn_message.json)."""
    data = {"step": 1, "sender": "thief", "hint": "", "smell_grid": {}, "commit": "c" * 64,
            "timestamp": ""}
    with pytest.raises(ValueError, match="timestamp"):
        TurnMessage.from_dict(data)


def test_a_missing_timestamp_is_also_refused() -> None:
    data = {"step": 1, "sender": "thief", "hint": "", "smell_grid": {}, "commit": "c" * 64}
    with pytest.raises(ValueError, match="timestamp"):
        TurnMessage.from_dict(data)


def test_wire_role_speaks_their_vocabulary_for_cop_and_passes_thief_through() -> None:
    assert wire_role("cop") == "police"
    assert wire_role("thief") == "thief"


def test_audit_records_binds_a_reveal_to_what_actually_arrived_live() -> None:
    """3.10: a record must match the commit that arrived live, not only itself."""
    sealed = sealing.seal(PAYLOAD)
    record = {"payload": PAYLOAD, **sealed}
    live = {PAYLOAD["step"]: sealed["commit"]}
    assert sealing.audit_records([record], live=live)["passed"]


def test_audit_records_fails_a_record_rewritten_after_the_fact() -> None:
    """Internally self-consistent (commit_of(payload, nonce) == commit) is not
    enough: the commit must also be the one that crossed the wire during play."""
    original_nonce = "1" * 32
    original_commit = sealing.commit_of(PAYLOAD, original_nonce)
    rewritten_nonce = "2" * 32
    rewritten_commit = sealing.commit_of(PAYLOAD, rewritten_nonce)
    record = {"payload": PAYLOAD, "nonce": rewritten_nonce, "commit": rewritten_commit}
    live = {PAYLOAD["step"]: original_commit}
    verdict = sealing.audit_records([record], live=live)
    assert not verdict["passed"]
    assert verdict["failed_steps"] == [PAYLOAD["step"]]


def test_audit_records_does_not_fail_a_step_never_seen_live() -> None:
    """A step-0 system-spec/declaration record exists only in the closing
    audit and never rides a live turn — found live against the league
    conformance kit's sparring peer, whose log carries exactly this record.
    "Never seen live" must not read the same as "seen and different"."""
    declaration = {"step": 0, "type": "system_spec"}
    sealed = sealing.seal(declaration)
    record = {"payload": declaration, **sealed}
    live = {3: "some-other-steps-commit"}  # step 0 is simply absent
    verdict = sealing.audit_records([record], live=live)
    assert verdict["passed"]
    assert verdict["failed_steps"] == []


def test_audit_records_without_live_tracking_still_only_checks_self_consistency() -> None:
    """Backward compatible: a caller that never tracked live commits (``live=None``,
    the default) gets exactly the old self-consistency check."""
    sealed = sealing.seal(PAYLOAD)
    record = {"payload": PAYLOAD, **sealed}
    assert sealing.audit_records([record])["passed"]


def test_peer_identity_fills_a_gap_the_nested_block_left() -> None:
    """yanell11, 24/08: reading only `message["identity"]` missed every
    top-level mirror a peer sends, even after we started sending our own."""
    message = {"identity": {"group_id": "yanell11"}, "step0_commit": "c" * 40,
               "games_played": 3}
    identity = peer_identity(message)
    assert identity["group_id"] == "yanell11"
    assert identity["github_commit"] == "c" * 40
    assert identity["counted_games_played"] == 3


def test_peer_identity_prefers_the_nested_block_when_both_are_present() -> None:
    message = {"identity": {"github_commit": "nested" + "a" * 34}, "step0_commit": "top" * 13}
    assert peer_identity(message)["github_commit"] == "nested" + "a" * 34


def test_peer_identity_accepts_a_numeric_string_count() -> None:
    """A peer that stringifies the integer must not read as unclaimed."""
    assert peer_identity({"games_played": "3"})["counted_games_played"] == 3


def test_peer_identity_leaves_a_boolean_count_unclaimed() -> None:
    """`True` is an `int` in Python; reading it as 1 would invent a claim."""
    assert "counted_games_played" not in peer_identity({"games_played": True})
