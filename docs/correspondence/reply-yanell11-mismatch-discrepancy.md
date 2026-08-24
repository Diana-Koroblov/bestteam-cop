Subject: bestteam <-> yanell11 - three of the five field claims don't match what we actually filed

Hi Nell, Yanal -

Before we build a replay mechanism, we need to reconcile something: we pulled
the exact result_bestteam-vs-yanell11.json we sent (game_uid
b8f8c576-5c08-a5f6-2c4d-d0d97c612b20) and checked it field by field against
what you listed as "our fault, already fixed." Three of the five don't match
what we actually filed:

    field                          you said we filed    what we actually filed
    first_meeting_between_groups   false                 true
    diversity_reward_applied       {both: false}          {bestteam: false, yanell11: true}
    github_commit.bestteam         "unknown"               real hashes on every row
                                                            (f278849f... / 844f10a7...)

Those three were already correct on our side before this message arrived - not
things we're now fixing, things that were never wrong. The two that do check
out: games_played_including_this.yanell11 really was null in our file (which
matches what you said was your side's issue), and our schema_version really is
"1.2" against your "1.1".

We're not saying nothing was wrong - clearly something didn't reconcile, or
this conversation wouldn't be happening. But we want to fix the real mismatch,
not three that don't exist alongside the ones that do. Can you re-send exactly
what you diffed against - the literal file or fields you compared - so we're
looking at the same artifact? It's possible you diffed against an earlier
attempt of ours, or a field got crossed in whichever direction the comparison
ran.

Once we're looking at the same two files, we're glad to work through the
labeled game_id mechanism, the schema_version move, and the league block
question - we want this to be the version that needs no follow-up as much as
you do. We'd rather spend an extra round getting the diff itself right than
build a whole replay off three claims that don't hold up against what we can
directly verify in our own sent artifact.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
