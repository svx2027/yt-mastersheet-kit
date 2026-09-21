"""Builds the synthetic video catalog behind docs/sample_run/. It describes 14
made-up videos for the fictional "Demo MATH Prep" (@MathPrepDemo) vertical that
already ships in config/vertical.example.yaml and inputs/*.example.*  -- the
same fictional identity the Quickstart and tests/ use. Nothing here is real
YouTube data; every id, title, and date is invented for this demo.

Run it, then point fake_yt_dlp.py's directory at a `yt-dlp` on PATH (see
docs/sample_run/README.md) to regenerate the sample run from scratch.
"""
import json
import os
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))


def ist(y, m, d, hh, mm):
    return int(datetime(y, m, d, hh, mm, tzinfo=IST).timestamp())


CHANNEL_ID = "UCFICTIONALDEMOMATHPREP1"

# Each entry: id, tab, duration(sec or None), timestamp(publish, unix or None),
# release_timestamp(air time, unix or None), live_status, was_live, title.
# _omit_from_details=True means the id is DISCOVERED (shows up in a channel-tab
# listing) but the per-video detail fetch never returns it -- this is how the
# demo exercises the fetch-failed / never-silently-dropped path.
VIDEOS = [
    # ---- streams tab: genuine lives, one is_upcoming, one fetch-failed, and a
    #      premiere that got listed under /streams (the "premieres are not
    #      lives" case) ----
    dict(id="live001", tab="streams", duration=3600,
         timestamp=ist(2026, 6, 30, 20, 0), release_timestamp=ist(2026, 7, 1, 18, 0),
         live_status="was_live", was_live=True,
         title="Algebra Live Class | Meera Iyer Ma'am"),
    dict(id="live002", tab="streams", duration=14400,
         timestamp=ist(2026, 7, 2, 21, 0), release_timestamp=ist(2026, 7, 3, 9, 0),
         live_status="was_live", was_live=True,
         title="Weekly Full Day Marathon: Arjun Rao Sir and Devika Menon"),
    dict(id="live003", tab="streams", duration=3000,
         timestamp=ist(2026, 7, 5, 15, 30), release_timestamp=ist(2026, 7, 5, 16, 0),
         live_status="was_live", was_live=True,
         title="Doubt Clearing Session"),
    dict(id="live004", tab="streams", duration=None,
         timestamp=ist(2026, 7, 6, 10, 0), release_timestamp=None,
         live_status="is_upcoming", was_live=True,
         title="Upcoming: Geometry Marathon (Scheduled)"),
    dict(id="live005", tab="streams", duration=None, timestamp=None,
         release_timestamp=None, live_status="NA", was_live=None,
         title="(simulated fetch failure)", _omit_from_details=True),
    dict(id="lf003", tab="streams", duration=2700,
         timestamp=ist(2026, 7, 6, 19, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Full Mock Test Premiere: Time and Work"),

    # ---- videos tab: long-form ----
    dict(id="lf001", tab="videos", duration=1800,
         timestamp=ist(2026, 7, 2, 11, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Coordinate Geometry Full Chapter | Arjun Rao Sir"),
    dict(id="lf002", tab="videos", duration=900,
         timestamp=ist(2026, 7, 4, 9, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="HCF and LCM Tricks | Devika Menon"),
    dict(id="lf004", tab="videos", duration=600,
         timestamp=ist(2026, 7, 7, 8, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Fun Friday Quiz Round 12"),
    dict(id="lf005", tab="videos", duration=1200,
         timestamp=ist(2026, 7, 6, 14, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Combined Revision: Arjun Rao Sir and Devika Menon"),
    dict(id="gap001", tab="videos", duration=220,
         timestamp=ist(2026, 7, 2, 16, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Bonus Explainer Clip"),

    # ---- shorts tab ----
    dict(id="sh001", tab="shorts", duration=45,
         timestamp=ist(2026, 7, 1, 7, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Quick Trick: Percentages in 30 Seconds | Meera Iyer Ma'am"),
    dict(id="sh002", tab="shorts", duration=50,
         timestamp=ist(2026, 7, 3, 7, 30), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Common Mistake in Probability | Arjun Rao Sir"),
    dict(id="sh003", tab="shorts", duration=40,
         timestamp=ist(2026, 7, 5, 8, 0), release_timestamp=None,
         live_status="not_live", was_live=False,
         title="Orientation Session Walkthrough"),
]

for v in VIDEOS:
    v["channel_id"] = CHANNEL_ID
    v["availability"] = "public"
    v.setdefault("_omit_from_details", False)

if __name__ == "__main__":
    out_path = os.path.join(HERE, "catalog.json")
    with open(out_path, "w") as f:
        json.dump(VIDEOS, f, indent=2)
    print(f"wrote {len(VIDEOS)} synthetic videos -> {out_path}")
    for v in VIDEOS:
        print(f"  {v['id']:<10} {v['tab']:<8} dur={str(v['duration']):>6} title={v['title'][:60]}")
