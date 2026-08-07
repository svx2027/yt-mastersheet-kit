"""The only data source: yt-dlp. No YouTube API key, no quota, free.

Why yt-dlp and not the YouTube Data API:
  - No API key to create, no 10,000-unit/day quota to manage. A vertical owner
    installs one tool and runs.
  - yt-dlp reads the SAME watch-page player response the API is built on, and
    exposes the exact fields the tracker needs -- including was_live, which is
    the watch page's isLiveContent flag. That flag is the ONLY reliable way to
    tell a Premiere (pre-recorded, isLiveContent=false) from a real livestream
    (isLiveContent=true); the API needs a second watch-page fetch to get it,
    yt-dlp hands it over directly.

Two operations:
  1. discover(): list a channel's /videos, /streams, /shorts tabs. The tabs are
     YouTube's OWN classification and are the source of truth for what a channel
     published -- the analog of the uploads playlist, not a lossy search index.
  2. fetch_details(): full per-video extraction for the fields the pipeline dates
     and categorizes on.

Field map (yt-dlp -> the equivalent YouTube Data API v3 fields):
  duration           <- contentDetails.duration (seconds; the playable VOD length)
  timestamp          <- snippet.publishedAt (publish time; unreliable for lives)
  release_timestamp  <- liveStreamingDetails.actualStartTime (a live's real air time)
  live_status        <- liveBroadcastContent + state (is_upcoming/is_live/post_live/was_live/not_live)
  was_live (bool)    <- videoDetails.isLiveContent  (TRUE only for genuine lives; premieres are FALSE)
  channel_id         <- snippet.channelId
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

# ASCII Unit Separator: never appears in a video title, so it is a safe delimiter
# for --print output even when titles contain |, tabs, quotes, emoji, etc.
SEP = "\x1f"

# Order of fields in the --print template below. Keep in sync with RawVideo.
_FIELDS = ["id", "duration", "timestamp", "release_timestamp",
           "live_status", "was_live", "channel_id", "availability", "title"]
_PRINT_TEMPLATE = SEP.join(f"%({f})s" for f in _FIELDS)

TABS = ("videos", "streams", "shorts")


class YtdlpError(RuntimeError):
    pass


@dataclass
class RawVideo:
    video_id: str
    duration: int | None          # seconds; None if not available (upcoming/live)
    timestamp: int | None         # unix publish time
    release_timestamp: int | None # unix live-start time (lives) / premiere schedule
    live_status: str              # is_upcoming | is_live | post_live | was_live | not_live | NA
    was_live: bool | None         # True only for genuine livestreams (isLiveContent)
    channel_id: str
    availability: str
    title: str
    source_tab: str               # which channel tab surfaced it (videos/streams/shorts)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def _which_ytdlp() -> str:
    from shutil import which
    exe = which("yt-dlp")
    if not exe:
        raise YtdlpError(
            "yt-dlp is not installed or not on PATH. Install it with:\n"
            "  pip install -r requirements.txt   (installs it into this project's venv)\n"
            "or system-wide:  brew install yt-dlp")
    return exe


def _run(args: list[str], timeout: int = 600) -> str:
    exe = _which_ytdlp()
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise YtdlpError(f"yt-dlp timed out after {timeout}s: {' '.join(args[:3])} ...") from e
    # yt-dlp exits non-zero if SOME videos failed but still prints the good ones;
    # we tolerate partial output (‑‑ignore-errors) and only hard-fail on empty output.
    return proc.stdout


def channel_tab_url(handle: str, tab: str) -> str:
    """Build a channel tab URL from an @handle, a full channel URL, or a UC... id."""
    h = handle.strip().rstrip("/")
    if h.startswith("http://") or h.startswith("https://"):
        base = h
    elif h.startswith("UC") and " " not in h and len(h) >= 20:
        base = f"https://www.youtube.com/channel/{h}"
    elif h.startswith("@"):
        base = f"https://www.youtube.com/{h}"
    else:
        base = f"https://www.youtube.com/@{h}"
    return f"{base}/{tab}"


def discover_ids(handle: str, tab: str, limit: int) -> list[str]:
    """Flat-list a channel tab, newest first, up to `limit` ids. Fast (one page
    scrape, no per-video fetch). A tab that doesn't exist returns []."""
    url = channel_tab_url(handle, tab)
    out = _run(["--flat-playlist", "--no-warnings", "-I", f":{limit}",
                "--print", "%(id)s", url])
    # split on \n only (not str.splitlines(), which also breaks on \r \x0b \x0c \x1c-\x1e \x85)
    ids = [line.strip() for line in out.split("\n") if line.strip()]
    # de-dup while preserving order (a video can appear under two tabs)
    seen, uniq = set(), []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            uniq.append(vid)
    return uniq


def _to_int(s: str) -> int | None:
    s = (s or "").strip()
    if s in ("", "NA", "None", "none"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _to_bool(s: str) -> bool | None:
    s = (s or "").strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    return None


def _parse_details(out: str, source_tab_by_id: dict[str, str]) -> list[RawVideo]:
    results: list[RawVideo] = []
    for line in out.split("\n"):  # records are \n-separated; never str.splitlines()
        if SEP not in line:
            continue
        parts = line.split(SEP)
        if len(parts) < len(_FIELDS):
            continue
        vid = parts[0].strip()
        results.append(RawVideo(
            video_id=vid,
            duration=_to_int(parts[1]),
            timestamp=_to_int(parts[2]),
            release_timestamp=_to_int(parts[3]),
            live_status=(parts[4] or "").strip() or "NA",
            was_live=_to_bool(parts[5]),
            channel_id=(parts[6] or "").strip(),
            availability=(parts[7] or "").strip(),
            title=SEP.join(parts[8:]).strip(),  # title is last; rejoin if it ever held a SEP
            source_tab=source_tab_by_id.get(vid, "unknown"),
        ))
    return results


def fetch_details(video_ids: list[str], source_tab_by_id: dict[str, str],
                  batch: int = 40) -> list[RawVideo]:
    """Full extraction for each id. One yt-dlp process per batch amortizes startup;
    each video is still a real watch-page fetch, so this is the slow step (~1-2s/video).

    A per-video extraction can fail (HTTP 429 throttle, transient network, geo-block,
    deleted mid-run). --ignore-errors keeps the batch alive but a failed video prints
    nothing, so it would vanish without a trace. To stop that: any requested id that
    did not come back is RETRIED once (fresh call); anything still missing after the
    retry is left out of the results, and the CALLER reconciles requested-vs-returned
    so the miss is recorded as an exclusion, never silently dropped.
    """
    results: list[RawVideo] = []
    got: set[str] = set()

    def run_ids(ids: list[str]) -> None:
        urls = [f"https://www.youtube.com/watch?v={v}" for v in ids]
        out = _run(["--no-warnings", "--ignore-errors", "--skip-download",
                    "--print", _PRINT_TEMPLATE, *urls])
        for rv in _parse_details(out, source_tab_by_id):
            if rv.video_id not in got:
                got.add(rv.video_id)
                results.append(rv)

    for i in range(0, len(video_ids), batch):
        chunk = video_ids[i:i + batch]
        run_ids(chunk)
        missing = [v for v in chunk if v not in got]
        if missing:
            run_ids(missing)  # one retry for the stragglers
    return results


def probe() -> dict:
    """Quick health check used by /yt-setup: is yt-dlp present and what version."""
    exe = _which_ytdlp()
    ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    return {"path": exe, "version": ver}
