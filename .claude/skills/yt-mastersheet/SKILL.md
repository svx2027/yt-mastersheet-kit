---
name: yt-mastersheet
description: Run the vertical's YouTube master-sheet tracker (yt-dlp based) for an IST date range and deliver the paste-ready master-sheet blocks plus the executive QA note. Triggers on "master sheet", "yt tracker", "youtube tracker", "pull the week", "master tracker blocks", and requests to turn recent YouTube uploads into the tracker sheet for this vertical.
---

# YouTube master-sheet tracker

Use this to produce the master-tracker paste blocks + QA note for this vertical's
YouTube channel(s) over an IST date range. It is the skill form of the
`/yt-mastersheet` command; the full runbook is `.claude/commands/yt-mastersheet.md`
and the pipeline's rules are in `CLAUDE.md`. Read both before running.

## When to use
- "Make the master sheet for last week", "pull 27th to 29th", "give me the
  tracker blocks", "update the YouTube tracker".
- If setup hasn't happened (`config/vertical.yaml` missing), run `/yt-setup`
  first instead.

## What to do
Run the four phases in order with `.venv/bin/python`, from the repo root:
1. `python -m src.pull --start START --end END`
2. `python -m src.verify --start START --end END`   (halts if not green)
3. `python -m src.format_master --start START --end END`  (refuses unless verify PASS)
4. `python -m src.qa_note --start START --end END`
(or `python run.py START END` for all four).

Then deliver in chat: each `output/START_to_END/blocks/*.tsv` as its own fenced
code block, then `qa_note.txt` as its own code block, then a short summary of
counts and anything flagged for a human.

## Guardrails (see CLAUDE.md for the full list)
- Dates are IST, inclusive; lives are dated by air time, everything else by
  publish time.
- The deliverable is withheld until `verify` is green -- never format or paste an
  unverified pull.
- No individual faculty -> the configured placeholder, never a guess; flagged in
  the QA note.
- Deliver the blocks AND the QA note; the JSON/XLSX files are intermediates.
