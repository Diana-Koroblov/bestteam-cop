Subject: bestteam <-> yanell11 - one field we need to double check before we call this fully settled

Hi Nell, Yanal -

Match is complete and filed, sha256 confirmed on our side - not raising this
to reopen anything, just flagging before you compare files.

We read your `step0_commit` and filed it as your git commit hash, per your own
description. Looking at what we actually filed:

    sub-game 1: 6cb3aecf92f89b9849a251ce6b4043e6bce696601185657db84e9091be678d79
    sub-game 3: e4ba661327721873d64da15d04d8c84e6f463cae37f78accb06e6bcdd8e8e1d3
    sub-game 5: 06fd0006abfb829cf22e025306c0f8c9066e853b059ab5d412bf853b607fe76a

These are 64 hex characters and different on every sub-game. A git commit is
40 hex (SHA-1) and does not change mid-series unless you pushed between
sub-games. This looks like a sealed commitment hash (SHA-256, per sub-game's
step-0 record), not your repository's HEAD.

Not a scoring problem - github_commit is outside the settlement hash, so this
does not touch mutual_agreement.sha256 or the result itself. But we'd rather
tell you now than have it surface as a "mismatch" that isn't one: is
step0_commit meant to be your git HEAD, or the seal of your step-0 record? If
it's the latter, we misread your spec and will stop filing it as
github_commit. If it's meant to be your HEAD and it's coming out wrong on your
side, that's worth knowing before your next counted series too.

Everything else stands as filed - this is the one loose thread.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
