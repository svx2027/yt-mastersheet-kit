# Sample run

A full run of the four-phase pipeline (`pull` -> `verify` -> `format_master` ->
`qa_note`), output committed here so you can see the shape of a real delivery
without running anything yourself first.

## What this is, and what it is not

This is **not** a live pull from a real YouTube channel. The environment this
kit's automation runs in has no outbound network access to youtube.com, so it
cannot fetch a real channel here. Rather than fake the output by hand-writing
plausible-looking text, this sample was produced by running the **real,
unmodified pipeline code in `src/`** -- the exact same `pull.py`, `verify.py`,
`format_master.py`, `categorize.py`, `faculty.py` your own run uses -- against
a small, fixed, openly synthetic video catalog, through a stand-in for yt-dlp
(`generate/fake_yt_dlp.py`) that answers the same command-line calls the real
`yt-dlp` would, from that local catalog instead of the network.

The vertical is the same fully fictional "Demo MATH Prep" (`@MathPrepDemo`)
identity already shipped in `config/vertical.example.yaml` and
`inputs/*.example.*` for the Quickstart -- nothing new was invented for this
sample, and nothing here is real YouTube data, a real channel, or a real
person.

## Why this is worth shipping instead of skipping

`src/` never changed to produce this. The only substitution is the data
source: 14 synthetic videos in `generate/build_catalog.py`, deliberately
covering most of the rules this kit exists to enforce, so the sample QA note
is not a trivial all-clear:

- **Air-time dating, not publish-time**: `live001`'s placeholder was posted
  30-Jun but it aired 01-Jul; the row lands on 01-Jul.
- **Marathon splitting**: `live002` (240 min, two faculty named in the title)
  becomes two rows, Arjun Rao Sir and Devika Menon, 120 minutes each.
- **No-individual-faculty placeholder**: four separate cases (a live with no
  name, a quiz with no name, a premiere that names no presenter, and a Short
  caught by a brand-content phrase) all land on `Channel Official`, listed in
  the QA note for a human to resolve.
- **Ambiguous multi-faculty (not a marathon)**: `lf005` names two faculty in a
  non-marathon long-form video and is tagged `NEEDS-MANUAL-SPLIT` rather than
  guessed.
- **Premiere vs. live**: `lf003` is discovered on the `/streams` tab but
  `was_live=False`, so it is correctly categorized Long-form (never Live, one
  of the four placeholder cases above since it names no presenter) and carries
  an informational flag, not a hard failure.
- **Not-yet-aired, excluded and queued**: `live004` (`is_upcoming`) is excluded
  and listed under "videos to verify," never written with a fake date.
- **Fetch-failed, excluded and queued, never silently dropped**: `live005` is
  discovered but its detail fetch is made to fail on purpose; it is recorded as
  a `fetch-failed` exclusion and appears in the QA note, exactly like a real
  429/throttle would be handled.
- **The 181-299s gap**: `gap001` (220s) is excluded as `gap-181-299s`.
- **`verify.py` genuinely re-derives and agrees**: `verify_report.json` here
  was produced by `verify.py`'s own independent re-implementation re-fetching
  every placed id (through the same stand-in) and re-walking every channel
  tab -- it is not a copy of `pull.py`'s output.

## The QA note itself

The exact text `qa_note.py` wrote for this window, so the delivered shape is
visible without opening `output/2026-07-01_to_2026-07-07/qa_note.txt`
yourself:

```
QA NOTE -- Demo MATH Prep -- 2026-07-01 to 2026-07-07
6 item(s) need a human to check on YouTube (2 possibly missing or uncertain, 4 unnamed faculty).

A) VIDEOS TO VERIFY (possibly missing, not yet aired, or uncertain)
1. (not yet dated) | Main | (fetch failed)
   Why: its YouTube page could not be read this run (network/throttle) -- re-pull to capture it
   Link: https://www.youtube.com/watch?v=live005
2. (not yet dated) | Main | Upcoming: Geometry Marathon (Scheduled)
   Why: not yet aired -- re-pull this window once it airs
   Link: https://www.youtube.com/watch?v=live004

B) ROWS TAGGED "Channel Official" (no individual faculty could be identified)
Open each link and tell us the real faculty, or confirm it is genuinely brand/institute content with no single presenter.
1. 05-Jul-2026 | Main | Live | Doubt Clearing Session
   Link: https://www.youtube.com/watch?v=live003
2. 07-Jul-2026 | Main | Long-form | Fun Friday Quiz Round 12
   Link: https://www.youtube.com/watch?v=lf004
3. 06-Jul-2026 | Main | Long-form | Full Mock Test Premiere: Time and Work
   Link: https://www.youtube.com/watch?v=lf003
4. 05-Jul-2026 | Main | Short | Orientation Session Walkthrough
   Link: https://www.youtube.com/watch?v=sh003

C) OTHER ITEMS FLAGGED THIS RUN
- Live live002: subject left blank, no keyword or faculty default matched: 'Weekly Full Day Marathon: Arjun Rao Sir and Devika Menon'
- Live live003: subject left blank, no keyword or faculty default matched: 'Doubt Clearing Session'
- LF lf004: subject left blank, no keyword or faculty default matched: 'Fun Friday Quiz Round 12'
- LF lf005: multiple faculty named, cannot attribute -- manual split: 'Combined Revision: Arjun Rao Sir and Devika Menon'
```

Sections A and B are the two "6 item(s)" this window's summary line counts (2
plus 4); section C is a separate, non-counted log of every subject-parsing
and multi-faculty case the run flagged along the way, including the two rows
that also appear in section B.

## Reproducing it yourself

```bash
cd yt-mastersheet-kit
python3 -m venv .venv && source .venv/bin/activate
pip install pyyaml openpyxl   # skip yt-dlp; the stand-in below replaces it

cp config/vertical.example.yaml config/vertical.yaml
cp inputs/faculties.example.csv inputs/faculties.csv
cp inputs/aliases.example.csv inputs/aliases.csv
cp inputs/faculty_emails.example.csv inputs/faculty_emails.csv
cp inputs/subjects.example.yaml inputs/subjects.yaml

python3 docs/sample_run/generate/build_catalog.py   # writes generate/catalog.json
chmod +x docs/sample_run/generate/fake_yt_dlp.py
mkdir -p /tmp/fake-ytdlp-bin
ln -sf "$(pwd)/docs/sample_run/generate/fake_yt_dlp.py" /tmp/fake-ytdlp-bin/yt-dlp
export PATH="/tmp/fake-ytdlp-bin:$PATH"

python3 -m src.pull          --start 2026-07-01 --end 2026-07-07 --no-xlsx
python3 -m src.verify        --start 2026-07-01 --end 2026-07-07
python3 -m src.format_master --start 2026-07-01 --end 2026-07-07
python3 -m src.qa_note       --start 2026-07-01 --end 2026-07-07
```

This regenerates `output/2026-07-01_to_2026-07-07/` locally, byte-for-byte the
same shape as what is committed under `docs/sample_run/output/` here (the JSON
files' key order matches; only re-run timing is not pinned).

To run it for real: skip `generate/` and the stand-in entirely, install the
real `yt-dlp` (`pip install -r requirements.txt`), and point
`config/vertical.yaml` at your own channel.

## What's here

```
generate/
  build_catalog.py   -- writes the synthetic catalog (14 videos, see above)
  fake_yt_dlp.py      -- stands in for the real yt-dlp binary, answers from the catalog
output/2026-07-01_to_2026-07-07/
  tracker_v1_..._raw.json   -- canonical rows (pull.py)
  verify_report.json        -- verify.py's independent re-derivation, PASS
  blocks/*.tsv               -- the paste-ready tracker blocks (format_master.py)
  qa_note.txt                 -- the executive QA note (qa_note.py)
  run_summary.json, exclusions.json, pending_reair.json,
  placeholder_rows.json, flagged_edge_cases.json, dropped_rows.json
```
