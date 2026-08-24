Subject: bestteam <-> yanell11 - checklist confirmed, built and shipped, one item genuinely on us

Hi Nell, Yanal -

Your diagnosis was right - checked, fixed, shipped. Going through in order.

## 1. games_played - real bug, fixed

You had it: we sent `games_played`, your reader looked for
`counted_games_played`, both at the root. Now sending both spellings, same
integer, verified live:

    counted_games_played = 3   -> {"games_played": 3, "counted_games_played": 3}

## 2. Our commit - a real bug on our side, independent of your diagnosis

You were right that we filed a stale value. Root cause: our own
`--their-commit` operator override was outranking whatever you actually
declared on the wire, unconditionally, on every launch since the 22 August
attempt. Fixed: the wire-declared value now wins; the override is a fallback
for an absent block only. Same class of bug this project already fixed once,
in a different shape.

Also added reading your top-level mirrors (`step0_commit`, `games_played`) if
your nested `identity` block doesn't carry them - so if you start sending
either at the message root, we pick it up even where the nested block is
silent.

## 3. league.authority - dropped

Matches your shape exactly now: `{"counted": ..., "reason": ...}`.

## 4. Arming gate

Confirmed character-for-character: `rmisegal+uoh26finalgame@gmail.com` in
both our configs. No typo.

## 5 & 6. Tie award, rule for the run

Unchanged from before - ADD, and full-series replay on any unsettled
sub-game. Already how our code has always computed it and behaved.

## Ready

Both processes will launch with `--counted`, label `counted-1`, commit
682f5ec91442bb0861af14df6e3c3e8600cbbc23 as our fallback (used only if your
wire stays silent - we'd rather read it live from you). Bringing both up now.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
