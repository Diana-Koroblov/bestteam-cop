# Research report — formalism, strategy, sensitivity, and evaluation

Written for TODO Phase 10 (10.3.1, 10.4.1-10.4.6). Linked from both `docs/README_cop.md` and
`docs/README_thief.md` rather than duplicated into each — the same pattern already used for
`CONTRADICTIONS.md` and `PROMPT_LOG.md`.

---

## 1. Formalism — a decentralised POMDP, not a POMDP

Cop-Thief is a **Dec-POMDP** (decentralised partially observable Markov decision process), not a
single-agent POMDP: two independent decision-makers, each with its own observation function, no
shared controller, and no bird's-eye state either agent's code is ever handed.

| Element | This project |
|---|---|
| State `s ∈ S` | `GameState`: both true positions, the barrier set, the step count. Neither peer's code ever holds a whole `GameState` for the opponent — `core/ui/live_gui.py` is structurally barred from importing anything that would let it (checked by a test that reads its own imports). |
| Actions `a_i ∈ A_i` | Four orthogonal moves + STAY, identical action set for both roles (M#14). The Cop's action space also includes barrier placement, which cop|stay to attach it to. |
| Transition `T(s' | s, a_cop, a_thief)` | Deterministic given both actions — `core/domain/movement.py` + `core/domain/rules.py`. The only stochasticity in the whole system is the nonce (`secrets.token_hex`), which is cryptographic, not part of the game dynamics. |
| Observation `Ω_i(o_i | s', a_i)` | Own position (exact), own barrier count (exact), the **opponent's transmitted scent field** (a lossy, decaying function of the opponent's recent positions — `core/domain/scent.py`), and a natural-language hint (which may lie — M#22). The Thief additionally never observes the Cop's barrier placements except by their effect on legal moves. |
| Belief `b_i(s)` | A discrete distribution over the opponent's position, `core/domain/filter.py`'s `BeliefFilter` — a recursive Bayesian update: predict (diffuse under a movement model) then correct (multiply by the scent-field likelihood), renormalise. This *is* the POMDP belief state, computed independently by each peer from only its own observation stream. |
| Reward `R_i` | Not shared, not zero-sum in general — `core/domain/scoring.py`'s capture/survival/tie/technical-loss table (Appendix F), asymmetric between the two roles by design (a technical loss pays 0 to *both*, so neither side profits from starving the other's clock). |
| Decentralisation | Each of the two roles runs in its **own OS process**, communicating only through the signed, committed wire messages FastMCP carries (`core/infra/mcp_client.py`, `core/infra/mcp_server.py`). There is no shared memory, no referee process, and no message either peer's code can read before it is revealed under commit-reveal — the decentralisation is structural, not simulated by running one program with two objects.

**Why this shape, and not a simpler one.** A single-agent POMDP would need a referee holding the
true state and dictating both agents' observations from it — which is exactly the "no referee"
constraint (M#3, M#4) the project rules forbid. Framing it as Dec-POMDP is not a stylistic choice;
it is the model implied by two independently-executing, mutually-untrusting processes that only
ever see their own history plus what the wire actually carried.

## 2. FastMCP orchestration — the dilemmas and how they were resolved

Running a Dec-POMDP over an unreliable network, with no referee, creates three orchestration
problems the domain layer alone cannot solve:

**Turn management without a shared clock.** Neither peer can be told "it is your turn" by a third
party. `core/runtime/peer_runtime.py` resolves this by making *arrival of a valid reveal* the
event that advances turn state — a message with no matching commit is refused outright, closing
the one channel that would let a peer see the other's move before committing its own.

**Network failure that must never look like a crash.** A dropped connection, a slow DNS resolve
over a tunnel, or a 502 from a still-cold ngrok endpoint are transport facts, not protocol facts.
`core/infra/mcp_client.py` raises one of four typed errors — `AuthError`, `TransportError`,
`DeadlineError`, `RemoteToolError` — specifically so the runtime can retry a transport hiccup and
never retry an expired deadline (retrying past the 30-second response window walks straight into
the watchdog and a technical loss worth 0 to both sides, Appendix F Table 17).

**The Gatekeeper and the Orchestrator are different jobs answering different threats.** The
Orchestrator (`core/runtime/orchestrator.py`) is the single gateway to all five subsystems — no
peripheral module talks to another directly (M#3) — so a bug in, say, hint generation cannot
silently corrupt the belief filter's state. The Gatekeeper (rate limiting, `core/shared/
rate_limiter.py` and friends) is insurance against a burst, not a throughput manager: measured
demand against a local provider is ~0.5 requests/minute against a 30 RPM budget (see `docs/
REFERENCE_PERFORMANCE_NOTES.md` §5), so in ordinary play it never queues. Its value is entirely in
the tail case — a retry storm, or `every_n_steps` dropped to 1 late in the project.

## 3. Strategies implemented

| Layer | What it does | Where |
|---|---|---|
| Belief filter | Recursive Bayesian predict/correct over the opponent's position from the scent field alone | `core/domain/filter.py` |
| Phase classifier | `HUNT` → `SEAL` → `CAPTURE`, switching on entropy (confidence) and the opponent's exit count | `police/phases.py` |
| Barrier-trap planning | Places barriers to drive `exit_count` toward 1 without self-confinement — `core/domain/connectivity.py`'s `region_size`/`exit_count`/`are_connected` exist specifically to tell *separation* (bad — the Cop walls itself out) apart from *confinement* (good — the Thief's region shrinks) | `police/barrier_policy.py`, `core/domain/connectivity.py` |
| Move search | Expectimax over the belief distribution, not a single point estimate — `believed_exit_count()` (added 24/08, in review) averages `exit_count` over the whole posterior rather than just its peak, because the filter's peak can sit a ring inside the true cell for several turns against an edge-hugging Thief, which was silently starving `SEAL` of its trigger | `police/phases.py`, `police/evaluation.py`, `police/search.py` |
| Scent-aware evasion | The Thief reads the Cop's own transmitted field the same way, and avoids paths that would sharpen the Cop's belief | `thief/advanced.py`, `thief/anchor.py` |
| Oracle mode | Cop given the true position (never used in a real match) — measures the *ceiling* a perfect belief would reach, so Phase 4's real performance can be judged against something | `scripts/selfplay.py --oracle` |

## 4. Learning curves — not applicable

**No reinforcement learning is used anywhere in this project** (ADR-002). Both agents are pure
Python search + a hand-built Bayesian filter; the only place a language model appears is generating
the verbal hint text, which never influences movement. There is therefore no training curve to
report. This section exists to say so explicitly rather than by omission, per the excellence
guide's own instruction.

## 5. Screenshots — human step required, not automatable

The M7 milestone screenshots already exist and are real (`docs/evidence/m7-live-gui.png`,
`m7-live-gui-belief.png`, `m7-replay-verified-ok.png`), captured 13/08.

**Opponent disconnect — captured 24/08.** A local two-process drill (`--allow-local-head`, both
roles on `localhost`, no tunnel), one side interrupted mid-series:

- `docs/evidence/edge-case-disconnect-gui.png` — the surviving side's Live GUI, frozen on "YOUR
  TURN" at step 13, the moment the peer stopped answering.
- `docs/evidence/edge-case-disconnect-terminal.png` — the interrupted side's own terminal,
  showing the real error and the resulting clean, persisted `TECHNICAL_LOSS` for each of its
  remaining sub-games: `opponent unreachable: 'receive_reveal' failed: RuntimeError: cannot
  schedule new futures after shutdown`. Both peers correctly declared the working-tree head
  DIRTY too, since this was a deliberate local drill rather than a real match.

The remaining three edge cases were assessed and deliberately not pursued today — P2/P3, and not
worth the remaining time against the deadline:

- A tunnel drop mid-protocol **already has real evidence**, from an actual opponent rather than a
  staged drill: see `docs/correspondence/reply-najamjad-warmup1-findings.md`, 24/08.
- An LLM provider timeout and a malformed hint were scoped (the timeout demo needs a real
  provider — `template`, this project's default, spends no tokens and cannot time out by
  construction, so the demo only means something on a machine running `ollama`) but not captured.
- A hash mismatch was not attempted; it needs a scratch run with a deliberately corrupted payload.

## 6. Parameter sensitivity study

Built `scripts/sweep.py` — a generic one-parameter-at-a-time harness (TODO 10.1.1) on top of the
existing `core.runtime.selfplay` engine already used for A/B testing (3.5). No network, no LLM;
each sweep value is applied to an **in-memory copy** of the loaded config, so the negotiated
contract on disk is never touched — a sweep can run mid-negotiation with a live opponent without
disturbing it.

**Both sweeps below came back flat, and the flat line is itself the finding.** Neither parameter
shows a sensitivity curve, because the Cop's barrier-sealing behaviour is not engaging at all in
this self-play configuration — not because either parameter is irrelevant.

### 6.1 Scent decay rate (ρ)

`AdvancedCop` vs `AdvancedThief`, 25 sub-games per value, ρ ∈ {0.05, 0.10, 0.20, 0.30, 0.40}:

| ρ | Cop win rate | Mean steps |
|---|---|---|
| 0.05 | 0.000 | 35.0 |
| 0.10 | 0.000 | 35.0 |
| 0.20 | 0.000 | 35.0 |
| 0.30 | 0.000 | 35.0 |
| 0.40 | 0.000 | 35.0 |

### 6.2 Barrier quota

Same brains, `max_barriers` ∈ {8, 10, 14, 18, 22} — 14 is the negotiated Appendix F minimum:

| max_barriers | Cop win rate | Mean steps | Mean barriers placed |
|---|---|---|---|
| 8 | 0.000 | 35.0 | 0.0 |
| 10 | 0.000 | 35.0 | 0.0 |
| 14 | 0.000 | 35.0 | 0.0 |
| 18 | 0.000 | 35.0 | 0.0 |
| 22 | 0.000 | 35.0 | 0.0 |

### 6.3 What this actually shows

Every one of 250 self-play sub-games across both sweeps ended `SURVIVAL`, the Cop capturing
zero, and — the part that reframes the whole result — **placing zero barriers in every single
game, regardless of quota.** Confirmed against the project's own unmodified `scripts/selfplay.py`
(not just this sweep harness) to rule out a bug in the sweep code itself:

```
cop_win_rate 0.000   barriers_spent 0   cop_separations 0   10/10 SURVIVAL
```

`cop_separations: 0` rules out the specific self-confinement failure `core/domain/connectivity.py`
was built to catch — the Cop is not walling itself off. It simply never reaches the `SEAL` phase
of `police/phases.py` against this Thief from the negotiated opening, so neither swept parameter
gets a chance to matter: **a flat sensitivity curve here does not mean the Cop is insensitive to
ρ or the barrier quota — it means the phase that would consume them isn't firing.**

This is consistent with, and adds independent evidence to, an in-progress fix already under
review in `police/phases.py` (`believed_exit_count()`), whose own docstring describes the same
symptom from a real league match log: entropy staying under the confidence threshold for a whole
Cop sub-game while barriers stayed at zero throughout. That fix was present (uncommitted, on disk)
for every game measured above and did not on its own change the outcome — either it is
insufficient by itself, or a second, still-unidentified cause sits alongside it. Root-causing
further was deliberately not pursued today: the four already-played league matches cannot be
replayed, and debugging core strategy code same-day as submission was judged not worth the risk
against the time available. Flagged here as a genuine, reproducible open question for the next
iteration rather than smoothed over.

## 7. Nielsen's 10 heuristics — GUI evaluation

Evaluated against the actual `core/ui/live_gui.py` + `widgets.py` implementation, not a mockup.

| # | Heuristic | Verdict | Evidence / mitigation |
|---|---|---|---|
| 1 | Visibility of system status | **Pass** | Status line refreshes every 250 ms (`POLL_MS`): current step, barriers remaining, latest hint, always on screen. |
| 2 | Match between system and the real world | **Pass** | Board rendered spatially (grid, own marker, belief heatmap), hints are plain-language sentences from the same template bank a human would recognise, not codes. |
| 3 | User control and freedom | **Partial, deliberately** | Keystrokes are dropped while a commit is already on the wire (`on_key`, "locked" state) — this is not an omission but the direct consequence of commit-reveal: accepting a late input would let a human change a move the opponent already holds a digest of. Documented as the one place this heuristic is knowingly subordinated to protocol correctness. |
| 4 | Consistency and standards | **Pass** | One rendering convention throughout (`draw_board`/`draw_banner`), same colour/marker semantics between the live GUI and the Replay app (`core/ui/replay.py` reuses the same widgets). |
| 5 | Error prevention | **Pass** | Illegal input is structurally unrepresentable at the boundary the human touches — locked-state key drop, and every domain-level illegal move already raises before it could reach the wire (`core/domain/movement.py`). |
| 6 | Recognition rather than recall | **Partial, deliberately** | No bird's-eye view exists **on purpose** — showing the opponent's true position would violate the Dec-POMDP's own observation constraint (M#8/M#9) and is explicit project disqualification. A human playing along must recall context (recent hints, the shape of the belief heatmap) rather than see it laid out globally. This is the one heuristic the domain rules themselves cap. |
| 7 | Flexibility and efficiency of use | **Not applicable** | This is a spectator/observer GUI for an autonomous match, not an interactive tool with a power-user path — there is no keyboard shortcut layer to evaluate. |
| 8 | Aesthetic and minimalist design | **Pass** | Three widgets total (banner, canvas, one status label); nothing is drawn that is not one of position, barriers, belief, or the latest hint. |
| 9 | Help users recognise, diagnose, and recover from errors | **Pass** | A technical loss prints its cause (which typed error fired) to both the terminal log and, at series end, the filed JSON report — the reason is never silently swallowed. |
| 10 | Help and documentation | **Pass** | `docs/MATCHDAY.md` walks a first-time operator through an entire match end-to-end; the GUI itself carries no in-window help, which is acceptable for an observer-only surface. |

## 8. ISO/IEC 25010 quality characteristics

| Characteristic | Assessment |
|---|---|
| **Functional suitability** | All four terminal conditions (capture, barrier-capture, sealed-in, survival) implemented and unit-tested to 100% coverage on `core/domain`; M1-M8 milestones each independently observed and evidenced. |
| **Performance efficiency** | Local self-play plays dozens of sub-games per second (no network, no LLM — see `scripts/selfplay.py`); the graded path's real bottleneck is the opponent's own response time, not our compute (§1 of `REFERENCE_PERFORMANCE_NOTES.md`). |
| **Compatibility** | Reference-protocol compatibility mode (`core/compat/`) built and used in every league match this session, interoperating with at least three independently-built opponent codebases (imreeyal, yanell11, najamjad) despite each carrying its own protocol quirks. |
| **Usability** | See §7 above (Nielsen). |
| **Reliability** | Every network call carries a deadline; a technical loss zeroes both sides rather than rewarding a timeout-inducing opponent; `--linger` and the audit-retry paths were hardened live against real opponents' transport instability (see `docs/correspondence/`). |
| **Security** | Commit-reveal via SHA-256 over canonical JSON with a 16-byte cryptographic nonce (`core/crypto/commitment.py`); a full secret scanner runs pre-publish and pre-commit, covering both tracked files and git history; `.env` never leaves either machine. |
| **Maintainability** | Hard 150-line ceiling per file (ADR-005), enforced by a standing CI/pre-commit gate, not a guideline; single canonical JSON serialiser project-wide; `core/shared/import_graph.py` proves no peripheral module imports another (M#3). |
| **Portability** | `.gitattributes` pins LF line endings specifically to keep the shared-config SHA-256 identical across Diana's and Itay's different OS line-ending defaults (CONTRADICTIONS C-004); config loading has no OS-specific path assumptions. |

---

*Sweep data in §6 and the accompanying `notebooks/results_analysis.ipynb` were generated
2026-08-24 against commit `<fill from git rev-parse HEAD at submission time>`.*
