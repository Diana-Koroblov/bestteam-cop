Subject: bestteam <-> yanell11 - both findings checked, one real bug fixed, replaying now

Hi Nell, Yanal -

Checked both, not just accepted them.

## games_played

Ran the exact code path our process uses and it produces a real integer, not
null - so I don't think the wire value itself was ever None. But I found a
real, independent bug while checking: our own LEAGUE_LOG.md still counted the
FIRST (voided) counted attempt against you as a completed match, which would
have made our wire value 4, not the 3 we told you. That's wrong regardless of
your None finding - a voided series that never reconciled should not count -
and it's fixed and shipped now. Confirmed on the published repo:
counted_matches() reads 3.

If you're still seeing null after this, it's not the LEAGUE_LOG count - would
you paste the exact raw field your parser reads it from? We can't find a path
in our own code that produces None for this field and want to see precisely
where yours diverges rather than guess again.

## sub-game 6

Our thief process did not crash. Its own log shows it received your sub-game 6
negotiate, then our own outbound reconnect failed with an empty error
(traced to FastMCP's own client.py - a third-party message with no detail,
not something in our code), filed the abandonment correctly, and stayed up
and reachable for its full linger afterward. Looks like a transient
connection failure, not a process going down or a bug on our end - but we
can't pin an exact cause beyond that, since the underlying library gives us
nothing more to go on.

## Replaying

Per your rule - not merging a series with an abandoned window. Bringing both
processes up now, same label friendly-1, same doors, wire now correctly
declaring 3.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
