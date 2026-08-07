"""Faculty-name detection against the vertical's roster + aliases.

Matches a title against the FULL roster (longest names first, word-boundaried),
masks what matched, then tries aliases on the remainder. Masking matters because
a short alias built from just the first name plus an honorific (e.g. "Firstname
Sir") would otherwise also match as a false positive inside a longer canonical
name that happens to contain the same first name (e.g. "Firstname Lastname
Sir") -- longest-first plus masking prevents that.

Handles the Mam / Ma'am honorific spelling variants automatically, so a roster
name recorded with the full "Ma'am" spelling still matches a title that uses
the shortened "Mam" spelling.
"""
from __future__ import annotations

import re

MAM_ALT = r"(?:Mam|Ma['’]am)"


def name_to_pattern(name: str) -> str:
    parts = name.split()
    out = []
    for p in parts:
        if p in ("Mam", "Ma'am") or p.replace("’", "'") == "Ma'am":
            out.append(MAM_ALT)
        else:
            out.append(re.escape(p))
    return r"\b" + r"\s+".join(out) + r"\b"


def build_detector(roster: list[str], aliases: dict[str, list[str]]):
    """Returns detect(text) -> sorted list of unique canonical names found."""
    canonical_sorted = sorted(roster, key=len, reverse=True)
    canonical_patterns = [(n, re.compile(name_to_pattern(n), re.IGNORECASE)) for n in canonical_sorted]

    alias_patterns: list[tuple[str, re.Pattern]] = []
    for canon, alist in aliases.items():
        for a in alist:
            alias_patterns.append((canon, re.compile(name_to_pattern(a), re.IGNORECASE)))
    alias_patterns.sort(key=lambda t: len(t[1].pattern), reverse=True)

    def detect(text: str) -> list[str]:
        masked = text or ""
        found: set[str] = set()
        for canon, pat in canonical_patterns:
            spans = []
            for m in pat.finditer(masked):
                spans.append((m.start(), m.end()))
                found.add(canon)
            if spans:
                buf = list(masked)
                for s, e in spans:
                    for i in range(s, e):
                        buf[i] = "\x00"
                masked = "".join(buf)
        for canon, pat in alias_patterns:
            if pat.search(masked):
                found.add(canon)
                masked = pat.sub(lambda m: "\x00" * (m.end() - m.start()), masked)
        return sorted(found)

    return detect
