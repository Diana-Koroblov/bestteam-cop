"""The reference path's per-sub-game log, and the proof it replays
(`core/report/match_log.py`'s twin, the same way `league_report.py` twins
`core/report/artefacts.py`).

**Why a second log builder rather than the native one.** The two protocols do
not seal the same thing. Natively a step is re-hashed from `STEP_FIELDS` through
`core/crypto/canonical.py`; here each record ships its own whole payload and is
re-hashed as ``canonical(payload) + "|" + nonce`` (`core/compat/sealing.py`).
Feeding reference records to the native verifier does not fail loudly — it
recomputes a different digest for every step and reports forgery against two
honest teams, which is the one outcome M#19 makes unrecoverable. So the log
shape follows the audit that will actually re-verify it.

🐛 **This path filed no log at all until 17/08.** `core/compat/reporting.py`
wrote `result_<game_id>.json` and nothing else, while its own docstring said
"the series is over and its logs are on disk" and `docs/MATCHDAY.md` claimed the
path "files the four artefacts". Both statements were false in the same
direction, so nothing contradicted anything and the gap stayed invisible across
two complete series against imreeyal — neither of which can now be replayed
(M#20), and whose filed `log_files` name files that were never written.

The evidence was never missing, only unwritten: `session.records` holds our own
sealed steps and `session.their_records` holds theirs, both already verified
live. This module writes down what the audit had in its hands.
"""

from __future__ import annotations

from typing import Any

from core.compat import sealing
from core.crypto.audit import AuditResult
from core.report.artefacts import utc_now
from core.shared.version import VERSION

__all__ = [
    "build_sub_game_log",
    "verify_sub_game_log",
    "our_group",
    "our_records",
    "audit_result",
    "record_ok",
]


def build_sub_game_log(
    *,
    game_identifier: str,
    sub_game: int,
    our_group: str,
    their_group: str,
    our_role: str,
    our_records: list[dict[str, Any]],
    their_records: list[dict[str, Any]],
    live_commits: dict[int, str],
    outcome: str,
    config_sha256: str = "",
) -> dict[str, Any]:
    """Assemble ``log_<game_id>_g<NN>.json`` for a finished reference sub-game.

    Args:
        our_records: ``[{"payload", "nonce", "commit"}]`` exactly as sealed and
            revealed. Stored **verbatim** — the audit re-hashes these bytes, so
            a normalised or re-ordered copy would fail every step.
        live_commits: ``{step: commit}`` as their turns actually arrived. This
            is what separates a genuine reveal from one rewritten and re-sealed
            afterwards, and it cannot be reconstructed later from the records
            themselves: a forged record is self-consistent by construction.
        config_sha256: Ties this log to the config snapshot beside it. Without
            it the two are related only by filename, and a filename is not
            evidence.

    Both sides' records are filed, not only theirs. An audit verdict names who
    failed; only the records show *what* was claimed, and a log holding one
    side's evidence lets neither peer re-check the half that matters to them.
    """
    return {
        "game_id": game_identifier,
        "sub_game": sub_game,
        "created_utc": utc_now(),
        "code_version": VERSION,
        "protocol": "reference",
        "roles": {our_group: our_role, their_group: _opposite(our_role)},
        "outcome": outcome,
        "config_sha256": config_sha256,
        "records": {
            our_group: [dict(record) for record in our_records],
            their_group: [dict(record) for record in their_records],
        },
        # Keyed by string, because JSON has no integer keys and a reader that
        # round-trips this file must get back what it wrote.
        "live_commits": {their_group: {str(k): v for k, v in sorted(live_commits.items())}},
        "step_count": {our_group: len(our_records), their_group: len(their_records)},
    }


def verify_sub_game_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Re-verify a written log, and return one verdict per side.

    The inverse of :func:`build_sub_game_log`, and the reason M#20's DoD can be
    demonstrated rather than asserted: build → write → read → verify has to end
    in a pass, or the log is not sufficient whatever it contains.

    Their side is re-checked against the `live_commits` the log carries, so the
    re-verification is the same question the live audit asked. Ours is checked
    for self-consistency only — we never saw our own commits arrive on a wire,
    and inventing a live column for them would be asserting evidence we do not
    have.
    """
    records = payload.get("records") or {}
    live_all = payload.get("live_commits") or {}
    verdicts: dict[str, Any] = {}
    for group, sealed in records.items():
        live = {int(step): commit for step, commit in (live_all.get(group) or {}).items()}
        verdicts[group] = sealing.audit_records(list(sealed), live=live or None)
    return {
        "passed": bool(verdicts) and all(side["passed"] for side in verdicts.values()),
        "sides": verdicts,
    }


def _opposite(role: str) -> str:
    """Return the other side's wire role. Reference vocabulary: police/thief."""
    return "thief" if role == "police" else "police"


def our_group(payload: dict[str, Any]) -> str:
    """Which side of a written log is this peer's own.

    `live_commits` is keyed by *their* group alone — we never saw our own
    commits cross a wire — so the side it does not name is ours. Insertion order
    would give the same answer today and stop giving it the first time the file
    is round-tripped through something that sorts keys.
    """
    groups = list(payload.get("records") or {})
    theirs = set(payload.get("live_commits") or {})
    ours = [group for group in groups if group not in theirs]
    return ours[0] if ours else (groups[0] if groups else "")


def our_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Our own sealed records, in play order."""
    return list((payload.get("records") or {}).get(our_group(payload)) or [])


def audit_result(payload: dict[str, Any]) -> AuditResult:
    """This log's verdict in the shape the Replay App speaks (M#20).

    The Replay App talks `AuditResult`; the reference audit answers per side.
    This is the adapter, and it exists so the viewer never reaches for
    `core.crypto.audit` on a reference log — that path re-hashes `STEP_FIELDS`
    and would report forgery against two honest teams, which is the outcome
    M#19 makes unrecoverable.

    **Both sides are counted**, because both were verified. A reference log
    holds the whole exchange rather than one role's view of it, and reporting
    only our own half would understate what the file actually proves.
    """
    verdict = verify_sub_game_log(payload)
    result = AuditResult()
    for group, side in sorted(verdict.get("sides", {}).items()):
        result.checked += int(side.get("verified_steps", 0))
        result.failures.extend(
            (int(step), f"{group}: record does not re-hash to the commit it revealed")
            for step in side.get("failed_steps", ())
        )
    result.failures.sort()
    return result


def record_ok(payload: dict[str, Any], index: int) -> bool:
    """Whether our *index*-th record re-hashes — the per-row mark in the viewer.

    Checked through `sealing.verify` against the pristine record, never the
    native per-step `verify`: the two protocols hash different things, and
    mixing them is the failure this module was split out to prevent.
    """
    records = our_records(payload)
    if not 0 <= index < len(records):
        return False
    record = records[index]
    return sealing.verify(record.get("payload"), record.get("nonce"), record.get("commit"))
