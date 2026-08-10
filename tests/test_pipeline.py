"""Pure-function tests -- no network, no yt-dlp. Run:

    .venv/bin/python -m unittest discover -s tests -v

Extend this file when you change a rule; don't hand-verify a rule change by
eyeballing one window's output.
"""
from __future__ import annotations

import unittest

from src import categorize as C
from src import format_master as F
from src.faculty import build_detector
from src.kitconfig import Channel, KitConfig
from src.pull import split_minutes
from src.verify import v_ceil_min
from src.ytdlp_client import RawVideo


def make_cfg(**over) -> KitConfig:
    cfg = KitConfig(
        name="MATH", display_name="Demo MATH Prep", timezone="Asia/Kolkata",
        channels=[Channel("Main", "@MathPrepDemo", "main", True)],
        shorts_max_seconds=180, longform_min_seconds=300, marathon_min_minutes=240,
        lookback_days=30, expected_weekly={"live": 5, "longform": 3, "shorts": 12},
        placeholder="Channel Official",
    )
    cfg.roster = ["Meera Iyer Ma'am", "Arjun Rao Sir", "Devika Menon"]
    cfg.aliases = {"Meera Iyer Ma'am": ["Meera Ma'am", "Meera Iyer"]}
    cfg.emails = {"Arjun Rao Sir": "arjun@example.com"}
    cfg.subject_keywords = [
        ("Algebra", ["algebra", "linear equations", "quadratic equations"]),
        ("Geometry", ["geometry", "triangles", "coordinate geometry"]),
        ("Statistics & Probability", ["statistics", "probability"]),
        ("Arithmetic", [r"\barithmetic\b", "percentages"]),
    ]
    cfg.default_subject_by_faculty = {"Arjun Rao Sir": "Geometry"}
    cfg.brand_content_patterns = ["meet the instructors", "orientation session"]
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


def raw(**over) -> RawVideo:
    base = dict(video_id="x", duration=600, timestamp=1705293000, release_timestamp=None,
                live_status="not_live", was_live=False, channel_id="UC", availability="public",
                title="A Title", source_tab="videos")
    base.update(over)
    return RawVideo(**base)


class TestDurationAndDates(unittest.TestCase):
    def test_ceil_rounds_up_any_leftover_seconds(self):
        self.assertEqual(C.duration_min_ceil(721), 13)   # 12m01s -> 13
        self.assertEqual(C.duration_min_ceil(720), 12)   # exact
        self.assertEqual(C.duration_min_ceil(62), 2)     # 1m02s -> 2
        self.assertEqual(C.duration_min_ceil(1), 1)

    def test_pull_and_verify_ceil_agree(self):
        # the two independent implementations must never diverge
        for s in [1, 59, 60, 61, 120, 599, 600, 3302, 39841, 86399]:
            self.assertEqual(C.duration_min_ceil(s), v_ceil_min(s), f"ceil mismatch at {s}s")

    def test_date_str_format(self):
        cfg = make_cfg()
        # 1705293000 = 2024-01-15 10:00 IST
        r = raw(timestamp=1705293000, duration=600)
        d = C.categorize(r, cfg)
        self.assertEqual(d.date_str, "15-Jan-2024")

    def test_longform_publish_time_ist_midnight_boundary(self):
        # 1705343399 and 1705343400 are exactly one second apart in absolute
        # time (18:29:59 UTC and 18:30:00 UTC on the same UTC calendar day),
        # but that one second straddles IST midnight: 23:59:59 IST on 15-Jan
        # vs 00:00:00 IST on 16-Jan. A long-form/short is dated by publish
        # time (timestamp), so this proves dating is done in the configured
        # timezone (IST), not in UTC -- a UTC-dated pipeline would report
        # both rows as 15-Jan-2024.
        cfg = make_cfg()
        just_before = C.categorize(raw(timestamp=1705343399, duration=600), cfg)
        just_after = C.categorize(raw(timestamp=1705343400, duration=600), cfg)
        self.assertEqual(just_before.date_str, "15-Jan-2024")
        self.assertEqual(just_after.date_str, "16-Jan-2024")

    def test_live_air_time_ist_midnight_boundary(self):
        # Same one-second UTC gap, but on the AIR time (release_timestamp) of
        # a genuine livestream, since lives are dated by air time, never by
        # publish time. Publish time is held fixed and unrelated so the test
        # isolates the boundary to release_timestamp specifically.
        cfg = make_cfg()
        just_before = C.categorize(raw(was_live=True, live_status="was_live", duration=3600,
                                       timestamp=1705200000, release_timestamp=1705343399,
                                       source_tab="streams"), cfg)
        just_after = C.categorize(raw(was_live=True, live_status="was_live", duration=3600,
                                      timestamp=1705200000, release_timestamp=1705343400,
                                      source_tab="streams"), cfg)
        self.assertEqual(just_before.date_str, "15-Jan-2024")
        self.assertEqual(just_after.date_str, "16-Jan-2024")

    def test_pull_and_verify_agree_at_ist_midnight_boundary(self):
        # The two independent categorize implementations (pull's C.categorize
        # and verify's v_categorize) must agree on which side of the boundary
        # a video falls, not just on ordinary mid-day timestamps.
        cfg = make_cfg()
        from src import verify as V
        r_before = raw(timestamp=1705343399, duration=600)
        r_after = raw(timestamp=1705343400, duration=600)
        _, v_ds_before, _ = V.v_categorize(r_before, cfg)
        _, v_ds_after, _ = V.v_categorize(r_after, cfg)
        self.assertEqual(C.categorize(r_before, cfg).date_str, v_ds_before)
        self.assertEqual(C.categorize(r_after, cfg).date_str, v_ds_after)


class TestCategorize(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def test_short(self):
        d = C.categorize(raw(duration=45, source_tab="shorts"), self.cfg)
        self.assertEqual(d.category, "Shorts")
        self.assertIsNone(d.duration_min)

    def test_longform(self):
        d = C.categorize(raw(duration=600), self.cfg)
        self.assertEqual(d.category, "LF")
        self.assertEqual(d.duration_min, 10)

    def test_gap_excluded(self):
        d = C.categorize(raw(duration=200), self.cfg)
        self.assertEqual(d.category, "EXCLUDE")
        self.assertEqual(d.reason, "gap-181-299s")

    def test_zero_duration_not_a_short(self):
        # a 0-length non-live video (still processing / withdrawn) must be excluded,
        # never emitted as a bogus 0-second Short
        d = C.categorize(raw(duration=0, was_live=False, live_status="not_live"), self.cfg)
        self.assertEqual((d.category, d.reason), ("EXCLUDE", "no-duration"))

    def test_genuine_live_dated_by_release_not_publish(self):
        # publish 2024-01-15 20:09; air 2024-01-16 07:00 -> must date to the AIR day
        d = C.categorize(raw(was_live=True, live_status="was_live", duration=3444,
                             timestamp=1705329540, release_timestamp=1705368600,
                             source_tab="streams", title="Live Doubt Session"), self.cfg)
        self.assertEqual(d.category, "Live")
        self.assertEqual(d.duration_min, 58)

    def test_premiere_is_not_live(self):
        # was_live False + long -> Long-form, never Live, even from the streams tab
        d = C.categorize(raw(was_live=False, live_status="not_live", duration=2400,
                             source_tab="streams", release_timestamp=None), self.cfg)
        self.assertEqual(d.category, "LF")

    def test_unaired_excluded(self):
        d = C.categorize(raw(live_status="is_upcoming", duration=None, was_live=True), self.cfg)
        self.assertEqual((d.category, d.reason), ("EXCLUDE", "unaired"))

    def test_live_in_progress_excluded(self):
        d = C.categorize(raw(live_status="is_live", duration=None, was_live=True), self.cfg)
        self.assertEqual((d.category, d.reason), ("EXCLUDE", "live-in-progress"))

    def test_post_live_no_vod_excluded(self):
        d = C.categorize(raw(live_status="post_live", duration=None, was_live=True), self.cfg)
        self.assertEqual((d.category, d.reason), ("EXCLUDE", "live-in-progress"))

    def test_marathon_flag(self):
        d = C.categorize(raw(was_live=True, live_status="was_live", duration=15000,
                             release_timestamp=1705293000, source_tab="streams",
                             title="Full Day Marathon"), self.cfg)
        self.assertTrue(d.is_marathon)


class TestFaculty(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.detect = build_detector(self.cfg.roster, self.cfg.aliases)

    def test_mam_maam_variants(self):
        self.assertEqual(self.detect("Algebra Basics | Meera Mam"), ["Meera Iyer Ma'am"])
        self.assertEqual(self.detect("Algebra Basics | Meera Ma'am"), ["Meera Iyer Ma'am"])

    def test_alias_maps_to_canonical(self):
        self.assertEqual(self.detect("Quadratic Equations | Meera Iyer"), ["Meera Iyer Ma'am"])

    def test_zero_and_two(self):
        self.assertEqual(self.detect("Weekly Practice Roundup | 29th July"), [])
        two = self.detect("Combined class | Arjun Rao Sir and Devika Menon")
        self.assertEqual(two, ["Arjun Rao Sir", "Devika Menon"])


class TestFormat(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.detect = build_detector(self.cfg.roster, self.cfg.aliases)

    def test_faculty_placeholder_when_none(self):
        _, disp, amb = F.resolve_faculty("Practice Set Review | 29th July", None, self.detect, self.cfg, False)
        self.assertEqual(disp, "Channel Official")
        self.assertFalse(amb)

    def test_faculty_single(self):
        det, disp, amb = F.resolve_faculty("Quadratic Equations | Meera Iyer", None, self.detect, self.cfg, False)
        self.assertEqual((det, disp, amb), ("Meera Iyer Ma'am", "Meera Iyer Ma'am", False))

    def test_faculty_needs_manual_split(self):
        _, disp, amb = F.resolve_faculty("Arjun Rao Sir & Devika Menon", None, self.detect, self.cfg, False)
        self.assertEqual(disp, F.NEEDS_MANUAL_SPLIT)
        self.assertTrue(amb)

    def test_brand_forces_placeholder_even_with_name(self):
        _, disp, _ = F.resolve_faculty("Orientation Session with Arjun Rao Sir", None, self.detect, self.cfg, True)
        self.assertEqual(disp, "Channel Official")

    def test_subject_keyword_first(self):
        subj, flagged = F.resolve_subject("Complete Algebra Revision", "Channel Official", self.cfg, False)
        self.assertEqual((subj, flagged), ("Algebra", False))

    def test_subject_default_by_faculty(self):
        subj, flagged = F.resolve_subject("Weekly Doubt Session", "Arjun Rao Sir", self.cfg, False)
        self.assertEqual((subj, flagged), ("Geometry", False))

    def test_subject_blank_flagged(self):
        subj, flagged = F.resolve_subject("Random Topic With No Keyword", "Channel Official", self.cfg, False)
        self.assertEqual((subj, flagged), ("", True))

    def test_shorts_topic_transform(self):
        out = F.shorts_topic("Word Problem Mistake: Deconstruct Steps | Rehan Sir Prep", "Rehan Sir", False)
        self.assertEqual(out, "Rehan Sir- word problem mistake: deconstruct steps - rehan sir prep shorts")

    def test_shorts_topic_english_prefix(self):
        out = F.shorts_topic("Vocabulary Trap | Naina Mam", "Naina Mam", True)
        self.assertTrue(out.startswith("Eng- Naina Mam- "))

    def test_shorts_topic_placeholder_drops_prefix(self):
        out = F.shorts_topic("Fraction Rule Students Miss", None, False)
        self.assertEqual(out, "fraction rule students miss shorts")

    def test_dedup_by_session_number(self):
        primary = [{"title": "Class Session 21 | Mentor A", "date_str": "15-Jan-2024",
                    "video_id": "m1", "url": "u1"}]
        sec = [{"title": "Class Session 21 English | Mentor A", "date_str": "15-Jan-2024",
                "video_id": "e1", "url": "u2"},
               {"title": "Unrelated Live", "date_str": "15-Jan-2024", "video_id": "e2", "url": "u3"}]
        kept, ledger = F.dedup_secondary_vs_primary(primary, sec)
        self.assertEqual([r["video_id"] for r in kept], ["e2"])  # e1 dropped, e2 kept
        self.assertEqual(len(ledger), 1)

    def test_dedup_zero_padded_session_matches(self):
        primary = [{"title": "Class Session 21 | Mentor A", "date_str": "15-Jan-2024",
                    "video_id": "m1", "url": "u1"}]
        sec = [{"title": "Class Session 021 English", "date_str": "15-Jan-2024",
                "video_id": "e1", "url": "u2"}]
        kept, ledger = F.dedup_secondary_vs_primary(primary, sec)
        self.assertEqual(kept, [])          # "021" matches "21"
        self.assertEqual(len(ledger), 1)

    def test_marathon_split_prefers_faculty_subject(self):
        # whole-marathon title matches a keyword (Algebra), but a per-faculty split row
        # for Arjun should use HIS default (Geometry) instead
        subj, _ = F.resolve_subject("Full Day Marathon: Algebra + Geometry",
                                    "Arjun Rao Sir", self.cfg, False, faculty_first=True)
        self.assertEqual(subj, "Geometry")
        # without faculty_first, the title keyword wins
        subj2, _ = F.resolve_subject("Full Day Marathon: Algebra + Geometry",
                                     "Arjun Rao Sir", self.cfg, False, faculty_first=False)
        self.assertEqual(subj2, "Algebra")


class TestSplit(unittest.TestCase):
    def test_split_sums_exactly(self):
        for total, n in [(100, 3), (480, 4), (7, 3), (60, 1)]:
            shares = split_minutes(total, n)
            self.assertEqual(sum(shares), total)
            self.assertEqual(len(shares), n)
            self.assertLessEqual(max(shares) - min(shares), 1)


if __name__ == "__main__":
    unittest.main()
