#!/usr/bin/env python3
"""An OFFLINE STAND-IN FOR yt-dlp, used only to (re)generate docs/sample_run/.
It is NOT part of the pipeline, is never referenced by requirements.txt, and a
real run of this kit never touches it -- src/ only ever calls the real yt-dlp.

It understands exactly the two call shapes src/ytdlp_client.py makes:
  1. discover_ids(): `yt-dlp --flat-playlist ... --print %(id)s <channel-tab-url>`
  2. fetch_details(): `yt-dlp ... --print <SEP-joined template> <watch-url> [...]`
and answers them from the fixed local catalog.json (built by build_catalog.py)
instead of a real network fetch to YouTube.

To use it: put a copy or symlink of this file, named exactly `yt-dlp`, ahead of
everything else on PATH. See docs/sample_run/README.md for the full recipe.
"""
import json
import os
import sys

SEP = "\x1f"
FIELDS = ["id", "duration", "timestamp", "release_timestamp",
          "live_status", "was_live", "channel_id", "availability", "title"]

HERE = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
with open(os.path.join(HERE, "catalog.json")) as f:
    CATALOG = json.load(f)
BY_ID = {v["id"]: v for v in CATALOG}


def fmt(v, field):
    val = v.get(field)
    if val is None:
        return "NA"
    if field == "was_live":
        return "True" if val else "False"
    return str(val)


def main() -> int:
    args = sys.argv[1:]

    if "--version" in args:
        print("2026.01.01 [offline-demo-stub, see docs/sample_run/README.md]")
        return 0

    if "--flat-playlist" in args:
        # discover_ids(): the last positional arg is the channel-tab URL,
        # e.g. https://www.youtube.com/@MathPrepDemo/videos
        url = args[-1]
        tab = url.rstrip("/").rsplit("/", 1)[-1]
        for v in CATALOG:
            if v["tab"] == tab:
                print(v["id"])
        return 0

    # fetch_details(): every positional arg that is a watch URL
    watch_prefix = "https://www.youtube.com/watch?v="
    ids = [a[len(watch_prefix):] for a in args if a.startswith(watch_prefix)]
    lines = []
    for vid in ids:
        v = BY_ID.get(vid)
        if v is None or v.get("_omit_from_details"):
            continue  # simulates a failed per-video fetch: prints nothing for it
        lines.append(SEP.join(fmt(v, f) for f in FIELDS))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
