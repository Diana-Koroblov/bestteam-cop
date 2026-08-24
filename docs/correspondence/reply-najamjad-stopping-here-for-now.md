Subject: Re: warm-up postmortem — taking you up on the graceful stop, not the rerun

Naji, Amjad -

Thank you for the real evidence, both directions - this is exactly the kind
of trace we'd want back if the roles were reversed, and we mean that.

On the substance: you're right about #3. We checked our own code, not just
your numbers - turns.py decays the outbound field once before it goes on
the wire (0.90 -> 0.80 under subtractive, matches your reading exactly).
That's a real bug on our side, and worse, we told you the wrong thing in
writing earlier (claimed deposit-then-transmit-then-decay without actually
checking it against the running code). Sorry for that - it was asserted,
not verified, and it should have been the other way around given everything
else we've held ourselves to this league.

#1 we can't fully agree on - our audit reader already discards any envelope
whose sub_game_number doesn't match the window being closed, so "reads from
the front of an undrained queue" isn't quite what our code does - but the
stale per-record labels you'd have to explain some other way, and we're not
going to chase that further right now. #2 we simply have no server-side logs
to confirm or deny - plausible, unresolved either way on our side.

Taking you up on the stop, though, not the rerun: today's our submission
deadline, and the fix is small but it's still a change to core protocol code
- not something we want to touch and re-verify same-day for a match we don't
need (we're already past the counted-match minimum on our side). We'd
rather ship a small, tested fix properly than rush it in the next hour.

If there's a next opportunity after today, we'd genuinely like to try again
- this was the most useful warm-up we've run all league, bugs found on both
sides and nobody's grade was ever on the line for it. For now: nothing was
filed, this whole thing stays a warm-up, and we're stopping here.

Good luck with your own remaining matches.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
