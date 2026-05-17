# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single source of truth for the in-app Release Notes + Changelog.

Both surfaces — the canonical Markdown files at the repo root
(``RELEASE_NOTES.md`` / ``CHANGELOG.md``) and the in-app About modal
(``templates/base.html``) — read from the same parsed structure produced
here. Editing the Markdown is the only step needed to keep the in-app
view in sync.

The Markdown files are baked into the Docker image (see Dockerfile).
The parser caches by mtime so dev edits show up without a restart.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import markdown as md_lib

# Files live at the repo root, one level above the ``app/`` package.
_ROOT = Path(__file__).resolve().parent.parent
_RELEASE_NOTES_PATH = _ROOT / "RELEASE_NOTES.md"
_CHANGELOG_PATH = _ROOT / "CHANGELOG.md"

_MD_EXT = ["extra", "nl2br", "sane_lists"]


@dataclass
class _Entry:
    version: str
    date: str         # ISO YYYY-MM-DD as written in the source, "" if unparseable
    date_label: str   # Friendly month-day-year for UI ("May 17, 2026"); "" when date is missing or unparseable
    title: str        # The short headline for release notes; "" for changelog (the body carries its own subheads)
    is_latest: bool   # True when the source header carried "(latest)"
    body_html: str    # Markdown body rendered to HTML


def _date_label(raw: str) -> str:
    """Friendly display form of a date string.

    ISO dates (``2026-05-17``) become ``May 17, 2026``. Any other
    freeform string (``May 2026``, ``April 2026``) passes through
    unchanged so legacy entries keep their original wording.
    """
    if not raw:
        return ""
    if _ISO_DATE.match(raw):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").strftime("%b %-d, %Y")
        except ValueError:
            pass
    return raw


# (mtime_ns, parsed entries) — recomputed when the file changes on disk.
_release_cache: tuple[int, List[_Entry]] | None = None
_changelog_cache: tuple[int, List[_Entry]] | None = None


def _split_sections(text: str) -> List[str]:
    """Return every ``## ...`` section's full text (header line + body).

    The top-of-file H1 + intro paragraphs are discarded — only level-2
    sections survive. Each returned string starts with ``## `` and runs
    up to the line before the next ``## `` (or EOF).
    """
    parts: List[str] = []
    current: List[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            if in_section and current:
                parts.append("\n".join(current))
            current = [line]
            in_section = True
        elif in_section:
            current.append(line)
    if in_section and current:
        parts.append("\n".join(current))
    return parts


# Release-notes header: ``## 2.0.4 — 2026-05-17 (latest) — Title``
# Permissive form so older entries with freeform dates ("May 2026") or
# version ranges ("1.8.6 – 1.8.8") still parse. Splits on em-dash (with
# en-dash + ASCII hyphen as fallbacks) into [version, date, title].
# ``(latest)`` is detected wherever it lands and stripped from the
# date label.
_DASH = r"[—–\-]"
# Version capture handles both single versions ("2.0.4", "1.0") and
# ranges ("1.8.6 – 1.8.8", "1.3.0 – 1.3.6") — without this an en-dash
# inside the version range would terminate the match prematurely and
# the second half of the range would be parsed as the date.
_VERSION = r"\d+(?:\.\d+)*(?:\s*[–\-]\s*\d+(?:\.\d+)*)?"
_RN_HEADER = re.compile(
    rf"^##\s+(?P<version>{_VERSION})\s+{_DASH}+\s+(?P<rest>.+)$"
)

# Changelog header: ``## [2.0.4] — 2026-05-17``
# Date is optional so a stub like ``## [Unreleased]`` (filtered out
# downstream) still matches without erroring.
_CL_HEADER = re.compile(
    rf"^##\s+\[(?P<version>[^\]]+)\](?:\s*{_DASH}+\s*(?P<date>.+))?\s*$"
)

_LATEST_FLAG = re.compile(r"\s*\(latest\)\s*", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _render(body: str) -> str:
    body = body.strip("\n")
    if not body:
        return ""
    return md_lib.markdown(body, extensions=_MD_EXT)


def _parse_release_notes(text: str) -> List[_Entry]:
    out: List[_Entry] = []
    for section in _split_sections(text):
        header, _, body = section.partition("\n")
        m = _RN_HEADER.match(header)
        if not m:
            continue
        version = m.group("version").strip()
        rest = m.group("rest")
        # Strip `(latest)` from anywhere in the rest of the header so
        # the date / title stay clean. Flag is True when removed.
        is_latest = bool(_LATEST_FLAG.search(rest))
        rest = _LATEST_FLAG.sub(" ", rest).strip()
        # Remaining `rest` splits on the next em-dash into [date, title].
        # If no dash, the whole thing is the date with no title.
        parts = re.split(rf"\s+{_DASH}+\s+", rest, maxsplit=1)
        date_raw = parts[0].strip()
        title = parts[1].strip() if len(parts) == 2 else ""
        out.append(_Entry(
            version=version,
            date=date_raw,
            date_label=_date_label(date_raw),
            title=title.strip(),
            is_latest=is_latest,
            body_html=_render(body),
        ))
    return out


def _parse_changelog(text: str) -> List[_Entry]:
    out: List[_Entry] = []
    for section in _split_sections(text):
        header, _, body = section.partition("\n")
        m = _CL_HEADER.match(header)
        if not m:
            continue
        version = m.group("version").strip()
        # Skip the ``[Unreleased]`` placeholder — it has no date and
        # nothing to show users.
        if version.lower() == "unreleased":
            continue
        date_raw = (m.group("date") or "").strip()
        out.append(_Entry(
            version=version,
            date=date_raw,
            date_label=_date_label(date_raw),
            title="",
            is_latest=False,
            body_html=_render(body),
        ))
    return out


def _load(path: Path, parser, cache_slot: str) -> List[_Entry]:
    global _release_cache, _changelog_cache
    cached = _release_cache if cache_slot == "release" else _changelog_cache
    try:
        mtime = path.stat().st_mtime_ns
    except FileNotFoundError:
        return []
    if cached and cached[0] == mtime:
        return cached[1]
    text = path.read_text(encoding="utf-8")
    entries = parser(text)
    if cache_slot == "release":
        _release_cache = (mtime, entries)
    else:
        _changelog_cache = (mtime, entries)
    return entries


def load_release_notes() -> List[_Entry]:
    """Parsed entries from ``RELEASE_NOTES.md``, newest first."""
    return _load(_RELEASE_NOTES_PATH, _parse_release_notes, "release")


def load_changelog() -> List[_Entry]:
    """Parsed entries from ``CHANGELOG.md``, newest first."""
    return _load(_CHANGELOG_PATH, _parse_changelog, "changelog")
