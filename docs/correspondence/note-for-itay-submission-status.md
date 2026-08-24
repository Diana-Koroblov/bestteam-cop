Subject: Submission status + what's on you before the deadline

Itay -

Status as of today (24/08, submission deadline): 4 counted matches banked
(imreeyal, vibecode, nis-yar1, yanell11), both split repos tagged
v1.0-submission and public, all tests green (1741 unit + 92 integration),
Phase 10 (research report, sweep data, notebook) written and pushed.

Three things that are on you specifically:

1. YOUR police/phases.py FIX - your call, not made yet
   You added `believed_exit_count()` to police/phases.py (probability-
   weighted exit count instead of the belief peak, to fix SEAL never
   firing). It's sitting UNCOMMITTED in the monorepo working tree right
   now - I've kept it out of every publish so it doesn't accidentally ship
   half-finished. It passes its own tests cleanly (12/12, 98% coverage).

   But: I ran a fresh self-play sweep today (AdvancedCop vs AdvancedThief,
   250 games total, sweeping both scent decay and barrier quota) WITH your
   fix present on disk, and the Cop still won 0% of the time and placed 0
   barriers in every single game. So either your fix isn't sufficient by
   itself, or there's a second cause alongside it. Written up honestly in
   docs/RESEARCH-REPORT-Performance-Analysis.md S6.3 if you want the full
   data.

   Decide: (a) it's done, commit it as-is - it's a real improvement even if
   it doesn't fully solve the problem, (b) you want to dig further first,
   or (c) leave it out and I'll leave it uncommitted. Whatever you decide,
   just tell Diana or push it yourself - either of you can commit it.

2. YOUR MOODLE SUBMISSION - separate from Diana's, mandatory
   TODO 11.2.5 (M#44): you have to submit on Moodle yourself, separately
   from Diana. No individual submission = no grade for you specifically,
   regardless of what she submits. Both repo links + team ID `bestteam` go
   in the form; self-grade on code quality only, never on league results
   (M#55).

3. Optional, not blocking: if you want a quick, real screenshot for the
   edge-case catalogue (LLM timeout), Diana's machine can't produce a
   meaningful one - she runs `template` (0 tokens, can't time out), you run
   `ollama`. Not required, we already have 2 of 5 edge cases covered with
   real evidence. Skip unless you have a spare few minutes.

Everything else on the TODO list is closed out or was never actually
blocking. Ping Diana if anything above doesn't match what you already know.

- Diana (drafted with Claude's help)
