"""Phase 1: discover -> categorize -> gate -> write rows.json (+ optional XLSX view).

Discovery source of truth is the channel's own tabs (yt-dlp), the analog of the
uploads playlist, never a lossy search. Each tab is walked newest-first and the
fetch stops a few days past the window start:
  - /streams is ordered by AIR date (validated against a real channel's tab
    ordering), so an early-announced live -- placeholder published days before
    it airs -- still surfaces near the top by its in-window air date. verify.py
    independently re-walks deeper (lookback_days) as the audit that nothing was
    missed.
  - /videos and /shorts are ordered by publish date; shorts/long-form are dated
    by publish, so no early-announce case exists for them.

rows.json is the canonical machine output; the XLSX is a human-readable VIEW of
the same rows (never re-read by the pipeline), so there is a single source of truth.

Usage: python -m src.pull --start YYYY-MM-DD --end YYYY-MM-DD [--allow-anomaly] [--no-xlsx]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import ytdlp_client as yt
from .categorize import (Decision, _parse_date_str, categorize, date_str,
                         to_ist, tz_from_name)
from .faculty import build_detector
from .kitconfig import OUTPUT_ROOT, KitConfig, load_config

VERSION = "v1"
STOP_MARGIN_DAYS = 3  # keep fetching this many days past window start, then stop


def halt(*lines: str) -> None:
    print("\nPULL FAIL", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover + categorize a YouTube window into rows.json.")
    p.add_argument("--start", required=True, help="IST start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="IST end date YYYY-MM-DD (inclusive)")
    p.add_argument("--allow-anomaly", action="store_true",
                   help="downgrade ONLY the baseline (quiet-week) gate to a warning; every other gate still hard-fails")
    p.add_argument("--no-xlsx", action="store_true", help="skip writing the human XLSX view")
    return p.parse_args()


def _validate_window(start: str, end: str) -> tuple[date, date]:
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        halt(f"start/end must be YYYY-MM-DD. Got start={start!r} end={end!r}.")
    if e < s:
        halt(f"end ({end}) is before start ({start}).")
    if (e - s).days > 90:
        halt(f"window is {(e - s).days + 1} days. Keep it to 90 days or fewer per run.")
    return s, e


def _flat_cap(cfg: KitConfig, start: str, window_days: int) -> int:
    """How many newest videos to LIST per tab. The walk starts at the tab's newest
    (today) and must reach back to (window start - lookback), so size it from
    today, not just the window length -- a catch-up run weeks after the window
    still needs to span from today back past the window."""
    try:
        days_from_today = max(window_days, (date.today() - date.fromisoformat(start)).days + 1)
    except Exception:
        days_from_today = window_days
    return min(800, (days_from_today + cfg.lookback_days + 5) * 6)


def collect_channel(cfg: KitConfig, channel, start: str, end: str,
                    window_days: int) -> tuple[dict[str, list[dict]], list[dict], int, list[str]]:
    """Return (buckets, exclusions, requested_count, walk_warnings) for one channel.

    buckets keys are Live/LF/Shorts (channel label appended by caller). requested_count
    is every id we attempted to fetch (so coverage balances even when a fetch fails).
    walk_warnings flags a tab that hit the discovery cap without reaching the window."""
    stop_date = (date.fromisoformat(start) - timedelta(days=STOP_MARGIN_DAYS)).isoformat()
    cap = _flat_cap(cfg, start, window_days)
    tz = tz_from_name(cfg.timezone)

    # Fetch each tab INDEPENDENTLY, newest-first, early-stopping that tab once a
    # whole batch is older than stop_date. Each tab is its own newest-first list,
    # so they must be walked separately -- concatenating them would let one tab's
    # early-stop cut off another tab (e.g. stop during /videos before reaching /shorts).
    fetched: list[yt.RawVideo] = []
    seen_ids: set[str] = set()
    requested_ids: set[str] = set()
    walk_warnings: list[str] = []
    batch = 40
    for tab in yt.TABS:
        ids = yt.discover_ids(channel.handle, tab, cap)
        source_tab = {vid: tab for vid in ids}
        reached_stop = False
        for i in range(0, len(ids), batch):
            chunk = [v for v in ids[i:i + batch] if v not in seen_ids]
            if not chunk:
                continue
            seen_ids.update(chunk)      # mark attempted (whether or not the fetch returns them)
            requested_ids.update(chunk)
            raws = yt.fetch_details(chunk, source_tab, batch=batch)
            fetched.extend(raws)
            # relevant date per raw: air (release) for genuine lives, else publish
            newest_in_chunk = None
            for r in raws:
                ts = r.release_timestamp if (r.was_live and r.release_timestamp) else r.timestamp
                if ts is None:
                    continue
                d = to_ist(ts, tz).date().isoformat()
                if newest_in_chunk is None or d > newest_in_chunk:
                    newest_in_chunk = d
            if newest_in_chunk is not None and newest_in_chunk < stop_date:
                reached_stop = True
                break  # this tab is exhausted for the window; move to the next tab
        # If we consumed the whole listing AND it was capped, the tab may be truncated
        # before the window's oldest day -- an in-window video could be beyond the cap.
        if not reached_stop and len(ids) >= cap:
            walk_warnings.append(f"{channel.label}/{tab}: walked the full {cap}-video cap without "
                                 f"reaching {stop_date}; window may be under-covered -- raise lookback/cap")

    # any id we asked for but never got back (429/transient/geo/deleted) -> fetch-failed,
    # recorded so coverage balances and the miss is visible, never a silent drop
    got = {r.video_id for r in fetched}
    exclusions: list[dict] = []
    for vid in sorted(requested_ids - got):
        exclusions.append({"video_id": vid, "title": "(fetch failed)",
                           "url": f"https://www.youtube.com/watch?v={vid}", "channel": channel.label,
                           "reason": "fetch-failed", "date_str": None,
                           "live_status": "NA", "was_live": None, "flags": ["fetch-failed"]})

    # 3) categorize + window-filter
    buckets: dict[str, list[dict]] = {"Live": [], "LF": [], "Shorts": []}
    for r in fetched:
        d: Decision = categorize(r, cfg)
        if d.category == "EXCLUDE":
            exclusions.append(_excl(r, channel, d.reason, d.flags))
            continue
        if not (start <= _parse_date_str(d.date_str) <= end):
            exclusions.append(_excl(r, channel, "out-of-window", d.flags, date_str=d.date_str))
            continue
        buckets[d.category].append({
            "video_id": r.video_id, "title": r.title, "url": r.url,
            "date_str": d.date_str, "ist_iso": d.ist_iso,
            "duration_min": d.duration_min, "live_status": r.live_status,
            "was_live": r.was_live, "source_tab": r.source_tab,
            "channel_label": channel.label, "language": channel.language,
            "is_marathon": d.is_marathon, "faculty": None, "flags": d.flags,
        })
    return buckets, exclusions, len(requested_ids), walk_warnings


def _excl(r: yt.RawVideo, channel, reason: str, flags: list[str], date_str: str | None = None) -> dict:
    return {
        "video_id": r.video_id, "title": r.title, "url": r.url,
        "channel": channel.label, "reason": reason, "date_str": date_str,
        "live_status": r.live_status, "was_live": r.was_live, "flags": flags,
    }


def split_minutes(total: int, n: int) -> list[int]:
    """Largest-remainder equal split; sums exactly to total."""
    base = total // n
    rem = total - base * n
    return [base + (1 if i < rem else 0) for i in range(n)]


def split_marathons(live_rows: list[dict], detect) -> list[dict]:
    """A marathon live is one row per resolved faculty, minutes split equally.
    Faculty come from the title (roster + alias). If the title names none, the
    row stays whole and unresolved (format assigns the no-individual placeholder)
    and is flagged. No thumbnail/vision step in the kit -- title/description only.
    """
    out: list[dict] = []
    for row in live_rows:
        if not row.get("is_marathon"):
            out.append(row)
            continue
        names = detect(row["title"])
        if len(names) <= 1:
            # 0 names -> placeholder later; 1 name -> normal single row
            if names:
                row = {**row, "faculty": names[0]}
            else:
                row = {**row, "flags": row.get("flags", []) + ["marathon-no-title-faculty"]}
            out.append(row)
            continue
        shares = split_minutes(row["duration_min"], len(names))
        for name, share in zip(names, shares):
            out.append({**row, "faculty": name, "duration_min": share})
    return out


# --------------------------------------------------------------------------- gates
def run_gates(all_buckets: dict[str, list[dict]], cfg: KitConfig, start: str, end: str,
              window_days: int, fetched_total: int, excl_total: int,
              allow_anomaly: bool) -> list[str]:
    warnings: list[str] = []
    failures: list[str] = []

    # boundary gate: every placed row inside the window
    for name, rows in all_buckets.items():
        for r in rows:
            if not (start <= _parse_date_str(r["date_str"]) <= end):
                failures.append(f"boundary: {name} {r['video_id']} dated {r['date_str']} is outside {start}..{end}")

    # cross-bucket duplicate gate: no video id in two buckets
    seen: dict[str, str] = {}
    for name, rows in all_buckets.items():
        for r in rows:
            prev = seen.get(r["video_id"])
            if prev and prev != name:
                failures.append(f"duplicate: {r['video_id']} appears in both {prev} and {name}")
            seen[r["video_id"]] = name

    # category-invariant gate
    for name, rows in all_buckets.items():
        base = name.split("_")[0]
        for r in rows:
            if base == "Shorts" and r["duration_min"] is not None:
                failures.append(f"category: {name} {r['video_id']} is a Short but carries a duration")
            if base == "LF" and r["was_live"] is True:
                failures.append(f"category: {name} {r['video_id']} is Long-form but was_live=True (should be Live)")
            if base == "Live" and r["was_live"] is not True:
                failures.append(f"category: {name} {r['video_id']} is Live but was_live!=True (premiere?)")

    # baseline (quiet-week) gate: scale weekly expectation to the window length
    scale = window_days / 7.0
    type_totals = {"Live": 0, "LF": 0, "Shorts": 0}
    for name, rows in all_buckets.items():
        type_totals[name.split("_")[0]] += len(rows)
    expect = {"Live": cfg.expected_weekly["live"] * scale,
              "LF": cfg.expected_weekly["longform"] * scale,
              "Shorts": cfg.expected_weekly["shorts"] * scale}
    for t, exp in expect.items():
        got = type_totals[t]
        if exp >= 3 and got == 0:
            msg = (f"baseline: expected ~{exp:.1f} {t} rows for a {window_days}-day window "
                   f"but got 0 -- looks like dropped data")
            (warnings if allow_anomaly else failures).append(msg)
        elif exp > 0 and got > 3 * exp:
            warnings.append(f"baseline: {t} got {got}, more than 3x the expected ~{exp:.1f} -- sanity-check")

    # coverage assertion (HARD failure, per the doctrine): every id we requested is
    # either placed or excluded. Marathons split one id into several rows, so count
    # unique placed ids. A mismatch means a video was neither placed nor recorded --
    # a silent drop -- and must halt, not warn.
    placed_ids = {r["video_id"] for rows in all_buckets.values() for r in rows}
    if len(placed_ids) + excl_total != fetched_total:
        failures.append(f"coverage: requested={fetched_total} but placed(unique)={len(placed_ids)} + "
                        f"excluded={excl_total} = {len(placed_ids) + excl_total} -- a video went unaccounted for")

    if failures:
        halt("gate failure(s):", *failures)
    return warnings


def raw_filename(start: str, end: str, ext: str) -> str:
    return f"tracker_{{v}}_{start}_to_{end}_raw.{ext}".replace("{v}", VERSION)


def write_xlsx(path: Path, buckets: dict[str, list[dict]], channels) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in buckets.items():
        ws = wb.create_sheet(title=name[:31])
        base = name.split("_")[0]
        if base == "Shorts":
            ws.append(["Date", "Title", "Video ID", "URL"])
            for r in rows:
                ws.append([r["date_str"], r["title"], r["video_id"], r["url"]])
        else:
            ws.append(["Date", "Title", "Duration (min)", "Faculty", "Video ID", "URL"])
            for r in rows:
                ws.append([r["date_str"], r["title"], r["duration_min"],
                           r.get("faculty") or "", r["video_id"], r["url"]])
    wb.save(path)
    return True


def main() -> int:
    args = parse_args()
    s, e = _validate_window(args.start, args.end)
    window_days = (e - s).days + 1
    cfg = load_config()

    detect = build_detector(cfg.roster, cfg.aliases)
    all_buckets: dict[str, list[dict]] = {}
    all_excl: list[dict] = []
    all_walk_warnings: list[str] = []
    fetched_total = 0

    print(f"[pull] {cfg.display_name} | window {args.start}..{args.end} ({window_days}d) IST | "
          f"{len(cfg.channels)} channel(s) | source=yt-dlp")
    for ch in cfg.channels:
        print(f"[pull] channel '{ch.label}' ({ch.handle}) ...")
        buckets, excl, requested, walk_warnings = collect_channel(cfg, ch, args.start, args.end, window_days)
        fetched_total += requested
        all_excl.extend(excl)
        all_walk_warnings.extend(walk_warnings)
        buckets["Live"] = split_marathons(buckets["Live"], detect)
        for base in ("Live", "LF", "Shorts"):
            all_buckets[f"{base}_{ch.label}"] = buckets[base]
        failed = sum(1 for x in excl if x["reason"] == "fetch-failed")
        print(f"        requested={requested}  Live={len(buckets['Live'])} "
              f"LF={len(buckets['LF'])} Shorts={len(buckets['Shorts'])} excluded={len(excl)}"
              + (f" fetch-failed={failed}" if failed else ""))

    warnings = run_gates(all_buckets, cfg, args.start, args.end, window_days,
                         fetched_total, len(all_excl), args.allow_anomaly)
    warnings = all_walk_warnings + warnings

    window = f"{args.start}_to_{args.end}"
    out_dir = OUTPUT_ROOT / window
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_doc = {
        "version": VERSION, "vertical": cfg.name, "display_name": cfg.display_name,
        "window": {"start": args.start, "end": args.end, "tz": cfg.timezone, "days": window_days},
        "channels": [{"label": c.label, "handle": c.handle, "language": c.language,
                      "is_primary": c.is_primary} for c in cfg.channels],
        "buckets": all_buckets,
    }
    rows_path = out_dir / raw_filename(args.start, args.end, "json")
    rows_path.write_text(json.dumps(rows_doc, indent=2, ensure_ascii=False))

    # exclusions + the subset that needs a future re-pull (unaired / still-airing / fetch-failed)
    pending = [x for x in all_excl if x["reason"] in ("unaired", "live-in-progress", "fetch-failed")]
    (out_dir / "exclusions.json").write_text(json.dumps(all_excl, indent=2, ensure_ascii=False))
    (out_dir / "pending_reair.json").write_text(json.dumps(pending, indent=2, ensure_ascii=False))

    xlsx_written = False
    if not args.no_xlsx:
        xlsx_written = write_xlsx(out_dir / raw_filename(args.start, args.end, "xlsx"),
                                  all_buckets, cfg.channels)

    summary = {
        "version": VERSION, "window": rows_doc["window"], "vertical": cfg.name,
        "fetched": fetched_total, "excluded": len(all_excl),
        "counts": {k: len(v) for k, v in all_buckets.items()},
        "warnings": warnings, "gate": "PASS",
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n==== SUMMARY ====")
    for name, rows in all_buckets.items():
        print(f"  {name:<18} {len(rows):>3} rows")
    print(f"Fetched   : {fetched_total}   Excluded: {len(all_excl)}   "
          f"Pending re-air: {len(pending)}")
    if warnings:
        print("Warnings  :")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("Warnings  : none")
    print(f"Gate      : PASS")
    print(f"Rows JSON : {rows_path}")
    print(f"XLSX view : {'written' if xlsx_written else '(skipped: openpyxl not installed)'}")
    print(f"\nNEXT STEP : python -m src.verify --start {args.start} --end {args.end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
