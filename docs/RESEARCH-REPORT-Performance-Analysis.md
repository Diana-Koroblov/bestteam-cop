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
| Phase classifier | `HERD` → `SEAL` → `SQUEEZE`, switching on entropy (confidence) and the exit count of the belief's peak cell — see §6.4, where that second test turns out never to pass | `police/phases.py` |
| Barrier-trap planning | Places barriers to drive `exit_count` toward 1 without self-confinement — `core/domain/connectivity.py`'s `region_size`/`exit_count`/`are_connected` exist specifically to tell *separation* (bad — the Cop walls itself out) apart from *confinement* (good — the Thief's region shrinks) | `police/barrier_policy.py`, `core/domain/connectivity.py` |
| Move search | Expectimax over the belief distribution, not a single point estimate. A proposed `believed_exit_count()` would average `exit_count` over the whole posterior rather than its peak; it is **not in this tree or the submission**, and §6.4 measures why it would not have been sufficient on its own | `police/evaluation.py`, `police/search.py` |
| Scent-aware evasion | The Thief reads the Cop's own transmitted field the same way, and avoids paths that would sharpen the Cop's belief | `thief/advanced.py`, `thief/anchor.py` |
| Oracle mode | Cop given the true position (never used in a real match) — measures the *ceiling* a perfect belief would reach, so Phase 4's real performance can be judged against something | `scripts/selfplay.py --oracle` |

## 4. Learning curves — not applicable

**No reinforcement learning is used anywhere in this project** (ADR-002). Both agents are pure
Python search + a hand-built Bayesian filter. The only component a language model *could* drive is
the verbal hint text, which never influences movement — and in every match actually played it drove
nothing at all: the committed provider is `template`, which composes hints from fixed phrasings,
and `tokens_total_series` is `0` for both sides in every filed series (§5). There is therefore no
training curve to report. This section exists to say so explicitly rather than by omission, per the excellence
guide's own instruction.

## 5. Screenshots

The brief names two specifically, and both are below — captured 13/08, unmodified.

**Belief heatmap — the Live GUI.** The Cop's posterior over the Thief's position, as the app
itself paints it: heat first, then barriers, then our own marker, so nothing important is buried
(`core/ui/widgets.py`). The peak cell is *outlined* rather than recoloured, so it stays findable
without lying about its intensity relative to its neighbours. This is the filter's own output on
screen, not a reconstruction of it.

![Belief heatmap as drawn by the Live GUI](docs/evidence/m7-live-gui-belief.png)

**`Verified OK` — the Replay App.** A saved `log_<game_id>_gNN.json` re-hashed step by step
against its commitments. The verdict carries in the **exit code** as well as the window — 0 for
`Verified OK`, 1 for `TAMPERED` — so a log can be checked from CI with no display at all:

```
$ uv run python -m core replay results/log_2026-08-15_bestteam-vs-bestteam_40a91bfa_g01.json --headless
Verified OK - 35 steps re-hashed, no mismatch
```

![Replay App reporting Verified OK on a saved log](docs/evidence/m7-replay-verified-ok.png)

The same board without the heatmap layer, for contrast, is at `docs/evidence/m7-live-gui.png`.

**The counted matches replay too — as of 24/08.** They did not before, and the reason is worth
recording. The two protocols seal different things: natively a step is re-hashed from
`STEP_FIELDS` through `core/crypto/canonical.py`, while on the reference path each record ships its
whole payload, re-hashed as `canonical(payload) + "|" + nonce`. The Replay App knew only the
first shape, so every league log — all four counted matches — opened as *"empty log, nothing to
verify"*. `ReplaySession` now dispatches on the shape it was given and routes reference logs to
the audit that actually sealed them; sending them to the native verifier was never an option,
since it recomputes a different digest per row and would report forgery against two honest teams,
the one outcome M#19 makes unrecoverable.

All eighteen sub-games of the three counted series whose artefacts we hold now re-hash off disk,
**both sides of each** (`docs/evidence/replay-counted-matches.txt`). The fourth, yanell11, was run
from the other team member's machine and its artefacts were never filed here — recorded as such
rather than quietly omitted:

```
sub-game 01  exit 0  Verified OK - 70 steps re-hashed, no mismatch
sub-game 02  exit 0  Verified OK - 42 steps re-hashed, no mismatch
...
```

The count is 70 rather than 35 because a reference log holds the whole exchange rather than one
role's view of it. Tampering is still caught in both directions: rewriting one of our own revealed
moves fails the row, and rewriting one of *theirs* and re-sealing it — self-consistent, so
re-hashing alone would accept it — still fails, because the log carries the `live_commits` column
binding each reveal to the commit that actually crossed the wire.

**Opponent disconnect — captured 24/08.** A local two-process drill (`--allow-local-head`, both
roles on `localhost`, no tunnel), one side interrupted mid-series:

- `docs/evidence/edge-case-disconnect-gui.png` — the surviving side's Live GUI, frozen on "YOUR
  TURN" at step 13, the moment the peer stopped answering.
- `docs/evidence/edge-case-disconnect-terminal.png` — the interrupted side's own terminal,
  showing the real error and the resulting clean, persisted `TECHNICAL_LOSS` for each of its
  remaining sub-games: `opponent unreachable: 'receive_reveal' failed: RuntimeError: cannot
  schedule new futures after shutdown`. Both peers correctly declared the working-tree head
  DIRTY too, since this was a deliberate local drill rather than a real match.

**Tunnel drop mid-protocol — real, from an opponent rather than a drill.** Written up in
`docs/correspondence/reply-najamjad-warmup1-findings.md`, 24/08.

**Hash mismatch — captured 24/08.** `docs/evidence/edge-case-hash-mismatch.txt`, with the
rewritten log beside it as `edge-case-hash-mismatch-log.json`. Step 7's revealed move was changed
`E` → `W` — a different but perfectly *legal* move — while `claimed_digest` and `nonce` were left
untouched, which is the shape a peer rewriting history after the fact would produce. The same
binary reads the clean log and the tampered one:

```
Verified OK - 35 steps re-hashed, no mismatch                                    exit 0
FAILED - 1 of 35 steps mismatch; first at step 7: digest does not match the
         revealed move, intent and nonce                                         exit 1
```

The commitment is what makes it detectable: the digest covers move + intent + nonce together, so
altering any one of them after the reveal cannot be made to re-hash. One `TAMPERED` voids the
match (7.24), and because the verdict is in the exit code, CI enforces it with no display.

**Malformed hint — captured 24/08.** `docs/evidence/edge-case-malformed-hint.txt`, eleven real
calls against the shipped parser: empty, whitespace, bearing-free prose, contradictory bearings,
a negation, NUL bytes and ANSI escapes, 24 kB of repetition, Hebrew, and a JSON injection attempt,
against a plain bearing as control. **Nothing raised.** Hostile text is read and never executed,
so a malformed hint costs a belief tilt and never a sub-game; unparseable input collapses to
`direction=None, usable=False`, handing the filter nothing rather than something wrong.

Worth stating because it looks like a defect and is not: `"north east"` is deliberately *not*
usable. `Direction` is `N/S/E/W/STAY` only, so a compound bearing is two claims in one sentence —
either a confused model or a smokescreen — and "unclear" is the honest reading of both.

**LLM provider timeout — not applicable to any match played.** Stated explicitly rather than
omitted, on the same principle as §4: an edge case that cannot arise in the configuration under
test is a finding about the system, not a gap in the catalogue.

No language model was in the loop for any counted match, on **either** side. The evidence is in
the filed artefacts rather than in our word for it:

| Series | `tokens_total_series` |
|---|---|
| imreeyal, 18/08 | `{"bestteam": 0, "imreeyal": 0}` |
| vibecode, 19/08 | `{"bestteam": 0, "vibecode": 0}` |

and the only `model` value any peer ever put on the wire, ours or theirs, is `"none"`. Our
provider selector sits at `[trash_talk] provider` with the committed value `template` (C-012,
`PARAMETERS.md` §5.2) — it composes hints from fixed phrasings, spends no tokens, and issues no
network call that could time out. There is no code path from a match turn to a provider request,
so a provider timeout has no way to reach the game loop.

Demonstrating one would mean reconfiguring a peer onto `ollama` and staging a failure the played
system cannot experience — evidence about a different configuration than the one that produced
every result in this report. The four cases above are the four that can actually occur.

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

This is consistent with, and adds independent evidence to, an in-progress fix under review in
`police/phases.py` (`believed_exit_count()`), whose own docstring describes the same symptom from
a real league match log: entropy staying under the confidence threshold for a whole Cop sub-game
while barriers stayed at zero throughout. That fix was present (uncommitted, on disk) for every
game measured above and did not on its own change the outcome — either it is insufficient by
itself, or a second cause sits alongside it.

**§6.4 answers that question.** It was left open when the sweeps were written; instrumenting the
phase machine settled it the same day.

### 6.4 Root cause — the belief peak is never on a sealable cell

Measured against the **shipped** `police/phases.py`, the one in this tree and in the submission —
`believed_exit_count()` is *not* present in it, so this is the behaviour as graded.

`classify()` reaches `SEAL` only if `exit_count(target, …) <= threshold`, where `target` is
`observation.most_likely_opponent()` — the single peak of the belief. Wrapping `classify` to
record its own inputs, over 10 self-play sub-games (350 classified turns, 360 thief positions):

| exit count | at the belief **peak** | at the **true** Thief |
|---|---|---|
| 2 (corner) | 0 | 60 |
| 3 (edge) | 0 | 240 |
| 4 (interior) | **350** | 60 |

**The true Thief stands on a sealable cell — 3 exits or fewer — 83 % of the time. The belief peak
reads 4 exits on 100 % of turns and has never once been sealable.** With a flee-greedy profile
the threshold tightens to `seal_exits - 1 = 3`, so the comparison `4 <= 3` is false on every turn
of every game. `SEAL` fired twice in 35 turns of the traced game, and both times only through the
`MovementStyle.ORBITER` clause that bypasses the exit test entirely. The phase that spends
barriers is unreachable by its own arithmetic, which is why both sweeps in §6.1–6.2 are flat and
why `barriers_spent` is 0 regardless of quota.

**Why the peak sits inside.** §4 of the notebook runs the shipped filter over a sub-game twice.
Fed a single fresh scent deposit, the posterior peak lands on the true cell **36 of 36 steps**.
Fed the field a match actually transmits — the Thief's accumulated trail, decayed history merged
with this turn's emission — it lands there **2 of 36**, and entropy *climbs* from 0.35 to 1.58
bits over the sub-game instead of falling. The trail is loudest where the Thief has been *most
often*, which is the interior of its patrol, not the edge cell it currently occupies. The filter
is not broken; its evidence is ambiguous by construction, and the ambiguity is biased inward.

![Cop's belief posterior against the Thief's true cell, for both inputs](results/fig_belief_convergence.png)

**Why `believed_exit_count()` did not fix it.** That change replaces the peak with a
probability-weighted exit count across the whole belief. But the whole belief is displaced onto
the same interior ridge — it is the distribution that is wrong, not merely the statistic taken
from it — so averaging over it lands interior too. This is the second cause the sweep write-up
suspected, and it explains the measurement honestly reported there: a real improvement to the
statistic, with no effect on the outcome.

The fix implied by the data is to stop asking the peak, or the mean, where the Thief is, and to
score the *sealability of the region* the belief mass covers, or to discount the trail's history
against its most recent deposit. Both are design changes, not one-line edits, and neither was
attempted the day of submission — a played match cannot be *re-run* against the opponent that
played it, so no fix could be scored against the four results that matter, and rewriting the
Cop's phase logic same-day was judged the larger risk. (Their logs re-verify off disk, §5; that
proves the records are sound, not that a strategy change can be measured against them.) Recorded here as a measured, reproducible
root cause rather than an open question.

### 6.5 Corroboration from league play

The sweeps above are self-play. The counted matches are the independent check, and they agree.
Two series survive de-duplication on `game_uid` — imreeyal (18/08) and vibecode (19/08), six
sub-games each, roles alternating three and three:

| Opponent | as Cop | as Thief |
|---|---|---|
| imreeyal | 0 / 3 | 2 / 3 |
| vibecode | 0 / 3 | 0 / 3 |
| **total** | **0 / 6** | **2 / 6** |

![Win rate by opponent and role, counted series only](results/fig_winrate_by_opponent_role.png)

Twelve sub-games is a small sample and the Thief's 2–0–0–0 split across two opponents is well
within noise. **The Cop's 0 of 6 is not.** It is the same number the 250-game self-play sweep
returned, arrived at against two different real opponents on a public network rather than against
our own Thief in-process — and §6.4 gives the mechanism that produces it in both settings. Three
measurements, one cause.

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

## 9. The deception detector was never exercised

`core/domain/reliability.py` keeps a Beta posterior over "does this opponent's hint match what
their scent then did", started at 1/1 so an unchecked opponent reads as a coin toss rather than a
saint. `claim_matches_scent` returns `None` — excluded, not scored as a lie — when a claim cannot
be verified, so a stationary opponent cannot accumulate a false reputation.

**It works.** Driven through the shipped class with a scripted opponent, honest twelve turns then
lying eighteen, the coefficient climbs 0.66 → 0.92 and falls to 0.41; the decayed variant (γ=0.85),
which is what the bluff policy actually reads, crosses below 0.5 within three turns of the switch
and bottoms at 0.05.

**It never ran in anger.** Across every counted-match log:

| Speaker | hints sent | claims we could check |
|---|---|---|
| imreeyal | 193 | **0** |
| vibecode | 0 | 0 |
| bestteam (us) | 335 | 51 |

![Reliability coefficient over time, and what opponents gave it to score](results/fig_reliability_over_time.png)

imreeyal's hints named invented landmarks — "Grand Central", "Brooklyn Bridge" — and `Direction`
is `N/S/E/W/STAY`, so not one of their 193 sentences yielded a bearing to test. vibecode sent no
hints at all. The detector was never exercised in a real match, and **not because opponents were
honest**: a private landmark vocabulary is unfalsifiable by construction, and an unparseable claim
cannot be caught lying. This is the same failure mode our own `fix(llm): forbid invented landmarks`
commit addressed on our side, for the same reason — they act as a private codebook.

The conclusion is about negotiation, not parsing: a shared hint vocabulary belongs in the pre-match
agreement alongside the decay model and the coordinate convention. No cleverer parser recovers a
bearing from a sentence that never encoded one.

---

*Sweep data in §6 and the accompanying `notebooks/results_analysis.ipynb` were generated
2026-08-24 against commit `<fill from git rev-parse HEAD at submission time>`.*
