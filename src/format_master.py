"""Phase 3: verified rows.json -> paste-ready master-tracker blocks.

Deterministic: same window in, same blocks out. Every faculty / subject / dedup
decision is code, and every drop or placeholder decision is written to disk, so
nothing lives only in a chat transcript.

Block layout (matches the shared master-tracker sheet's known column order):
  LIVE / LONG-FORM  -> 11 fields, 10 tabs:
    DATE  ·  (blank DAY)  ·  (blank TIME)  ·  EXAM  ·  FACULTY  ·  TYPE  ·
    SUBJECT  ·  TITLE  ·  (blank)  ·  FACULTY_EMAIL  ·  DURATION
    TYPE = "YT Live" (Live) or "YT Recorded" (Long-form).
  SHORTS  -> 8 fields, 7 tabs:
    DATE · (blank) · (blank) · EXAM · FACULTY · "YT Shorts" · "YT Shorts" · TOPIC

Refuses to run unless verify_report.json says overall=PASS -- the deliverable is
withheld until verification is green, enforced in code.

Usage: python -m src.format_master --start YYYY-MM-DD --end YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .faculty import build_detector
from .kitconfig import OUTPUT_ROOT, KitConfig, load_config

NEEDS_MANUAL_SPLIT = "NEEDS-MANUAL-SPLIT"
SESSION_NUM_PATTERN = re.compile(r"\bsession\s*[-#]?\s*(\d+)\b", re.IGNORECASE)


def halt(*lines: str) -> None:
    print("\nFORMAT FAIL", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    sys.exit(2)


def resolve_subject(title: str, faculty_display: str | None, cfg: KitConfig,
                    is_brand: bool, faculty_first: bool = False) -> tuple[str, bool]:
    """Keyword rules first, then per-faculty default, else blank + flagged.

    faculty_first flips the order for a marathon SPLIT row: the title is the whole
    marathon's (many subjects), so a per-faculty split row should trust that
    faculty's own default subject over whichever title keyword happens to match
    first -- otherwise every faculty in the marathon gets the same subject."""
    def faculty_default() -> str | None:
        if (not is_brand) and faculty_display and faculty_display not in (cfg.placeholder, NEEDS_MANUAL_SPLIT):
            return cfg.default_subject_by_faculty.get(faculty_display)
        return None

    if faculty_first:
        d = faculty_default()
        if d:
            return d, False
    tl = title.lower()
    for subject, patterns in cfg.subject_keywords:
        if any(re.search(pat, tl) for pat in patterns):
            return subject, False
    d = faculty_default()
    if d:
        return d, False
    return "", True


def resolve_faculty(title: str, existing_faculty, detect, cfg: KitConfig,
                    is_brand: bool) -> tuple[str | None, str, bool]:
    """(detected_faculty, faculty_display, ambiguous).
    Brand/institute content is never attributed to a mentor even if a name appears."""
    if existing_faculty:  # pre-resolved marathon split row
        return existing_faculty, existing_faculty, False
    if is_brand:
        return None, cfg.placeholder, False
    names = detect(title)
    if len(names) == 1:
        return names[0], names[0], False
    if len(names) == 0:
        return None, cfg.placeholder, False
    return None, NEEDS_MANUAL_SPLIT, True


def shorts_topic(title: str, detected_faculty: str | None, is_english: bool) -> str:
    t = title.replace("|", "-")
    t = re.sub(r"\s+", " ", t).strip().lower()
    topic = f"{t} shorts"
    if detected_faculty:
        topic = f"{detected_faculty}- {topic}"
    if is_english:
        topic = f"Eng- {topic}"
    return topic


def is_brand_content(title: str, cfg: KitConfig) -> bool:
    tl = title.lower()
    return any(p in tl for p in cfg.brand_content_patterns)


def to_tsv_block(rows: list[list], expected_tabs: int, sheet: str) -> str:
    lines = []
    for fields in rows:
        line = "\t".join("" if f is None else str(f) for f in fields)
        tabs = line.count("\t")
        if tabs != expected_tabs:
            halt(f"{sheet}: row has {tabs} tabs, expected {expected_tabs}: {fields}")
        lines.append(line)
    return "\n".join(lines)


def dedup_secondary_vs_primary(primary_live: list[dict], sec_live: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop a secondary-channel Live row only on the strong signal: same date AND
    same 'Session N' number as a primary Live row. No session number on either
    side -> keep both (never guess from fuzzy title similarity)."""
    ledger = []
    primary_key: dict[tuple, dict] = {}
    for r in primary_live:
        m = SESSION_NUM_PATTERN.search(r["title"])
        if m:
            primary_key[(r["date_str"], int(m.group(1)))] = r  # int() so "21" and "021" match
    kept = []
    for r in sec_live:
        m = SESSION_NUM_PATTERN.search(r["title"])
        key = (r["date_str"], int(m.group(1))) if m else None
        match = primary_key.get(key) if key else None
        if match:
            ledger.append({"dropped_video_id": r["video_id"], "dropped_title": r["title"],
                           "dropped_url": r["url"], "kept_video_id": match["video_id"],
                           "kept_title": match["title"], "date_str": r["date_str"],
                           "session_number": key[1], "reason": "same date + session number as a primary row"})
        else:
            kept.append(r)
    return kept, ledger


def build_live_lf_row(r: dict, base: str, detect, cfg: KitConfig):
    brand = is_brand_content(r["title"], cfg)
    type_label = "YT Live" if base == "Live" else "YT Recorded"
    detected, display, ambiguous = resolve_faculty(r["title"], r.get("faculty"), detect, cfg, brand)
    is_marathon_split = bool(r.get("faculty")) and bool(r.get("is_marathon"))
    subject, subj_flagged = resolve_subject(r["title"], display, cfg, brand, faculty_first=is_marathon_split)
    email = cfg.emails.get(display, "") if display not in (cfg.placeholder, NEEDS_MANUAL_SPLIT) else ""
    fields = [r["date_str"], "", "", cfg.name, display, type_label, subject, r["title"], "", email, r["duration_min"]]
    flag = None
    if ambiguous:
        flag = f"{base} {r['video_id']}: multiple faculty named, cannot attribute -- manual split: {r['title'][:70]!r}"
    elif subj_flagged:
        flag = f"{base} {r['video_id']}: subject left blank, no keyword or faculty default matched: {r['title'][:70]!r}"
    return fields, flag, display == cfg.placeholder


def build_shorts_row(r: dict, detect, cfg: KitConfig):
    brand = is_brand_content(r["title"], cfg)
    is_english = r.get("language") == "english"
    detected, display, ambiguous = resolve_faculty(r["title"], None, detect, cfg, brand)
    topic = shorts_topic(r["title"], detected, is_english)
    fields = [r["date_str"], "", "", cfg.name, display, "YT Shorts", "YT Shorts", topic]
    flag = None
    if ambiguous:
        flag = f"Shorts {r['video_id']}: multiple faculty named, cannot attribute -- manual split: {r['title'][:70]!r}"
    return fields, flag, display == cfg.placeholder


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Format a verified window into master-tracker blocks.")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config()
    window = f"{args.start}_to_{args.end}"
    out_dir = OUTPUT_ROOT / window

    rows_files = sorted(out_dir.glob("*_raw.json"))
    if not rows_files:
        halt(f"no *_raw.json in {out_dir} -- run pull first.")
    report_path = out_dir / "verify_report.json"
    if not report_path.exists():
        halt(f"missing {report_path} -- run verify first; the deliverable is withheld until it's green.")
    report = json.loads(report_path.read_text())
    if report.get("overall") != "PASS":
        halt(f"{report_path} says overall={report.get('overall')!r} -- fix and re-verify before formatting.")

    doc = json.loads(rows_files[0].read_text())
    buckets = doc["buckets"]
    detect = build_detector(cfg.roster, cfg.aliases)

    primary_label = cfg.primary_channel.label
    dedup_ledger: list[dict] = []
    # dedup each secondary channel's Live rows against the primary channel's
    if cfg.is_multi_channel:
        primary_live = buckets.get(f"Live_{primary_label}", [])
        for ch in cfg.channels:
            if ch.label == primary_label:
                continue
            key = f"Live_{ch.label}"
            if key in buckets:
                kept, ledger = dedup_secondary_vs_primary(primary_live, buckets[key])
                buckets[key] = kept
                dedup_ledger.extend(ledger)

    flags: list[str] = []
    placeholder_rows: list[dict] = []
    blocks: dict[str, str] = {}
    counts: dict[str, int] = {}

    # order: primary channel first, then the rest; within a channel Live, LF, Shorts
    ordered_labels = [primary_label] + [c.label for c in cfg.channels if c.label != primary_label]
    ordered_sheets = [f"{base}_{lbl}" for lbl in ordered_labels for base in ("Live", "LF", "Shorts")]

    for sheet in ordered_sheets:
        rows = buckets.get(sheet, [])
        base = sheet.split("_")[0]
        out_rows = []
        for r in rows:
            if base == "Shorts":
                fields, flag, is_ph = build_shorts_row(r, detect, cfg)
                rtype = "Short"
            else:
                fields, flag, is_ph = build_live_lf_row(r, base, detect, cfg)
                rtype = "Live" if base == "Live" else "Long-form"
            out_rows.append(fields)
            if flag:
                flags.append(flag)
            if is_ph:
                placeholder_rows.append({"date_str": r["date_str"], "channel": sheet.split("_", 1)[1],
                                         "type": rtype, "title": r["title"], "url": r["url"]})
        blocks[sheet] = to_tsv_block(out_rows, 7 if base == "Shorts" else 10, sheet)
        counts[sheet] = len(out_rows)

    blocks_dir = out_dir / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    for sheet, text in blocks.items():
        (blocks_dir / f"{sheet}.tsv").write_text(text + ("\n" if text else ""))
    (out_dir / "dropped_rows.json").write_text(json.dumps(dedup_ledger, indent=2, ensure_ascii=False))
    (out_dir / "placeholder_rows.json").write_text(json.dumps(placeholder_rows, indent=2, ensure_ascii=False))
    (out_dir / "flagged_edge_cases.json").write_text(json.dumps(flags, indent=2, ensure_ascii=False))

    print("[format] row counts:")
    for sheet, n in counts.items():
        print(f"  {sheet:<18} {n:>3} rows")
    print(f"[format] dedup: {len(dedup_ledger)} secondary Live row(s) dropped as primary duplicates")
    print(f"[format] {cfg.placeholder}: {len(placeholder_rows)} row(s)")
    print(f"[format] flagged edge cases: {len(flags)}")
    print(f"[format] blocks -> {blocks_dir}")
    print(f"\nNEXT STEP : python -m src.qa_note --start {args.start} --end {args.end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
