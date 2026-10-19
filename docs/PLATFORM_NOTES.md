# Platform notes: telling a Premiere from a real livestream

This kit dates a genuine livestream by when it went live (`release_timestamp`),
everything else by when it was published. Get the Premiere/livestream call wrong
and a video gets dated, durationed, and categorized by the wrong rule — so this
is worth its own writeup, not just the one bullet in the main README.

## The signals that look like they'd work, and don't

A YouTube "Premiere" is a **pre-recorded** upload that the creator schedules to
drop at a set time, with a countdown, concurrent-viewer count, and live chat
during the premiere window. From the outside it is built to look exactly like a
livestream, which is the point — and it is also exactly why several signals that
seem like they should distinguish the two don't:

- **Which channel tab it's discovered on.** This kit treats a channel's
  `/videos`, `/streams`, and `/shorts` tabs as the source of truth for *what a
  channel published* (never a keyword search), and that part holds. But tab
  membership does not tell you *which kind of broadcast it was*: a Premiere can
  surface on the `/streams` tab the same way a real livestream does. The repo's
  own sample data carries exactly this case (`lf003`, see
  [`docs/sample_run/`](sample_run/)) — discovered via `/streams`, and still a
  Premiere underneath.
- **The live-status state machine.** yt-dlp (and the underlying watch-page
  response) exposes a `live_status` field that walks through
  `is_upcoming` → `is_live` → `post_live` → `was_live` / `not_live`. A scheduled
  Premiere walks through states that look the same on the surface — a countdown,
  then "currently playing," then done — which is exactly why this field alone
  isn't the discriminator either.
- **Scheduled-start presence or a countdown/chat UI.** Both exist for Premieres
  specifically because that's the feature doing its job: making a pre-recorded
  drop feel live. Presence of a scheduled time proves nothing about whether the
  underlying video was ever actually broadcast live.
- **Title wording** ("LIVE", "Premiere," a session number). Creators are
  inconsistent, and a title is just a string a human typed — never a safe
  signal to categorize on.

## The one signal that actually works

`was_live`, sourced from the watch page's `isLiveContent` flag
(`videoDetails.isLiveContent` in API terms), is `True` only for a video that was
genuinely broadcast live, and `False` for a Premiere regardless of how it was
scheduled or discovered. It's the one place the platform itself records the fact
that matters — not a derived or inferred state, the literal flag the player
uses to decide whether to show a scrubber for a VOD or a "started N minutes ago"
marker for a broadcast. See [`src/ytdlp_client.py`](../src/ytdlp_client.py) for
the full field map (yt-dlp field → the API field it corresponds to) and
[`src/categorize.py`](../src/categorize.py) for where `was_live` is the hard
branch point, independent of tab or title.

## What breaks if you get it wrong

- **Dating.** A genuine live is dated by `release_timestamp` (when it actually
  went live), because its publish time is often a placeholder posted hours or
  days earlier. A Premiere is dated by publish time instead — its "air time"
  concept doesn't apply the same way. Categorize a Premiere as a live and it
  gets dated (and possibly shifted a day) by a rule meant for a different kind
  of video.
- **Categorization.** A genuine live skips the Shorts/Long-form duration
  thresholds entirely. Run a Premiere through that branch by mistake and a short
  recap video could get waved through as "Live" regardless of length.
- **Marathon splitting.** The one-row-per-named-faculty marathon rule only
  applies to genuine lives above a configured length. Misclassifying a long
  Premiere as live would wrongly split it across presenters named in the title.

## Where this is enforced, not just documented

`categorize.py` checks `raw.was_live is True` as the sole gate into the Live
branch, and separately flags (never silently ignores) the specific
tab-contradicts-signal case: a video discovered on `/streams` with
`was_live=False` gets an informational `premiere-from-streams-tab` flag, but is
still categorized by duration like any other upload — the flag records that the
discovery signal and the classification signal disagreed, not that the
classification is in doubt. `tests/test_pipeline.py::test_premiere_is_not_live`
pins this with a synthetic video that is long, `was_live=False`, and discovered
via `/streams` — on three separate signals it looks like it could be a live, and
the test exists to confirm it still lands as Long-form. `pull.py`'s own gate
(`category: ... is Live but was_live!=True (premiere?)`) catches the same
mistake again at the pipeline level, independent of the categorizer's own logic,
in case the two ever drift apart.
