"""Dating, duration, and categorization rules. Used by pull.py.

verify.py deliberately does NOT import this module -- it re-implements the same
rules on a separate code path, so when the two agree it actually means the logic
is right and not just that one buggy function was called twice. (tests/ cross-
checks that the two independent implementations agree.)

The rules, all doctrine, do not weaken without a reason written next to the change:
  - Timezone: everything is the vertical's configured tz (IST by default). Windows
    are inclusive calendar days in that tz.
  - Lives are dated by their AIR time (release_timestamp = actualStartTime), NOT
    their publish time. A live's publish time is the placeholder or the VOD
    release and can be a different day -- dating by it mislabels sessions
    (a Thursday live shows as Wednesday).
  - Shorts and long-form are dated by publish time (timestamp).
  - Duration for Live/LF is the VOD length rounded UP to the next whole minute
    (ceil). Any leftover seconds bump the minute: 12m01s -> 13. Always round up,
    never to nearest. Shorts carry no duration.
  - Premieres are NOT lives. was_live (isLiveContent) is the authority: a genuine
    livestream is was_live=True; a premiere is was_live=False and falls to
    Long-form/Shorts by duration, dated by publish.
  - An unaired placeholder (is_upcoming) and a still-airing live (is_live, or
    post_live with no usable VOD yet) are excluded and flagged for a re-pull --
    writing them would inject a 0-minute or misdated row.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def tz_from_name(name: str) -> timezone:
    """Return a fixed-offset tzinfo. Asia/Kolkata is UTC+5:30 (no DST), which is
    all this pipeline needs; using a fixed offset avoids a zoneinfo dependency."""
    if name in ("Asia/Kolkata", "Asia/Calcutta", "IST"):
        return timezone(timedelta(hours=5, minutes=30))
    # Fallback: allow "UTC+H:MM" style, else UTC.
    return timezone(timedelta(0))


def to_ist(unix_ts: int, tz: timezone) -> datetime:
    return datetime.fromtimestamp(int(unix_ts), tz)


def date_str(dt: datetime) -> str:
    """'27-Jul-2026' -- the master-tracker date format (locale-independent)."""
    return f"{dt.day:02d}-{_MONTHS[dt.month]}-{dt.year}"


def duration_min_ceil(seconds: int | None) -> int | None:
    if seconds is None:
        return None
    return math.ceil(seconds / 60)


@dataclass
class Decision:
    category: str                 # "Live" | "LF" | "Shorts" | "EXCLUDE"
    reason: str = ""              # exclusion reason when category == "EXCLUDE"
    date_str: str | None = None
    ist_iso: str | None = None
    duration_min: int | None = None
    is_marathon: bool = False
    flags: list[str] = field(default_factory=list)


def categorize(raw, cfg) -> Decision:
    """Classify one RawVideo. `cfg` is a KitConfig (thresholds + tz)."""
    tz = tz_from_name(cfg.timezone)
    title = raw.title or ""
    ls = (raw.live_status or "NA").lower()

    # --- not-yet-aired / still-airing: exclude, flag for re-pull -------------
    if ls == "is_upcoming":
        return Decision("EXCLUDE", reason="unaired")
    if ls == "is_live":
        return Decision("EXCLUDE", reason="live-in-progress")
    if ls == "post_live" and not raw.duration:
        # ended moments ago, VOD still processing -> no usable length yet
        return Decision("EXCLUDE", reason="live-in-progress")

    is_genuine_live = raw.was_live is True

    # --- genuine livestream -------------------------------------------------
    if is_genuine_live:
        if not raw.duration:
            return Decision("EXCLUDE", reason="live-in-progress")
        flags: list[str] = []
        air_ts = raw.release_timestamp
        if not air_ts:  # None OR 0 -- match verify's truthiness guard, no 1970 dates
            # A genuine live with no air timestamp is unusual; fall back to
            # publish time but flag it loudly for a human to sanity-check.
            air_ts = raw.timestamp
            flags.append("live-missing-airtime")
        if not air_ts:
            return Decision("EXCLUDE", reason="live-no-date", flags=["live-no-date"])
        dt = to_ist(air_ts, tz)
        dmin = duration_min_ceil(raw.duration)
        is_marathon = (dmin is not None and dmin >= cfg.marathon_min_minutes) \
            or ("marathon" in title.lower())
        return Decision("Live", date_str=date_str(dt), ist_iso=dt.isoformat(),
                        duration_min=dmin, is_marathon=is_marathon, flags=flags)

    # --- premiere or plain upload: date by publish, categorize by duration --
    if raw.timestamp is None:
        return Decision("EXCLUDE", reason="no-publish-date")
    dt = to_ist(raw.timestamp, tz)
    dur = raw.duration
    flags = []
    if raw.source_tab == "streams" and raw.was_live is False:
        flags.append("premiere-from-streams-tab")  # informational: a premiere, not a live
    if not dur:  # None OR 0 -- a 0-length VOD (still processing / withdrawn) is not a Short
        return Decision("EXCLUDE", reason="no-duration", flags=flags)
    if dur <= cfg.shorts_max_seconds:
        return Decision("Shorts", date_str=date_str(dt), ist_iso=dt.isoformat(),
                        duration_min=None, flags=flags)
    if dur >= cfg.longform_min_seconds:
        return Decision("LF", date_str=date_str(dt), ist_iso=dt.isoformat(),
                        duration_min=duration_min_ceil(dur), flags=flags)
    # 181-299s gap: no long-form under 5 min on these channels
    return Decision("EXCLUDE", reason="gap-181-299s", flags=flags)


def in_window(date_str_val: str, start: str, end: str) -> bool:
    """Both endpoints inclusive. date_str_val is 'DD-Mon-YYYY'; start/end are ISO."""
    d = _parse_date_str(date_str_val)
    return start <= d <= end


def _parse_date_str(s: str) -> str:
    """'27-Jul-2026' -> '2026-07-27' for comparison."""
    day, mon, year = s.split("-")
    m = _MONTHS.index(mon)
    return f"{int(year):04d}-{m:02d}-{int(day):02d}"
