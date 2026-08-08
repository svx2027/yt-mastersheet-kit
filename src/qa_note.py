"""Phase 4: the executive QA note.

Plain language for a non-technical person who will open YouTube and check
things, not read code. Built only from artifacts already on disk -- it derives
nothing itself. No jargon, no em dashes.

Two required sections:
  A) Videos to verify: re-walk misses, and placeholders that were excluded
     because they had not aired / were still airing (need a re-pull once live).
  B) Every row tagged with the no-individual-faculty placeholder, so a human
     can give the real faculty or confirm it is brand/institute content.
  C) Any other flags (ambiguous faculty, blank subject, marathon with no named
     faculty, a live missing its air time).

Usage: python -m src.qa_note --start YYYY-MM-DD --end YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .kitconfig import OUTPUT_ROOT, load_config


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the executive QA note.")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config()
    window = f"{args.start}_to_{args.end}"
    out_dir = OUTPUT_ROOT / window

    pending = load(out_dir / "pending_reair.json", [])
    verify_report = load(out_dir / "verify_report.json", {})
    rewalk_missing = verify_report.get("checks", {}).get("air_date_rewalk", {}).get("missing", [])
    placeholder_rows = load(out_dir / "placeholder_rows.json", [])
    flagged = load(out_dir / "flagged_edge_cases.json", [])

    section_a = []
    _reason_text = {
        "unaired": "not yet aired -- re-pull this window once it airs",
        "live-in-progress": "still airing when pulled -- re-pull once it ends",
        "fetch-failed": "its YouTube page could not be read this run (network/throttle) -- re-pull to capture it",
    }
    for e in pending:
        section_a.append({"title": e["title"], "date": e.get("date_str") or "(not yet dated)",
                          "channel": e["channel"], "url": e["url"],
                          "why": _reason_text.get(e["reason"], "excluded -- please check")})
    for m in rewalk_missing:
        section_a.append({"title": m["title"], "date": m["date_str"], "channel": m["channel"], "url": m["url"],
                          "why": "found by the re-walk but not in the file -- possible miss, please check"})

    total = len(section_a) + len(placeholder_rows)
    lines = []
    lines.append(f"QA NOTE -- {cfg.display_name} -- {args.start} to {args.end}")
    lines.append(f"{total} item(s) need a human to check on YouTube "
                 f"({len(section_a)} possibly missing or uncertain, {len(placeholder_rows)} unnamed faculty).")
    lines.append("")
    lines.append("A) VIDEOS TO VERIFY (possibly missing, not yet aired, or uncertain)")
    if not section_a:
        lines.append("None this run.")
    else:
        for i, item in enumerate(section_a, 1):
            lines.append(f"{i}. {item['date']} | {item['channel']} | {item['title']}")
            lines.append(f"   Why: {item['why']}")
            lines.append(f"   Link: {item['url']}")
    lines.append("")
    lines.append(f'B) ROWS TAGGED "{cfg.placeholder}" (no individual faculty could be identified)')
    lines.append("Open each link and tell us the real faculty, or confirm it is genuinely "
                 "brand/institute content with no single presenter.")
    if not placeholder_rows:
        lines.append("None this run.")
    else:
        for i, r in enumerate(placeholder_rows, 1):
            lines.append(f"{i}. {r['date_str']} | {r['channel']} | {r['type']} | {r['title']}")
            lines.append(f"   Link: {r['url']}")

    if flagged:
        lines.append("")
        lines.append("C) OTHER ITEMS FLAGGED THIS RUN")
        for f_ in flagged:
            lines.append(f"- {f_}")

    note = "\n".join(lines)
    (out_dir / "qa_note.txt").write_text(note + "\n")
    print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
