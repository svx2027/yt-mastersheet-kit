"""Phase 2: independent re-derivation. Withholds the deliverable until green.

This runs on a genuinely SEPARATE code path from pull.py: its own duration
rounding, its own IST conversion, its own categorization, and its own fresh
yt-dlp fetches. It deliberately does NOT import src.categorize -- if it did,
agreement would only prove one function was called twice. Because the two
implementations are written independently, agreement is real evidence the
derivation is correct.

Checks:
  1. every placed video's date, duration, and category re-derived and matched
  2. no video id appears in two buckets
  3. an independent deeper re-walk (lookback_days) of every channel tab, by air
     date for lives / publish date otherwise, confirming nothing in-window is
     missing from rows.json

Writes verify_report.json with overall: PASS|FAIL. format_master.py refuses to
run unless it says PASS. Halts (exit 2) on any mismatch.

Usage: python -m src.verify --start YYYY-MM-DD --end YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import ytdlp_client as yt
from .kitconfig import OUTPUT_ROOT, load_config

_MON = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
_MON_REV = {v: k for k, v in _MON.items()}


# --- independent re-implementations (intentionally not shared with pull) ----
def v_offset(tzname: str) -> timedelta:
    return timedelta(hours=5, minutes=30) if tzname in ("Asia/Kolkata", "Asia/Calcutta", "IST") else timedelta(0)


def v_ist(unix_ts: int, off: timedelta) -> datetime:
    return datetime.fromtimestamp(int(unix_ts), timezone(off))


def v_date_str(dt: datetime) -> str:
    return f"{dt.day:02d}-{_MON[dt.month]}-{dt.year}"


def v_ceil_min(seconds: int) -> int:
    return -(-int(seconds) // 60)  # ceil via floor-negate, a different formula than pull's math.ceil


def v_iso(date_str_val: str) -> str:
    d, m, y = date_str_val.split("-")
    return f"{int(y):04d}-{_MON_REV[m]:02d}-{int(d):02d}"


def v_categorize(r: yt.RawVideo, cfg) -> tuple[str, str | None, int | None]:
    """Return (category, date_str, duration_min). category in Live/LF/Shorts/EXCLUDE:<reason>."""
    off = v_offset(cfg.timezone)
    ls = (r.live_status or "NA").lower()
    if ls == "is_upcoming":
        return "EXCLUDE:unaired", None, None
    if ls == "is_live":
        return "EXCLUDE:live-in-progress", None, None
    if ls == "post_live" and not r.duration:
        return "EXCLUDE:live-in-progress", None, None
    if r.was_live is True:
        if not r.duration:
            return "EXCLUDE:live-in-progress", None, None
        air = r.release_timestamp if r.release_timestamp else r.timestamp
        if air is None:
            return "EXCLUDE:live-no-date", None, None
        dt = v_ist(air, off)
        return "Live", v_date_str(dt), v_ceil_min(r.duration)
    if r.timestamp is None:
        return "EXCLUDE:no-publish-date", None, None
    dt = v_ist(r.timestamp, off)
    if not r.duration:  # None OR 0
        return "EXCLUDE:no-duration", None, None
    if r.duration <= cfg.shorts_max_seconds:
        return "Shorts", v_date_str(dt), None
    if r.duration >= cfg.longform_min_seconds:
        return "LF", v_date_str(dt), v_ceil_min(r.duration)
    return "EXCLUDE:gap", None, None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Independently verify a pulled window.")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    return p.parse_args()


def find_rows(out_dir: Path) -> Path | None:
    cands = sorted(p for p in out_dir.glob("*_raw.json"))
    return cands[0] if cands else None


def main() -> int:
    args = parse_args()
    cfg = load_config()
    window = f"{args.start}_to_{args.end}"
    out_dir = OUTPUT_ROOT / window
    rows_path = find_rows(out_dir)
    if rows_path is None:
        print(f"[verify] no *_raw.json in {out_dir}; run pull first.", file=sys.stderr)
        return 2
    doc = json.loads(rows_path.read_text())
    buckets = doc["buckets"]

    # Videos the pull DELIBERATELY excluded (out-of-window, gap, unaired, still-airing,
    # fetch-failed). The re-walk must not report these as "missing" -- they were
    # consciously handled and recorded, not overlooked. A live that was still airing
    # at pull time and finished by verify time is the canonical case.
    excl_path = out_dir / "exclusions.json"
    excluded_ids = {x.get("video_id") for x in json.loads(excl_path.read_text())} if excl_path.exists() else set()

    report: dict = {"overall": "PASS", "checks": {}}
    mismatches: list[str] = []

    # gather every placed (video_id -> its rows; marathons repeat an id across split rows)
    placed_rows: list[dict] = []
    id_to_buckets: dict[str, set] = {}
    for name, rows in buckets.items():
        for r in rows:
            placed_rows.append({**r, "_bucket": name})
            id_to_buckets.setdefault(r["video_id"], set()).add(name)

    # check 2: no id in two buckets
    dup = {vid: sorted(bs) for vid, bs in id_to_buckets.items() if len(bs) > 1}
    report["checks"]["no_cross_bucket_dup"] = {"pass": not dup, "duplicates": dup}
    if dup:
        mismatches.append(f"video id(s) in two buckets: {dup}")

    # check 1: re-fetch every placed id and re-derive
    unique_ids = list(id_to_buckets.keys())
    print(f"[verify] re-fetching {len(unique_ids)} placed video(s) for independent re-derivation ...")
    fresh = {r.video_id: r for r in yt.fetch_details(unique_ids, {}, batch=40)}
    rederive_fail = []
    for row in placed_rows:
        vid = row["video_id"]
        r = fresh.get(vid)
        if r is None:
            rederive_fail.append(f"{vid}: could not re-fetch")
            continue
        cat, ds, dmin = v_categorize(r, cfg)
        base = row["_bucket"].split("_")[0]
        # independent boundary check: a placed row's re-derived date must be in-window
        # (don't rely only on the pull's own boundary gate)
        if not cat.startswith("EXCLUDE") and ds and not (args.start <= v_iso(ds) <= args.end):
            rederive_fail.append(f"{vid}: re-derived date {ds} is outside window {args.start}..{args.end}")
        if row.get("is_marathon") and base == "Live":
            # marathon split rows carry a per-faculty share; re-derive only date + category, not minutes
            if cat != "Live" or ds != row["date_str"]:
                rederive_fail.append(f"{vid}: marathon row re-derived cat={cat} date={ds} vs {row['date_str']}")
            continue
        if cat != base:
            rederive_fail.append(f"{vid}: category {cat} != {base}")
        if ds != row["date_str"]:
            rederive_fail.append(f"{vid}: date {ds} != {row['date_str']}")
        if base in ("Live", "LF") and dmin != row["duration_min"]:
            rederive_fail.append(f"{vid}: duration {dmin} != {row['duration_min']}")
    report["checks"]["rederive"] = {"pass": not rederive_fail, "count": len(placed_rows),
                                    "failures": rederive_fail}
    mismatches.extend(rederive_fail)

    # check 3: independent deeper re-walk, confirm nothing in-window is missing.
    # Walks each tab newest-first with its own early-stop, at a DEEPER margin than
    # the pull (7 days vs 3) so it is a genuine second look, not a copy of the pull.
    off = v_offset(cfg.timezone)
    start, end = args.start, args.end
    v_margin = 7
    vstop = (date.fromisoformat(start) - timedelta(days=v_margin)).isoformat()
    try:
        days_from_today = max(doc["window"]["days"], (date.today() - date.fromisoformat(start)).days + 1)
    except Exception:
        days_from_today = doc["window"]["days"]
    cap = min(800, (days_from_today + cfg.lookback_days + 5) * 6)
    missing: list[dict] = []
    seen: set[str] = set()
    for ch in cfg.channels:
        for tab in yt.TABS:
            ids = yt.discover_ids(ch.handle, tab, cap)
            stab = {vid: tab for vid in ids}
            for i in range(0, len(ids), 40):
                chunk = [v for v in ids[i:i + 40] if v not in seen]
                if not chunk:
                    continue
                raws = yt.fetch_details(chunk, stab, batch=40)
                newest = None
                for r in raws:
                    seen.add(r.video_id)
                    cat, ds, _ = v_categorize(r, cfg)
                    rel = r.release_timestamp if (r.was_live and r.release_timestamp) else r.timestamp
                    if rel is not None:
                        di = v_ist(rel, off).date().isoformat()
                        if newest is None or di > newest:
                            newest = di
                    if cat.startswith("EXCLUDE"):
                        continue
                    if (start <= v_iso(ds) <= end and r.video_id not in id_to_buckets
                            and r.video_id not in excluded_ids):
                        missing.append({"video_id": r.video_id, "title": r.title, "url": r.url,
                                        "date_str": ds, "channel": ch.label, "category": cat})
                if newest is not None and newest < vstop:
                    break
    report["checks"]["air_date_rewalk"] = {"pass": not missing, "missing": missing}
    if missing:
        mismatches.append(f"{len(missing)} in-window video(s) found by re-walk but missing from rows.json")

    if mismatches:
        report["overall"] = "FAIL"
        report["mismatches"] = mismatches
    (out_dir / "verify_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"[verify] check 1 re-derivation : {'PASS' if not rederive_fail else 'FAIL'} ({len(placed_rows)} rows)")
    print(f"[verify] check 2 no cross-bucket dup : {'PASS' if not dup else 'FAIL'}")
    print(f"[verify] check 3 re-walk missing : {'PASS' if not missing else f'FAIL ({len(missing)})'}")
    if report["overall"] == "PASS":
        print("[verify] PASS -- independent re-derivation agrees with the file")
        return 0
    print("\n[verify] FAIL:", file=sys.stderr)
    for m in mismatches:
        print(f"  - {m}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
