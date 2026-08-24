Subject: bestteam <-> najamjad - warm-up ran, found a real bug on your audit side before we go further

Hi Naji, Amjad -

Doors were up, negotiation worked, sub-games actually played - but we can't
call this warm-up clean, and we'd rather show you the evidence now than run
a counted series on top of it.

======================================================================
WHAT WE SAW
======================================================================
    sub-game 1  (us cop, you thief)   timeout - no turns, no audit ever
                                       arrived from your side
    sub-game 2  (us thief, you cop)   clean - audit passed
    sub-game 3  (us cop, you thief)   same pattern as sub-game 1 - repeated
                                       re-negotiate, no turns. We stopped it
                                       ourselves partway through its own 900s
                                       wait once the pattern was clear, rather
                                       than grind out the full budget on 3 and
                                       then 5 too - so we don't have a formal
                                       timeout line logged for it, but nothing
                                       arrived in the time we did wait.
    sub-game 4  (us thief, you cop)   audit FAILED - every step
    sub-game 5                        never reached
    sub-game 6  (us thief, you cop)   audit FAILED - every step

======================================================================
ROOT CAUSE, NOT A GUESS - WE TRACED IT IN THE RAW LOGS
======================================================================
Not accusing anyone of tampering. We independently recomputed your
commit-reveal hashes by hand:

  - Every record you revealed for sub-games 4 and 6 is internally
    consistent (commit_of(payload, nonce) == commit, all 32/35 records).
  - But every one of those records carries the WRONG sub-game number
    in its own payload: the reveal you sent for sub-game 4's audit is
    labeled "sub_game": 2 in every record - it's sub-game 2's move log,
    resent. The reveal for sub-game 6 is labeled "sub_game": 4 - the
    previous sub-game's log, resent again.

So your audit reveal looks one sub-game behind, consistently. That reads
like your side isn't rebuilding/clearing the records buffer between
sub-games - each audit send reuses the prior sub-game's list. That's why
every step fails against what actually arrived live during THIS sub-game:
you're not sending this sub-game's data at all.

Separately, sub-game 1 (and now 3) look like a different issue - your
thief process never engaged at all, not a stale-reveal problem. Might be
worth checking whether your thief process only serves negotiate but never
receive_turn on some sub-games, or whether it's tied up.

======================================================================
WHAT WE'D LIKE TO DO
======================================================================
Nothing filed as a result yet - we're holding this as a warm-up, not
touching the counted series. Once you've had a look, we're glad to run a
fresh, full 6-sub-game warm-up from scratch. No pressure on timing - we'd
rather get a clean one than rush a counted match that voids itself the
same way our previous one with another team did.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
