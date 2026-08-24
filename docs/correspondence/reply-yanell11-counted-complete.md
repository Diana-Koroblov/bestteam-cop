Subject: bestteam <-> yanell11 - counted series complete, our report sent

Hi Nell, Yanal -

Clean 6/6 on our side, no technical losses:
1 survival  2 capture  3 survival  4 capture  5 survival  6 capture
yanell11 wins all six, 90-30 aggregate.

mutual_agreement.sha256 = dcf6bf9bdbc7bfe648adcb8d67189829123465d25e338d7f89f3f6e18795c9f6
games_played_including_this: bestteam 4

Our report has already been sent to rmisegal+uoh26finalgame@gmail.com.

One gap: your consensus envelope never landed within our window (our own
internal wait for it is a fixed 20s inside the report step, separate from
--linger, which only keeps the door open for the connection itself - so the
600s linger prevented a transport failure but didn't extend how long we
actively wait to read it). Can you confirm your sha256 for this run in this
thread so we can manually verify it matches ours?

Also noticed: our filed report shows your declared games_played as null on our
side - same class of issue you caught in ours earlier, might be worth checking
on your end.

Good game either way - thanks for the rigor through all of this.

- bestteam
  Itay Malich, Diana Koroblov
  itay.malich2@gmail.com
