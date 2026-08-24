# Defect log — resolved, open, and environmental

A running record of every defect found during match preparation and play, what
was done about it, and what remains open. Entries are dated and name the test or
artefact that demonstrates them, so a claim here can be checked rather than
taken on trust.

Open items are listed with the same detail as resolved ones. An issue we have
measured and understood but not yet fixed is more useful written down than
quietly dropped — and a defect log that only lists successes is not a defect
log.

## Fixed

- **The Replay App could not open a league log (24/08).** Every counted match
  runs `protocol=reference`, and `ReplaySession` knew only the native shape, so
  all four opened as `FAILED - empty log, nothing to verify` (M#20). The data
  was never missing — `core/compat/match_log.verify_sub_game_log` already
  verified them — the viewer simply never called it. Fixed by dispatching on
  the log's shape (`is_reference`) in `verify_all`, `steps`, `step_ok` and
  `audit_records`. **Not** by writing native `steps` into reference logs: the
  two protocols hash different things, and feeding one to the other recomputes
  a different digest per row and reports forgery against two honest teams.
  All twelve sub-games of the imreeyal and vibecode series now re-verify off
  disk, both sides of each (`docs/evidence/replay-counted-matches.txt`), and a
  tampered record is still refused — including one rewritten *and re-sealed*,
  which only the `live_commits` binding catches.

- **Silent audit-push failure (17/08).** `core/cli_compat.py`'s outbound
  `submit_audit` call was wrapped in `contextlib.suppress(PeerError)` with no
  retry and no error message. A stale connection (the peer that just won can
  exit the moment it reads its inbox) made the push fail invisibly — our own
  log showed nothing wrong while najamjad recorded `AUDIT SKIPPED`. Fixed:
  extracted to `core.compat.turn_wait.push_audit` (one redial, one retry,
  reports every failure). Proven against real transport code, not mocks, in
  `tests/integration/test_audit_push_recovers.py`. Shipped in commit
  `fix(compat): retry the outbound submit_audit push...`.
- **Two stale test thresholds** in `test_advanced_selfplay.py` and
  `test_advanced_thief_selfplay.py`, both predating the 15/08 barrier-deadlock
  fix (`seal_exits`/`weight_reach` in `game.toml`) and an earlier scent-timing
  fix (TODO 4.1.6). Re-measured and documented rather than silently bumped —
  see those files' own dated comments for the numbers.
- **The advanced Cop self-separated from the advanced Thief, 6/48 openings
  (18/08).** Traced to a specific mechanism, not guessed: the Cop's belief
  stayed 98%+ confident about a cell the Thief had already left (opening
  cop=(2,1)/thief=(4,5), full trace below), and stepping into that
  now-sealed-behind-us pocket blended to a near-certain-capture value on
  belief's confidence alone — `separation_mass` reported nothing stranded,
  because almost all believed mass sat *inside* the trap. Two false starts
  before the real fix: (1) a barrier-placement guard in
  `barrier_policy.rejection_for` — reverted, the wall itself doesn't
  geometrically trap the Cop at the moment it's placed, an escape cell is
  still open; (2) an isolation term inside `evaluate()` alone — barely moved
  the number, because `search._value_of` blends `caught * CAPTURE_VALUE` with
  `(1 - caught) * ahead`, and at `caught = 0.97` the isolation-aware `ahead`
  term is scaled to noise. **Real fix**: a new `CopWeights.isolation` term
  applied to the full blended value in `_value_of` (`police/search.py`), not
  just the leaf evaluation — belief-independent, so a wrong filter cannot buy
  its way past it. Default `weight_isolation = 100.0`
  (`config/police/game.toml`). Confirmed on the full 48-opening benchmark:
  6/48 separations to 0/48, zero regression on every matchup that already
  worked (`test_advanced_league_benchmark.py -m slow`, all re-run clean).
  Unit tests: `test_isolation_*` in `test_cop_evaluation.py`,
  `test_isolation_discounts_a_wall_that_would_leave_a_tiny_pocket` in
  `test_cop_barrier_policy.py`.

  **Scope of this fix, stated so it is not over-read.** Advanced-cop-vs-
  advanced-thief remains 0/48 captures: self-separation was never the main
  cause of that number. The deeper cause is recorded under Open below.

## Open — affects results, not the ability to complete a match

- **`--gui` does nothing during a league match (24/08).** The Live GUI is
  driven by the native turn loop's `play_with_window` (`core/cli_gui.py`),
  which moves the match off the main thread so Tk can own it. The reference
  path never got that treatment, so `core/cli_compat.py` refuses the flag and
  says so rather than opening nothing quietly. Since every counted match is
  reference-protocol, **no league match has ever been watchable live** — the
  belief-map captures in `docs/evidence/` all come from native self-play, which
  is what M#8/Ch. 9.4 actually ask for, so this costs nothing at submission.
  Fixing it means mirroring `play_with_window` for the compat loop, where the
  thread ownership is the difficult part. Deferred deliberately: the change sits
  in the live match path, and the evidence the brief requires is already
  captured by the native route.

- **The advanced Cop still never captures the advanced Thief, 0/48 openings**
  (`test_the_competitive_cell_is_reported_and_not_gated` and
  `test_a_better_cop_is_still_a_harder_cop`, same slow benchmark). Confirmed
  this is a separate, deeper issue from the self-separation bug above — fixing
  that changed 0 of these 48 outcomes. Root-caused on 24/08 — see
  `RESEARCH-REPORT-Performance-Analysis.md` §6.4, which measures the belief
  peak sitting on a non-sealable cell on 100 % of turns while the Thief is on a
  sealable one 83 % of the time. A lost sub-game still completes and audits
  cleanly, so this costs points rather than participation.
- **The advanced Cop is now slower than the baseline Cop against the baseline
  Thief** (`test_the_advanced_cop_captures_faster_than_the_baseline_one`),
  the accepted trade-off from the 15/08 barrier-deadlock fix — see that commit
  and `test_advanced_selfplay.py`'s module docstring. Known and accepted at the
  time the trade was made, not a regression.

## Operational constraints — environment and process, not code defects

- **Playing ANY match — including a rehearsal against the kit's own practice
  bot — overwrites `config/<role>/game.json` in place** with whatever got
  negotiated: `agreed_between`, `map_area`, `decay_model`, all silently
  rewritten to the rehearsal opponent's values. Found live (18/08): a
  sparring-bot rehearsal left `bestteam-thief`'s own `config/thief/game.json`
  declaring `agreed_between: ["bestteam", "sparring-local"]` and
  `decay_model: "multiplicative"` — the REAL opponent (najamjad) needs
  `"najamjad"` and `"subtractive"`. Had this shipped or been left in place, the
  next real match would have negotiated the wrong terms entirely. **Always
  `git diff config/` after any rehearsal, in every repo it touched
  (`p2p-chase` AND both split repos if run from there), before playing the
  real match or running `ship.py`.**

- **Killing and restarting our `core play` processes mid-series desyncs the
  opponent.** Their per-sub-game watchdog keeps running on their own clock; a
  restart on our side doesn't reset it, and they'll report sub-games as
  timed-out or audit-skipped even though we're still genuinely playing. Once
  armed, let a series run to completion rather than restarting to fix
  something else.
- **Free ngrok tunnels fail TLS handshakes under load** (~120 req/min), not a
  clean error — `SSL: UNEXPECTED_EOF_WHILE_READING` on both sides. Repeated
  restarts + curl probing + both sides' retries can trigger this. If it
  happens, stop all processes and allow several minutes before retrying rather
  than restarting into the failure.
- **`scripts/ship.py` / `publish.py` wipes each split repo's `results/`
  folder** with whatever is in `p2p-chase/results/` (which has none of the
  match files, since matches are run from inside `bestteam-cop`/
  `bestteam-thief` directly). Shipping a code change mid-match-prep silently
  deletes any result artifacts sitting only in the split repos. Copy anything
  worth keeping out first.
- **A real match must run from the published repo, not `p2p-chase`.** `core
  play` refuses with "no git remote" from the dev tree — launch from inside
  `bestteam-cop`/`bestteam-thief`, each with its own `.env` (copied, gitignored)
  and its own `uv sync`.
- **Bash + Windows path syntax**: `--out results\` (trailing backslash, copied
  from the PowerShell-flavoured docs) gets swallowed by Git Bash as an escaped
  space, eating the next flag. Use `--out results` (no trailing separator) when
  running through the Bash tool.
- **Orphaned `ngrok.exe` can outlive its Python process.** Check
  `tasklist //FI "IMAGENAME eq ngrok.exe"` and the tunnel's own
  `127.0.0.1:4040/api/tunnels` if a tunnel seems to still be answering after
  you thought you'd stopped it.
