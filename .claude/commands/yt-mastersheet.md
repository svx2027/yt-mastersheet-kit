---
description: Run the vertical's YouTube tracker for an IST date range and deliver the paste-ready master-sheet blocks plus the executive QA note. Args: START END (YYYY-MM-DD, inclusive). No args = propose the next window.
argument-hint: [start YYYY-MM-DD] [end YYYY-MM-DD]
---

Run this kit's tracker for the IST window **$1 to $2** and deliver the
master-sheet paste blocks plus the executive QA note. `CLAUDE.md` in this folder
is the source of truth -- read it first.

- Python: `.venv/bin/python` in this repo. Data source: yt-dlp (no API key).
- If `config/vertical.yaml` is missing, this kit isn't set up yet -- run
  `/yt-setup` first, don't try to pull.
- **Deliverable: the tab-separated master-sheet blocks (one per channel per type)
  AND the executive QA note, printed as fenced code blocks in chat.** The
  rows.json / XLSX / other JSON files are intermediates, not the output.

Do this in order:

1. **Pre-flight.** If no dates were given, look at the `output/` folders, take the
   latest window's end date, propose START = that date + 1 and END = yesterday
   (IST), state the proposed window, and wait for a yes. Validate `$1`/`$2` are
   `YYYY-MM-DD`, `$2 >= $1`, range <= 90 days. Note if the window overlaps an
   existing `output/` folder (a re-pull that supersedes those dates).

2. **Pull.** `.venv/bin/python -m src.pull --start $1 --end $2`
   Discovers via the channel's own tabs (yt-dlp), dates lives by air time and
   everything else by publish time (all IST), rounds Live/LF duration up to whole
   minutes, excludes not-yet-aired / still-airing placeholders, splits marathons,
   and runs the gates. It halts on any gate failure. Only a genuinely quiet week
   justifies re-running with `--allow-anomaly` (downgrades ONLY the baseline gate);
   never use it to wave through a boundary/duplicate/category failure. Don't paper
   over a halt -- read the message and fix the cause.

3. **Verify (deliverable withheld until green).**
   `.venv/bin/python -m src.verify --start $1 --end $2`
   Independent re-derivation on a separate code path with fresh yt-dlp fetches,
   plus a re-walk that confirms nothing in-window is missing. Halts (exit 2) on
   any mismatch and writes `verify_report.json`. Do not proceed past a red verify.

4. **Format.** `.venv/bin/python -m src.format_master --start $1 --end $2`
   Refuses to run unless verify said PASS. Resolves Faculty (roster + aliases;
   the configured placeholder when no individual is identifiable -- never blank,
   never guessed, never written into a Shorts topic), Subject (keyword rules then
   per-faculty default, blank + flagged if neither), and cross-channel Live dedup
   (only same date + same "Session N"). FACULTY_EMAIL is left BLANK: the tracker
   never populates it (the master sheet supplies that column), so keep
   `inputs/faculty_emails.csv` empty and never print an email address. Asserts tab counts itself (Live/LF = 10 tabs, Shorts = 7)
   and halts on a mismatch, so you don't hand-verify counts -- but read each block
   once before pasting it.

5. **QA note.** `.venv/bin/python -m src.qa_note --start $1 --end $2`
   Plain-language note built from artifacts on disk: videos to verify, rows tagged
   with the no-faculty placeholder, and other flags.

6. **Deliver in chat, in this order:**
   - Each `output/$1_to_$2/blocks/<Bucket>.tsv` as its own fenced code block,
     clearly labeled (empty buckets: say "empty this window", don't paste blanks).
   - The QA note (`qa_note.txt`) as its own fenced code block.
   - A short summary: row counts, anything flagged for a human, and (if it
     overlaps a prior window) which dates it supersedes.

7. **Offer to improve.** If a flag recurs (a faculty who's never detected, a
   subject keyword that keeps missing), offer to add it to `inputs/` so the next
   run resolves it automatically. That's how the kit gets better over time.
