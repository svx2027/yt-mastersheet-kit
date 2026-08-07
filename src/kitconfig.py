"""Load and validate the one file that makes this kit yours: config/vertical.yaml,
plus the roster / alias / email / subject inputs it points at.

Everything vertical-specific (which exam, which channels, which faculty, which
subjects, how often you post) lives in config + inputs. NONE of it is hardcoded
in the pipeline. That is the whole point of the kit: the engine is shared and
proven; you only ever edit config and inputs.

A non-technical person edits these files, so every failure here is a plain-English
sentence that says which file to open and what to fix, never a stack trace.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - guarded so the message is friendly
    print("Missing dependency 'pyyaml'. Run:  pip install -r requirements.txt", file=sys.stderr)
    raise

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
INPUTS_DIR = REPO_ROOT / "inputs"
OUTPUT_ROOT = REPO_ROOT / "output"

# The live config the recipient actually runs on. The kit ships an *example*
# (vertical.example.yaml); /yt-setup copies it to vertical.yaml and fills it in.
CONFIG_PATH = CONFIG_DIR / "vertical.yaml"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "vertical.example.yaml"


def die(*lines: str) -> None:
    """Stop with a plain-English message aimed at a non-coder."""
    print("\nSETUP PROBLEM", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    sys.exit(3)


@dataclass
class Channel:
    label: str          # internal name, used in bucket/block names (e.g. "Main")
    handle: str         # @handle, full URL, or UC... channel id
    language: str       # "main" or "english" (controls the "Eng- " shorts prefix + dedup side)
    is_primary: bool


@dataclass
class KitConfig:
    name: str                       # short vertical token -> master column D (e.g. "MATH")
    display_name: str
    timezone: str
    channels: list[Channel]
    shorts_max_seconds: int
    longform_min_seconds: int
    marathon_min_minutes: int
    lookback_days: int
    expected_weekly: dict           # {"live": n, "longform": n, "shorts": n}
    placeholder: str                # "Channel Official" style no-individual-faculty marker
    # inputs
    roster: list[str] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    emails: dict[str, str] = field(default_factory=dict)
    subject_keywords: list[tuple[str, list[str]]] = field(default_factory=list)
    default_subject_by_faculty: dict[str, str] = field(default_factory=dict)
    brand_content_patterns: list[str] = field(default_factory=list)

    @property
    def primary_channel(self) -> Channel:
        for c in self.channels:
            if c.is_primary:
                return c
        return self.channels[0]

    @property
    def is_multi_channel(self) -> bool:
        return len(self.channels) > 1


def _require(d: dict, key: str, where: str):
    if key not in d or d[key] in (None, ""):
        die(f"'{key}' is missing under {where} in config/vertical.yaml.",
            "Open config/vertical.yaml and fill it in (config/vertical.example.yaml shows a full example).")
    return d[key]


# The kit dates on a fixed +5:30 offset (see categorize.tz_from_name). These are
# the only timezone values it understands; anything else would silently become UTC
# and shift every date, so it is rejected up front instead.
ACCEPTED_TIMEZONES = {"Asia/Kolkata", "Asia/Calcutta", "IST"}


def _int(d: dict, key: str, default: int, where: str) -> int:
    val = d.get(key, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        die(f"'{key}' under {where} in config/vertical.yaml must be a number, got {val!r}.",
            "Open config/vertical.yaml and set it to a plain number (no quotes, no text).")


def load_config(path: Path | None = None) -> KitConfig:
    path = path or CONFIG_PATH
    if not path.exists():
        die(f"config/vertical.yaml not found ({path}).",
            "Run  /yt-setup  (or copy config/vertical.example.yaml to config/vertical.yaml and edit it).")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        die("config/vertical.yaml is not valid YAML (a typo in the formatting).",
            f"Details: {e}")

    v = raw.get("vertical") or {}
    name = _require(v, "name", "vertical:")
    display_name = v.get("display_name") or name
    timezone = v.get("timezone") or "Asia/Kolkata"
    if timezone not in ACCEPTED_TIMEZONES:
        die(f"timezone '{timezone}' is not supported. This kit currently dates on IST only.",
            f"Set  timezone: \"Asia/Kolkata\"  in config/vertical.yaml (accepted: {', '.join(sorted(ACCEPTED_TIMEZONES))}).")

    chans_raw = raw.get("channels") or []
    if not chans_raw:
        die("No channels listed in config/vertical.yaml under 'channels:'.",
            "Add at least one channel (your own YouTube channel for this vertical).")
    channels: list[Channel] = []
    for i, c in enumerate(chans_raw):
        label = _require(c, "label", f"channels[{i}]:")
        handle = _require(c, "handle", f"channels[{i}]:")
        language = (c.get("language") or "main").lower()
        if language not in ("main", "english"):
            die(f"channels[{i}].language is '{language}', must be 'main' or 'english'.")
        channels.append(Channel(label=label, handle=handle, language=language,
                                is_primary=bool(c.get("is_primary", False))))
    if not any(c.is_primary for c in channels):
        channels[0].is_primary = True  # first channel is primary by default
    if sum(1 for c in channels if c.is_primary) > 1:
        die("More than one channel is marked is_primary: true in config/vertical.yaml.",
            "Exactly one channel is the primary. Set is_primary: true on one, false on the rest.")

    cat = raw.get("categorization") or {}
    shorts_max = _int(cat, "shorts_max_seconds", 180, "categorization:")
    lf_min = _int(cat, "longform_min_seconds", 300, "categorization:")
    marathon_min = _int(cat, "marathon_min_minutes", 240, "categorization:")

    disc = raw.get("discovery") or {}
    lookback = _int(disc, "lookback_days", 30, "discovery:")
    expected = disc.get("expected_weekly") or {}
    expected_weekly = {
        "live": _int(expected, "live", 0, "discovery.expected_weekly:"),
        "longform": _int(expected, "longform", 0, "discovery.expected_weekly:"),
        "shorts": _int(expected, "shorts", 0, "discovery.expected_weekly:"),
    }

    roster_cfg = raw.get("roster") or {}
    placeholder = roster_cfg.get("placeholder") or "Channel Official"

    cfg = KitConfig(
        name=name, display_name=display_name, timezone=timezone, channels=channels,
        shorts_max_seconds=shorts_max, longform_min_seconds=lf_min,
        marathon_min_minutes=marathon_min, lookback_days=lookback,
        expected_weekly=expected_weekly, placeholder=placeholder,
    )

    cfg.roster = _load_roster(roster_cfg.get("faculties_file", "inputs/faculties.csv"))
    cfg.aliases = _load_aliases(roster_cfg.get("aliases_file", "inputs/aliases.csv"))
    cfg.emails = _load_emails(roster_cfg.get("emails_file", "inputs/faculty_emails.csv"))
    _load_subjects(raw.get("subjects") or {}, cfg)
    return cfg


def _resolve(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO_ROOT / pp)


def _load_roster(rel: str) -> list[str]:
    p = _resolve(rel)
    if not p.exists():
        die(f"Faculty roster file not found: {rel}",
            "This is the list of your teachers' names. Run /yt-setup, or create it "
            "(one name per line, a header row on top).")
    rows = []
    with open(p, newline="") as f:
        r = csv.reader(f)
        for i, row in enumerate(r):
            if not row:
                continue
            name = row[0].strip()
            if i == 0 and name.lower() in ("name", "faculty", "faculties"):
                continue  # header
            if name:
                rows.append(name)
    if not rows:
        die(f"The faculty roster {rel} is empty.",
            "Add your teachers' names (one per line). The pipeline needs them to attribute videos.")
    return rows


def _load_aliases(rel: str) -> dict[str, list[str]]:
    p = _resolve(rel)
    aliases: dict[str, list[str]] = {}
    if not p.exists():
        return aliases  # optional
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            canon = (row.get("canonical") or "").strip()
            alias = (row.get("alias") or "").strip()
            if canon and alias:
                aliases.setdefault(canon, []).append(alias)
    return aliases


def _load_emails(rel: str) -> dict[str, str]:
    p = _resolve(rel)
    out: dict[str, str] = {}
    if not p.exists():
        return out  # optional, built up incrementally
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if name and email:
                out[name] = email
    return out


def _load_subjects(subj_cfg: dict, cfg: KitConfig) -> None:
    """Subjects can be inline in vertical.yaml or in a pointed-at file."""
    data = subj_cfg
    file_rel = subj_cfg.get("file")
    if file_rel:
        p = _resolve(file_rel)
        if not p.exists():
            die(f"Subjects file not found: {file_rel}",
                "This maps title keywords to your exam's subjects. Run /yt-setup or create it.")
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as e:
            die(f"{file_rel} is not valid YAML.", f"Details: {e}")

    kws = []
    for entry in (data.get("keywords") or []):
        subject = (entry.get("subject") or "").strip()
        patterns = [str(x) for x in (entry.get("patterns") or []) if str(x).strip()]
        if subject and patterns:
            kws.append((subject, patterns))
    cfg.subject_keywords = kws
    cfg.default_subject_by_faculty = {
        str(k).strip(): str(v).strip()
        for k, v in (data.get("default_by_faculty") or {}).items() if str(v).strip()
    }
    cfg.brand_content_patterns = [str(x).strip().lower()
                                  for x in (data.get("brand_content_patterns") or []) if str(x).strip()]
