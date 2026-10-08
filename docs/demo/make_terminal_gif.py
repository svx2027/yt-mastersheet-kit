#!/usr/bin/env python3
"""Render a terminal-session GIF from captured output of the kit's own sample run.

Does not fabricate output: the four `CAPTURES` blocks below are the real stdout
this repo's real src/pull.py -> src/verify.py -> src/format_master.py ->
src/qa_note.py produced against the fictional "Demo MATH Prep" catalog in
docs/sample_run/ (see docs/sample_run/README.md for how to reproduce that run
yourself). The only edit made to any captured line is swapping the sandbox's
absolute temp-dir path (an artifact of where this script happened to run, not
of the tool) for the same path the committed docs/sample_run/README.md already
shows, relative to the repo root. Nothing is shortened, reworded, or invented.
This script only does the typing/scrolling animation and rendering.

Usage: python3 docs/demo/make_terminal_gif.py
Requires: Pillow (pip install Pillow). No network, no repo code imported.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
OUT_GIF = HERE / "mastersheet_demo.gif"

# Exact captured stdout of each phase, from a real run against the sample catalog.
CAPTURES = [
    (
        "python3 -m src.pull --start 2026-07-01 --end 2026-07-07 --no-xlsx",
        """[pull] Demo MATH Prep | window 2026-07-01..2026-07-07 (7d) IST | 1 channel(s) | source=yt-dlp
[pull] channel 'Main' (@MathPrepDemo) ...
        requested=14  Live=4 LF=5 Shorts=3 excluded=3 fetch-failed=1

==== SUMMARY ====
  Live_Main            4 rows
  LF_Main              5 rows
  Shorts_Main          3 rows
Fetched   : 14   Excluded: 3   Pending re-air: 2
Warnings  : none
Gate      : PASS
Rows JSON : output/2026-07-01_to_2026-07-07/tracker_v1_2026-07-01_to_2026-07-07_raw.json
XLSX view : (skipped: openpyxl not installed)

NEXT STEP : python -m src.verify --start 2026-07-01 --end 2026-07-07""",
    ),
    (
        "python3 -m src.verify --start 2026-07-01 --end 2026-07-07",
        """[verify] re-fetching 11 placed video(s) for independent re-derivation ...
[verify] check 1 re-derivation : PASS (12 rows)
[verify] check 2 no cross-bucket dup : PASS
[verify] check 3 re-walk missing : PASS
[verify] PASS -- independent re-derivation agrees with the file""",
    ),
    (
        "python3 -m src.format_master --start 2026-07-01 --end 2026-07-07",
        """[format] row counts:
  Live_Main            4 rows
  LF_Main              5 rows
  Shorts_Main          3 rows
[format] dedup: 0 secondary Live row(s) dropped as primary duplicates
[format] Channel Official: 4 row(s)
[format] flagged edge cases: 4
[format] blocks -> output/2026-07-01_to_2026-07-07/blocks

NEXT STEP : python -m src.qa_note --start 2026-07-01 --end 2026-07-07""",
    ),
    (
        "python3 -m src.qa_note --start 2026-07-01 --end 2026-07-07",
        """QA NOTE -- Demo MATH Prep -- 2026-07-01 to 2026-07-07
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
- LF lf005: multiple faculty named, cannot attribute -- manual split: 'Combined Revision: Arjun Rao Sir and Devika Menon'""",
    ),
]

INTRO = "# fictional demo vertical (docs/sample_run/) -- not a live pull from a real channel"

# --- layout ---
COLS, ROWS = 102, 30
FONT_SIZE = 15
PAD_X, PAD_Y = 18, 16
BG = (13, 17, 23)
TITLEBAR = (22, 27, 34)
FG = (201, 209, 217)
GREEN = (63, 185, 80)
CYAN = (88, 166, 255)
YELLOW = (210, 153, 34)
DIM = (125, 133, 144)

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
bold_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", FONT_SIZE
)
ascent, descent = font.getmetrics()
line_h = ascent + descent + 6
char_w = font.getlength("M")

TITLEBAR_H = 34
W = int(PAD_X * 2 + COLS * char_w)
H = int(TITLEBAR_H + PAD_Y * 2 + ROWS * line_h)


def line_color(text):
    if "PASS" in text or "Gate" in text and "PASS" in text:
        return GREEN
    if "fetch-failed" in text or "FAIL" in text or "excluded" in text:
        return YELLOW
    if text.startswith("[") or text.startswith("NEXT STEP") or text.startswith("===="):
        return CYAN
    if text.startswith("#"):
        return DIM
    return FG


def render_frame(visible_lines, cursor_on=False, cursor_line_idx=None, cursor_text=""):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, TITLEBAR_H], fill=TITLEBAR)
    for i, c in enumerate((0xFF5F56, 0xFFBD2E, 0x27C93F)):
        draw.ellipse(
            [16 + i * 22, TITLEBAR_H // 2 - 6, 16 + i * 22 + 12, TITLEBAR_H // 2 + 6],
            fill=f"#{c:06x}",
        )
    draw.text(
        (W / 2, TITLEBAR_H / 2),
        "yt-mastersheet-kit -- sample run",
        font=font,
        fill=(140, 148, 158),
        anchor="mm",
    )

    y = TITLEBAR_H + PAD_Y
    for idx, raw in enumerate(visible_lines):
        is_prompt = raw.startswith("$ ")
        if is_prompt:
            draw.text((PAD_X, y), "$", font=bold_font, fill=GREEN)
            draw.text((PAD_X + char_w * 2, y), raw[2:], font=bold_font, fill=(230, 237, 243))
        else:
            draw.text((PAD_X, y), raw, font=font, fill=line_color(raw))
        y += line_h

    if cursor_on:
        cy = TITLEBAR_H + PAD_Y + cursor_line_idx * line_h
        cx = PAD_X + char_w * 2 + font.getlength(cursor_text)
        draw.rectangle([cx, cy, cx + char_w * 0.6, cy + line_h - 6], fill=(230, 237, 243))
    return img


def wrap_line(text, width=COLS - 2):
    """Soft-wrap a long captured line for display; never drops or alters characters."""
    if len(text) <= width:
        return [text]
    indent = "   " if not text.startswith(" ") else "     "
    out = [text[:width]]
    rest = text[width:]
    cont_width = width - len(indent)
    while rest:
        out.append(indent + rest[:cont_width])
        rest = rest[cont_width:]
    return out


def build():
    buf = [INTRO, ""]
    frames = []
    durations = []

    def push(cursor=None):
        view = buf[-ROWS:] if len(buf) > ROWS else buf[:] + [""] * (ROWS - len(buf))
        cur_idx = None
        cur_text = ""
        if cursor is not None:
            rel = len(buf) - 1 - (len(buf) - ROWS if len(buf) > ROWS else 0)
            cur_idx = rel
            cur_text = cursor
        frames.append(render_frame(view, cursor is not None, cur_idx, cur_text))

    push()
    durations.append(900)

    for cmd, output in CAPTURES:
        # type the command character by character
        typed = ""
        prompt_prefix = "$ "
        buf.append(prompt_prefix)
        for ch in cmd:
            typed += ch
            buf[-1] = prompt_prefix + typed
            push(cursor=typed)
            durations.append(18)
        push()
        durations.append(500)

        for line in output.split("\n"):
            for physical in wrap_line(line):
                buf.append(physical)
                push()
                durations.append(90)
        buf.append("")
        push()
        durations.append(650)

    # final hold
    durations[-1] = 3200

    return frames, durations


def main():
    frames, durations = build()
    frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"wrote {OUT_GIF} ({len(frames)} frames, {OUT_GIF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
