---
description: One-time setup for this YouTube channel tracker kit. Installs the tools, then interviews you for your vertical (exam, channel, faculty, subjects, cadence) and writes your config. No coding needed.
---

You are setting up this kit for a NEW vertical. The person running you may not be
technical. Be a patient installer: explain each step in plain language, ask ONE
thing at a time in normal chat (never a popup/menu), wait for the answer, and
never assume. Read `CLAUDE.md` in this folder first so you respect the pipeline's
rules. Do the steps below in order.

## 0. Orient
- Confirm the working directory is the kit folder (it has `src/`, `config/`,
  `inputs/`, `run.py`). If not, ask the person to open a terminal/Claude in the
  folder they unzipped.
- If `config/vertical.yaml` ALREADY exists, tell them setup was done before and
  ask whether to (a) reconfigure from scratch, or (b) just add/adjust faculty or
  subjects. Don't overwrite their file without a clear yes.

## 1. Tools (do this before any questions)
Goal: a working Python virtual environment with the three dependencies, and
yt-dlp available. Check, then fix only what's missing. Explain like they've never
used a terminal.

1. Python: run `python3 --version`. Need 3.10+. If missing, tell them how to get
   it for their computer:
   - macOS: `brew install python` (and if Homebrew is missing, point them to
     https://brew.sh). Windows: install from https://python.org and tick "Add
     to PATH". Linux: `sudo apt install python3 python3-venv`.
2. Create the environment and install dependencies (this also installs yt-dlp):
   ```
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   ```
   (On Windows the path is `.venv\Scripts\pip`.)
3. Confirm yt-dlp works: `.venv/bin/yt-dlp --version` (or a system `yt-dlp --version`).
   yt-dlp is the ONLY data source. There is NO YouTube API key to create -- if
   they ask about keys, reassure them none are needed today.
4. Report what you found/installed in one or two lines. If a step needs their
   password (installing Python system-wide), you cannot run it -- give them the
   exact command to run themselves and wait.

## 2. Interview (one question at a time, plain chat)
Collect the facts below. After each answer, reflect it back briefly so they can
correct you. Where you can, look at their channel with yt-dlp to make good
suggestions they just confirm -- but never invent faculty names.

1. **Exam / vertical name** -- short code for the master sheet's course column
   (e.g. `MATH`, `SCI`, `LANG`). And a friendly display name (e.g. `Demo MATH Prep`).
2. **Timezone** -- default `Asia/Kolkata` (IST). Keep unless they say otherwise.
3. **Channel(s)** -- their own YouTube channel for this vertical. Ask for the
   `@handle` (find it at the top of their channel page, e.g. `@YourChannelHandle`)
   or the channel URL. Ask: do they run just this one, or also a separate (e.g.
   English) channel? Most run ONE. If two, mark one as primary; the second's
   language is `english` (adds the `Eng- ` shorts prefix and turns on same-session
   dedup). Verify each handle resolves:
   `.venv/bin/yt-dlp --flat-playlist -I :3 --print "%(title)s" "https://www.youtube.com/<handle>/videos"`
4. **Faculty roster** -- the list of their teachers' names, written exactly as
   they should appear in the sheet, WITH honorifics (`Sir` / `Ma'am` / `Mam`).
   To help them, pull ~25 recent titles and show the names you see after a `|`:
   `.venv/bin/yt-dlp --flat-playlist -I :25 --print "%(title)s" "https://www.youtube.com/<handle>/videos"`
   and the same for `/streams`. Suggest the names, but they confirm the final
   list. Also ask for any **short forms / aliases** (e.g. "Meera Ma'am" is really
   "Meera Iyer Ma'am"). Note: many channels DON'T put the teacher's name in
   every title -- that's fine, those rows will show the placeholder and get
   flagged for a human; it is not an error.
5. **Subjects** -- their exam's sections (e.g. Algebra, Geometry, Number Theory,
   Statistics & Probability, Arithmetic). For each, ask for a few title keywords
   that signal it. The example file `inputs/subjects.example.yaml` is a starting
   point -- walk them through adapting it to their own exam's sections. Also ask
   for each faculty's usual subject (used only when a title has no keyword), and
   any "brand/institute" phrases (channel tours, fees, "why choose us") that
   should never be attributed to a teacher.
6. **Cadence** -- roughly how many Live / Long-form / Shorts they publish in a
   normal WEEK. This powers the safety check that shouts if a normally-active
   category comes back empty (a sign of dropped data). A rough number is fine.
7. **Placeholder label** -- default `Channel Official` for "no individual faculty".
   Keep unless they use a different bucket name.

## 3. Write their config
From the answers, create (copy the matching `*.example.*` file, then edit):
- `config/vertical.yaml`   (from `config/vertical.example.yaml`)
- `inputs/subjects.yaml`   (from `inputs/subjects.example.yaml`)
- `inputs/faculties.csv`   (one name per line, a header row on top)
- `inputs/aliases.csv`     (`canonical,alias` rows; may be empty)
- `inputs/faculty_emails.csv` (leave EMPTY, header only. Faculty emails are NOT used
  in the tracker output; the master sheet supplies FACULTY_EMAIL itself.)
Show them the finished `config/vertical.yaml` and the roster and get a yes.

## 4. Validate with a real pull
Pick a recent 2-3 day window that already has content (e.g. the last 3 days
before today) and run just the pull to prove the setup end-to-end:
`.venv/bin/python -m src.pull --start <start> --end <end>`
Show them the SUMMARY (counts + any warnings) and confirm the numbers look like
what they actually posted. If a normally-active category is 0, investigate before
declaring success (see the doctrine in `CLAUDE.md`). You do not need to run the
full pipeline here -- the pull passing is enough to confirm setup.

## 5. Hand off
Tell them setup is done and how to use it going forward:
- Every run: `/yt-mastersheet <start> <end>` (or `python run.py <start> <end>`),
  which pastes the master-sheet blocks + QA note into chat.
- To add a teacher or fix a subject later: edit `inputs/faculties.csv` /
  `inputs/subjects.yaml` (or just ask their Claude to). No code, no re-setup.
Keep the closing summary short.
