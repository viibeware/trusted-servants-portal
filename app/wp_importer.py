# SPDX-License-Identifier: AGPL-3.0-or-later
"""WordPress post importer — REST or CSV → Stories / Announcements / Events / Blog.

Wizard flow (driven by routes in app/routes.py and templates in
templates/wp_import_*):

  1. Source pick → admin chooses REST (URL + user + app password) or CSV.
  2. Connect / parse → posts + categories + tags normalized into one
     shape and written to a stash JSON keyed by an opaque token. The
     stash lives in ``$TSP_DATA_DIR/wp_import/<token>.json`` so it
     survives gunicorn worker churn within a single boot.
  3. Map → admin assigns each post (or all posts in a category) to one
     of stories / announcements / events / blog / skip. The mapping is
     saved back into the stash.
  4. Dry run → ``compile_plan`` walks the saved mapping and resolves
     per-target slug uniqueness, so the preview names exactly which
     rows would be created vs. skipped vs. blocked by a slug clash. It
     also reports how many BlogCategory / BlogTag rows would be auto-
     created (matching by slug + name first; net-new rows added when
     no match).
  5. Commit → ``apply_plan(dry_run=False)`` creates the rows + downloads
     featured images via ``download_image_to_uploads`` (with sha256
     dedupe through MediaItem) + materializes BlogCategory / BlogTag
     rows for each WP category / tag a blog-targeted post carries.
     Stash is deleted on success.

Post body is stored as the WP-rendered HTML — the rendered Stories /
Announcements / Events / Blog templates already pass body through the
``markdown`` Jinja filter, which routes HTML through bleach with the
SAFE_RICH_TAGS allowlist. So WP HTML round-trips through to the public
site without a separate HTML→Markdown pass.
"""
import csv
import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime
from urllib.parse import urlparse

import requests
from flask import current_app
from werkzeug.utils import secure_filename


DEFAULT_TIMEOUT = 25
USER_AGENT = "tspro-wp-importer/1.0"
# Connect fetches up to this many posts (newest first) into one stash —
# comfortably importable within the 120s request timeout. The COMMIT is
# what's chunked across requests (image downloads dominate the cost);
# see COMMIT_CHUNK_SIZE.
MAX_FETCH_POSTS = 3000
# Posts committed per request when importing. Bounds each commit so a
# large site's image downloads can't blow the request timeout — the
# wizard auto-advances through the chunks behind a progress bar.
COMMIT_CHUNK_SIZE = 200
TARGETS = ("stories", "announcements", "events", "blog", "skip")
TARGET_LABELS = {
    "stories":       "Story",
    "announcements": "Announcement",
    "events":        "Event",
    "blog":          "Blog",
    "skip":          "Skip",
}


# ---------------------------------------------------------------------------
# ACF custom-field mapping.
#
# Each Post column we can auto-fill from ACF lists the field-name aliases
# we look for. Resolution is case-insensitive and tries each alias in
# order; the first non-empty leaf wins. Dotted aliases (``event.start``)
# match against the flattened-with-dots ACF dict produced by
# ``_flatten_acf``. This is intentionally generous because ACF field
# names are site-defined — a fellowship using "venue_name" or "place"
# or "location" all want the same target column.
# ---------------------------------------------------------------------------
ACF_FIELD_ALIASES = {
    # Event timing. Full-datetime aliases live here; the resolver also
    # composes a real datetime from separate date + time aliases below
    # when no full-datetime field is found, so a site that stores
    # ``event_date`` (YYYYMMDD) alongside ``event_start_time`` ("6:00 pm")
    # still lands a proper start datetime in the row.
    "event_starts_at": [
        "event_starts_at", "event_start_at", "event_start_datetime",
        "event_start", "event_starts",
        "event_datetime", "event_date_time",
        "start_datetime", "start_date_time", "starts_at",
        "date_start", "datetime_start",
    ],
    "event_ends_at": [
        "event_ends_at", "event_end_at", "event_end_datetime",
        "event_end", "event_ends",
        "end_datetime", "end_date_time", "ends_at",
        "date_end", "datetime_end",
    ],
    # Event location.
    "is_online": [
        "is_online", "online", "online_event", "online_only",
        "virtual", "is_virtual", "remote", "is_remote", "online_meeting",
    ],
    "location_name": [
        "event_location_name", "venue_name", "venue",
        "place_name", "place",
        "location_name", "location_title", "location",
        "event_location", "event_venue",
    ],
    "location_address": [
        "event_location_address", "event_address",
        "venue_address", "location_address", "address",
        "street_address", "full_address",
        "address_line_1", "address1",
    ],
    "google_maps_url": [
        "google_maps_url", "google_maps_link",
        "map_url", "map_link", "maps_url", "maps_link",
        "google_maps", "google_map_link", "directions_url",
    ],
    # Event website.
    "website_url": [
        "event_website_url", "event_website_link", "event_website",
        "website_url", "website_link", "website",
        "event_url", "event_link", "external_url",
        "link_url", "register_url", "registration_url", "rsvp_url",
        "more_info_url", "info_url",
    ],
    "website_label": [
        "event_website_label", "event_website_text",
        "website_label", "website_text",
        "register_label", "registration_label",
        "link_text", "link_label", "button_label", "cta_label",
    ],
    # Event Zoom.
    "zoom_meeting_id": [
        "zoom_meeting_id", "zoom_id", "meeting_id", "zoom_meeting",
    ],
    "zoom_passcode": [
        "zoom_meeting_passcode", "zoom_meeting_password",
        "zoom_passcode", "zoom_password",
        "meeting_passcode", "meeting_password",
        "passcode", "password",
    ],
    "zoom_url": [
        "zoom_url", "zoom_link", "zoom_join_url",
        "join_url", "join_link", "video_link", "video_url",
        "conference_url", "conference_link",
    ],
    # Contact (used by both announcements + events).
    "contact_name": [
        "event_contact_name", "announcement_contact_name",
        "contact_name", "contact_person", "contact",
        "host_name", "organizer", "organiser",
    ],
    "contact_phone": [
        "event_contact_phone", "event_contact_number",
        "announcement_contact_phone",
        "contact_phone", "contact_number", "contact_phone_number",
        "phone", "phone_number", "telephone",
    ],
    "contact_email": [
        "event_contact_email", "announcement_contact_email",
        "contact_email", "contact_email_address",
        "email", "email_address",
    ],
    # Summary override — ACF sites often duplicate the WP excerpt into a
    # dedicated rich-text field. When present, this beats the excerpt.
    "summary": [
        "announcement_summary", "event_summary",
        "summary", "excerpt", "short_description", "tagline",
    ],
}

# Aliases used when composing a full datetime from separate date + time
# fields. Tried in order; the first non-empty match wins for each part.
# The resolver only uses these when no full-datetime alias above
# produced a parseable value, so sites that store one combined field
# still take precedence over the date/time split.
ACF_DATE_ALIASES = {
    "start": [
        "event_start_date", "event_date", "start_date", "date_start",
        "date", "event_day", "day", "from_date",
    ],
    "end": [
        "event_end_date", "end_date", "date_end",
        "event_date", "date",  # same-day events
        "until_date", "to_date",
    ],
}
ACF_TIME_ALIASES = {
    "start": [
        "event_start_time", "event_starts_time", "event_start_at",
        "start_time", "starts_time", "time_start",
        "event_time", "from_time", "starts", "start",
    ],
    "end": [
        "event_end_time", "event_ends_time", "event_end_at",
        "end_time", "ends_time", "time_end",
        "until_time", "to_time", "ends", "end",
    ],
}

# Flat set of every alias the mapper recognises — used by the CSV parser
# to decide which columns to treat as ACF input even when they aren't
# prefixed with ``acf_``. Stored lower-case so lookups can compare
# against ``col.strip().lower()``.
_ACF_ALIAS_SET = {alias.lower() for aliases in ACF_FIELD_ALIASES.values()
                  for alias in aliases}


# ---------------------------------------------------------------------------
# Destination-field registry — the single extension point for the
# user-defined custom-field mapping (and for future post types).
#
# For each target post type, list the "extra" destination fields a
# discovered WordPress custom field can be mapped onto. Built-in WP
# fields (title, body, featured image, author byline, publish date) are
# auto-mapped elsewhere and are intentionally NOT listed here — only the
# extended, type-specific fields. ``summary`` is the one near-built-in we
# expose so a dedicated ACF excerpt field can override the WP excerpt.
#
#   key      → the destination column on the target model.
#   label    → human label shown in the mapping UI.
#   type     → drives commit-time coercion: text | url | datetime | date | bool.
#   aliases  → seed the auto-suggested default mapping; the admin can
#              override every one. (Reused from ACF_FIELD_ALIASES where a
#              match exists so the two stay in sync.)
#
# Adding a new post type later is just a new entry here plus a branch in
# apply_plan that constructs the row — discovery, suggestion, the mapping
# UI, and value coercion all flow from this table automatically.
# ---------------------------------------------------------------------------
_POST_TARGET_FIELDS = [
    {"key": "summary",          "label": "Summary / excerpt",  "type": "text",     "aliases": ACF_FIELD_ALIASES["summary"]},
    {"key": "event_starts_at",  "label": "Start date & time",  "type": "datetime", "aliases": ACF_FIELD_ALIASES["event_starts_at"] + ACF_DATE_ALIASES["start"]},
    {"key": "event_ends_at",    "label": "End date & time",     "type": "datetime", "aliases": ACF_FIELD_ALIASES["event_ends_at"] + ACF_DATE_ALIASES["end"]},
    {"key": "is_online",        "label": "Online event?",       "type": "bool",     "aliases": ACF_FIELD_ALIASES["is_online"]},
    {"key": "location_name",    "label": "Location name",       "type": "text",     "aliases": ACF_FIELD_ALIASES["location_name"]},
    {"key": "location_address", "label": "Location address",    "type": "text",     "aliases": ACF_FIELD_ALIASES["location_address"]},
    {"key": "google_maps_url",  "label": "Google Maps URL",     "type": "url",      "aliases": ACF_FIELD_ALIASES["google_maps_url"]},
    {"key": "website_url",      "label": "Website / link URL",  "type": "url",      "aliases": ACF_FIELD_ALIASES["website_url"]},
    {"key": "website_label",    "label": "Website link label",  "type": "text",     "aliases": ACF_FIELD_ALIASES["website_label"]},
    {"key": "zoom_meeting_id",  "label": "Zoom meeting ID",      "type": "text",     "aliases": ACF_FIELD_ALIASES["zoom_meeting_id"]},
    {"key": "zoom_passcode",    "label": "Zoom passcode",        "type": "text",     "aliases": ACF_FIELD_ALIASES["zoom_passcode"]},
    {"key": "zoom_url",         "label": "Zoom join URL",        "type": "url",      "aliases": ACF_FIELD_ALIASES["zoom_url"]},
    {"key": "contact_name",     "label": "Contact name",         "type": "text",     "aliases": ACF_FIELD_ALIASES["contact_name"]},
    {"key": "contact_phone",    "label": "Contact phone",        "type": "text",     "aliases": ACF_FIELD_ALIASES["contact_phone"]},
    {"key": "contact_email",    "label": "Contact email",        "type": "text",     "aliases": ACF_FIELD_ALIASES["contact_email"]},
]
_STORY_AUTHOR_ALIASES = ["author", "author_name", "byline", "writer", "by", "submitted_by"]
_AUTHOR_BIO_ALIASES = ["author_bio", "bio", "about_author", "author_about", "about_the_author"]
TARGET_FIELDS = {
    "announcements": _POST_TARGET_FIELDS,
    "events":        _POST_TARGET_FIELDS,
    "stories": [
        {"key": "summary",       "label": "Summary",              "type": "text", "aliases": ACF_FIELD_ALIASES["summary"]},
        {"key": "author_name",   "label": "Author byline",        "type": "text", "aliases": _STORY_AUTHOR_ALIASES},
        {"key": "author_bio",    "label": "Author bio",           "type": "text", "aliases": _AUTHOR_BIO_ALIASES},
        {"key": "story_date",    "label": "Story date",           "type": "date", "aliases": ["story_date", "date", "story_day"]},
        {"key": "sobriety_date", "label": "Clean / sobriety date", "type": "date", "aliases": ["sobriety_date", "clean_date", "clean_time", "sober_date", "recovery_date", "anniversary", "clean_anniversary"]},
    ],
    "blog": [
        {"key": "summary",     "label": "Summary",       "type": "text", "aliases": ACF_FIELD_ALIASES["summary"]},
        {"key": "author_name", "label": "Author byline", "type": "text", "aliases": _STORY_AUTHOR_ALIASES},
        {"key": "author_bio",  "label": "Author bio",    "type": "text", "aliases": _AUTHOR_BIO_ALIASES},
    ],
}

# Length caps applied to mapped string/url values at commit, matching the
# destination columns' DB widths.
_FIELD_CAPS = {
    "summary": 500, "location_name": 255, "location_address": 8000,
    "google_maps_url": 500, "website_url": 500, "website_label": 120,
    "zoom_meeting_id": 64, "zoom_passcode": 128, "zoom_url": 500,
    "contact_name": 120, "contact_phone": 64, "contact_email": 255,
    "author_name": 120, "author_bio": 8000,
}

# CSV column headers that are NEVER ACF — they're built-in WP fields
# the parser already maps to other slots. Stops a Title column from
# being treated as an ACF "name"-style field.
_CSV_BUILTIN_COLS = {"title", "post_title", "post title", "categories",
                     "post_category", "category", "tags", "post_tag",
                     "post tags", "date", "post_date", "published",
                     "publish date", "content", "post_content", "body",
                     "excerpt", "post_excerpt", "summary", "author",
                     "post_author", "slug", "post_name", "url slug",
                     "featured image", "image url", "attachment url",
                     "status", "post_status", "permalink", "url", "link"}

# Truthy strings ACF / form-style sources use for boolean toggles. Used
# to coerce is_online and the like into a real bool when the source
# emits checkbox-style values rather than Python bools.
_TRUTHY = {"1", "true", "yes", "y", "on", "online", "virtual"}
_FALSEY = {"0", "false", "no", "n", "off", "in-person", "in person", "physical"}


# ACF / CMS field-name prefixes the resolver strips when building its
# lookup index. Sites that put every field under ``event_*``,
# ``announcement_*``, etc. still match plain aliases like
# ``contact_name`` (which would otherwise miss ``event_contact_name``).
_ACF_PREFIX_STRIPS = (
    "event_", "evt_", "events_",
    "announcement_", "announcements_", "ann_",
    "story_", "stories_", "post_", "wp_",
    "field_",
)


def _build_acf_index(acf):
    """Build the lookup tables ``_resolve_acf_value`` uses. Stamped
    under multiple keys so a single ACF field like ``event_contact_name``
    resolves against any of: the literal key, the prefix-stripped key
    (``contact_name``), and the dotted-leaf segment. The same value is
    also indexed with hyphens / spaces normalized to underscores so
    inconsistent author conventions still hit."""
    by_key = {}
    by_leaf = {}
    if not acf:
        return by_key, by_leaf
    for k, v in acf.items():
        if v in (None, ""):
            continue
        lk = k.strip().lower()
        variants = {lk,
                    lk.replace(" ", "_"),
                    lk.replace("-", "_")}
        # Prefix-stripped variants — generalises the common
        # "every ACF field is event_*" convention without forcing
        # every alias list to enumerate the prefixed form.
        stripped = set()
        for v_ in variants:
            for pfx in _ACF_PREFIX_STRIPS:
                if v_.startswith(pfx) and len(v_) > len(pfx):
                    stripped.add(v_[len(pfx):])
        variants |= stripped
        for kk in variants:
            by_key.setdefault(kk, v)
            leaf = kk.split(".")[-1]
            by_leaf.setdefault(leaf, v)
    return by_key, by_leaf


def _resolve_acf_value(acf, target_field):
    """Return the first non-empty alias hit for ``target_field``, or
    ``None``. Walks ``ACF_FIELD_ALIASES[target_field]`` in declared
    order; resolves against the indexed dict from ``_build_acf_index``
    which carries prefix-stripped variants for sites that namespace
    every field under ``event_*`` / ``announcement_*``."""
    if not acf:
        return None
    by_key, by_leaf = _build_acf_index(acf)
    for alias in ACF_FIELD_ALIASES.get(target_field, ()):
        la = alias.strip().lower()
        if la in by_key:
            return by_key[la]
        if "." not in la and la in by_leaf:
            return by_leaf[la]
    return None


def _resolve_one_alias(by_key, by_leaf, alias):
    """Lookup a single alias against the pre-built indexes. Mirrors
    the resolver's match order — exact key first, then leaf segment."""
    la = alias.strip().lower()
    if la in by_key:
        return by_key[la]
    if "." not in la and la in by_leaf:
        return by_leaf[la]
    return None


def _resolve_event_datetime(acf, side):
    """Resolve an event start / end datetime from ACF, composing a
    real ``datetime`` from whatever the site provides:

      1. Full-datetime alias (single field that already holds both
         date and time) — wins outright when present.
      2. Date alias + time alias composed via ``datetime.combine``.
      3. Date alias alone — datetime defaults to midnight.

    ``side`` is ``'start'`` or ``'end'``. Returns ``None`` when nothing
    parses so the caller falls back to its own default (e.g. the post's
    publish date).
    """
    if not acf:
        return None
    by_key, by_leaf = _build_acf_index(acf)

    # Step 1 — try the dedicated full-datetime aliases first.
    target = "event_starts_at" if side == "start" else "event_ends_at"
    for alias in ACF_FIELD_ALIASES.get(target, ()):
        v = _resolve_one_alias(by_key, by_leaf, alias)
        dt = _parse_acf_datetime(v)
        if dt is not None:
            return dt

    # Step 2 — compose from a date alias + (optionally) a time alias.
    date_part = None
    for alias in ACF_DATE_ALIASES.get(side, ()):
        v = _resolve_one_alias(by_key, by_leaf, alias)
        d = _parse_acf_date(v)
        if d is not None:
            date_part = d
            break

    time_part = None
    for alias in ACF_TIME_ALIASES.get(side, ()):
        v = _resolve_one_alias(by_key, by_leaf, alias)
        t = _parse_acf_time(v)
        if t is not None:
            time_part = t
            break

    if date_part and time_part:
        return datetime.combine(date_part, time_part)
    if date_part:
        return datetime.combine(date_part, datetime.min.time())
    return None


def _parse_acf_date(value):
    """Coerce an ACF date field value into a ``date``. ACF date pickers
    most commonly emit ``YYYY-MM-DD``, ``YYYYMMDD`` (an older ACF save
    format), or whatever ``display_format`` was configured. Returns
    ``None`` when nothing parses."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value)).date()
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit() and len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
                "%B %d, %Y", "%b %d, %Y", "%A %B %d, %Y", "%A %B %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Last try — let the datetime parser have a shot (handles ISO with
    # a time component too — we drop the time when composing later).
    dt = _parse_acf_datetime(s)
    return dt.date() if dt else None


def _parse_acf_time(value):
    """Coerce an ACF time field value into a ``time``. ACF time pickers
    emit ``HH:MM:SS`` or ``HH:MM`` by default; many sites also use a
    12-hour format like "6:00 pm" / "6 PM" in the display_format. We
    try a generous suite so the field's display_format doesn't matter."""
    if value in (None, ""):
        return None
    s = str(value).strip().lower().replace(".", "")
    if not s:
        return None
    # Common shorthand without a colon: "6pm", "11am".
    m = re.fullmatch(r"\s*(\d{1,2})\s*(am|pm)\s*", s)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(2) == "pm":
            hour += 12
        from datetime import time as _time
        return _time(hour, 0)
    # Standard ACF time strings.
    for fmt in ("%H:%M:%S", "%H:%M",
                "%I:%M:%S %p", "%I:%M %p", "%I %p",
                "%I:%M:%S%p", "%I:%M%p", "%I%p"):
        try:
            t = datetime.strptime(s, fmt).time()
            return t
        except ValueError:
            continue
    return None


def _parse_acf_datetime(value):
    """Coerce an ACF date / datetime value into a ``datetime``. ACF
    date pickers emit one of: ``YYYY-MM-DD HH:MM:SS`` (DB-save format,
    most common), ``YYYY-MM-DD`` (date-only), Unix timestamp (rare),
    or whatever the field's ``return_format`` is set to. We try a
    suite of common formats and return ``None`` on no match so the
    caller can leave the column NULL."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value))
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    # Pure-digit values are likely Unix timestamps.
    if s.isdigit() and 8 <= len(s) <= 10:
        try:
            return datetime.fromtimestamp(int(s))
        except (OSError, OverflowError, ValueError):
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y/%m/%d %H:%M:%S",
                "%Y%m%d%H%M%S", "%Y%m%d",
                "%Y-%m-%d", "%Y/%m/%d",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                "%m/%d/%Y", "%d/%m/%Y",
                "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s[:len(fmt) + 6], fmt)
        except (ValueError, TypeError):
            continue
    return None


def _acf_preview_value(v):
    """Short, human-readable rendering of an ACF-resolved value for
    surfacing on the dry-run preview. Datetimes get a friendly format;
    long strings truncate. Returns a plain string the template can
    drop in without escaping concerns."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, datetime):
        try:
            return v.strftime("%b %-d, %Y %-I:%M %p").replace(" 12:00 AM", "")
        except (ValueError, AttributeError):
            return v.isoformat()
    s = str(v).strip()
    if len(s) > 80:
        s = s[:77] + "…"
    return s


def _coerce_bool(v):
    """Best-effort boolean coercion for ACF / CSV truthy strings. Returns
    ``None`` for values that aren't unambiguously true or false so the
    caller can decide whether to leave the column at its default."""
    if isinstance(v, bool):
        return v
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSEY:
        return False
    return None


def _extract_acf_post_fields(acf, target):
    """Resolve every ACF alias for the Post columns relevant to the
    given target (``events`` or ``announcements``) and return a dict
    suitable for splatting into the ``Post(**…)`` constructor.

    Returns ``({column: value, …}, applied)`` where ``applied`` is a
    list of column names the UI can surface so admins see exactly what
    landed where. Empty list = nothing landed.

    The summary column rides along when the source ACF has a dedicated
    summary / excerpt field — caller is responsible for honouring that
    override before the WP excerpt fallback.
    """
    if not acf or target not in ("events", "announcements"):
        return {}, []

    # Columns both targets accept. Posts on this site share a single
    # ``Post`` model — the ``is_announcement`` / ``is_event`` flags are
    # independent and the public archive mixes both kinds in the same
    # year sections, so an admin who imports a post as an
    # ``announcement`` still wants the event-shaped ACF fields
    # (start/end times, location, zoom, contact, …) to land on the
    # row. Same set for both targets.
    cols = ("event_starts_at", "event_ends_at", "is_online",
            "location_name", "location_address", "google_maps_url",
            "website_url", "website_label",
            "zoom_meeting_id", "zoom_passcode", "zoom_url",
            "contact_name", "contact_phone", "contact_email",
            "summary")
    out = {}
    applied = []
    BOOL_COLS = {"is_online"}
    STRING_LIMITS = {
        "location_name": 255, "location_address": 8000,
        "google_maps_url": 500, "website_url": 500, "website_label": 120,
        "zoom_meeting_id": 64, "zoom_passcode": 128, "zoom_url": 500,
        "contact_name": 120, "contact_phone": 64, "contact_email": 255,
        "summary": 500,
    }

    for col in cols:
        # Event datetime columns get the composer treatment — many ACF
        # sites split start_date + start_time across two fields.
        if col in ("event_starts_at", "event_ends_at"):
            dt = _resolve_event_datetime(
                acf, "start" if col == "event_starts_at" else "end")
            if dt is None:
                continue
            out[col] = dt
            applied.append(col)
            continue

        raw = _resolve_acf_value(acf, col)
        if raw is None or raw == "":
            continue
        if col in BOOL_COLS:
            b = _coerce_bool(raw)
            if b is None:
                continue
            out[col] = b
            applied.append(col)
            continue
        # String columns — coerce to str, strip, length-cap.
        s = str(raw).strip()
        if not s:
            continue
        limit = STRING_LIMITS.get(col)
        if limit and len(s) > limit:
            s = s[:limit]
        out[col] = s
        applied.append(col)
    return out, applied


def _humanize_field(key):
    """Pretty label for a discovered field key — leaf segment, spaced,
    title-cased. ``event_details.start_date`` → ``Start Date``."""
    leaf = (key or "").split(".")[-1]
    return leaf.replace("_", " ").replace("-", " ").strip().title() or key


def discover_fields(posts):
    """Aggregate every scalar custom field present across ``posts`` into a
    sorted list of ``{key, label, sample, count}`` for the mapping UI.

    Group / repeater parents (dict / list values) are skipped — only
    directly-mappable scalar leaves surface. ``count`` is how many posts
    carry the field; ``sample`` is a short preview of the first value
    seen, so the admin can recognise the field by its data."""
    agg = {}
    for p in posts or []:
        acf = p.get("acf") or {}
        if not isinstance(acf, dict):
            continue
        for k, v in acf.items():
            if isinstance(v, (dict, list)):
                continue
            if v in (None, "", False):
                continue
            entry = agg.get(k)
            if entry is None:
                entry = {"key": k, "label": _humanize_field(k),
                         "sample": _acf_preview_value(v), "count": 0}
                agg[k] = entry
            entry["count"] += 1
    return sorted(agg.values(), key=lambda e: e["key"].lower())


def _key_index(keys):
    """Index discovered field keys for alias matching, mirroring
    ``_build_acf_index``'s normalisation (lowercase, space/hyphen →
    underscore, common prefix strips, dotted-leaf). Maps each normalised
    variant → the ORIGINAL discovered key so a matched alias resolves to
    a real, selectable field key."""
    by_key, by_leaf = {}, {}
    for k in keys:
        lk = (k or "").strip().lower()
        if not lk:
            continue
        variants = {lk, lk.replace(" ", "_"), lk.replace("-", "_")}
        stripped = set()
        for v_ in variants:
            for pfx in _ACF_PREFIX_STRIPS:
                if v_.startswith(pfx) and len(v_) > len(pfx):
                    stripped.add(v_[len(pfx):])
        variants |= stripped
        for kk in variants:
            by_key.setdefault(kk, k)
            by_leaf.setdefault(kk.split(".")[-1], k)
    return by_key, by_leaf


def _match_discovered_key(by_key, by_leaf, alias):
    la = (alias or "").strip().lower()
    if la in by_key:
        return by_key[la]
    if "." not in la and la in by_leaf:
        return by_leaf[la]
    return None


def suggest_mapping(posts, targets):
    """Auto-suggested default mapping for each target in ``targets``:
    ``{target: {dest_field: discovered_key}}``. Walks each registry
    field's aliases and picks the first discovered field that matches —
    the same generous matching the legacy auto-mapper used, now surfaced
    as an editable default."""
    keys = set()
    for p in posts or []:
        acf = p.get("acf") or {}
        if not isinstance(acf, dict):
            continue
        for k, v in acf.items():
            if isinstance(v, (dict, list)) or v in (None, "", False):
                continue
            keys.add(k)
    by_key, by_leaf = _key_index(keys)
    out = {}
    for t in targets:
        m = {}
        for f in TARGET_FIELDS.get(t) or []:
            for alias in f.get("aliases", ()):
                hit = _match_discovered_key(by_key, by_leaf, alias)
                if hit:
                    m[f["key"]] = hit
                    break
        out[t] = m
    return out


def _coerce_field(raw, ftype, dest):
    """Coerce a raw ACF value to the destination column's shape."""
    if raw is None:
        return None
    if ftype == "datetime":
        # Prefer a full datetime; fall back to a date at midnight. A pure
        # 8-digit YYYYMMDD is parsed as a date first — the datetime
        # parser's epoch fallback would otherwise misread it as a Unix
        # timestamp.
        s = str(raw).strip()
        if s.isdigit() and len(s) == 8:
            dd = _parse_acf_date(raw)
            return datetime.combine(dd, datetime.min.time()) if dd else None
        dt = _parse_acf_datetime(raw)
        if dt is not None:
            return dt
        dd = _parse_acf_date(raw)
        return datetime.combine(dd, datetime.min.time()) if dd else None
    if ftype == "date":
        return _parse_acf_date(raw)
    if ftype == "bool":
        return _coerce_bool(raw)
    s = str(raw).strip()
    if not s:
        return None
    cap = _FIELD_CAPS.get(dest)
    if cap and len(s) > cap:
        s = s[:cap]
    return s


def _extract_target_fields(acf, target, field_mapping):
    """Resolve the destination fields for ``target`` from ``acf`` using
    the user's ``field_mapping`` (``{target: {dest: wp_key}}``).

    Returns ``(values, applied)`` where ``values`` is ``{dest: coerced}``
    ready to stamp onto the row and ``applied`` is the list of dest cols
    that received a value (for the preview).

    Backward-compatible fallback: when no user mapping exists for the
    target (old stash, or the field step was skipped), Post targets fall
    back to the legacy alias auto-detection so existing imports keep
    landing event/contact data; story/blog get nothing (they had no
    auto-mapping before)."""
    fields = TARGET_FIELDS.get(target)
    if not fields:
        return {}, []
    acf = acf or {}
    tmap = (field_mapping or {}).get(target)
    if not tmap:
        if target in ("events", "announcements"):
            return _extract_acf_post_fields(acf, target)
        return {}, []
    type_by_dest = {f["key"]: f["type"] for f in fields}
    out, applied = {}, []
    for dest, wp_key in tmap.items():
        if not wp_key or dest not in type_by_dest:
            continue
        raw = acf.get(wp_key)
        if raw is None or raw == "":
            continue
        val = _coerce_field(raw, type_by_dest[dest], dest)
        if val is None or val == "":
            continue
        out[dest] = val
        applied.append(dest)
    return out, applied


def _classify_wp_status(raw):
    """Resolve a WP post-status string into a draft flag.

    WP's standard statuses are publish / future / draft / pending /
    private / trash / auto-draft / inherit. ``draft``/``private``/
    ``pending`` route to our Drafts state since the WP intent there
    is unambiguous.

    Archived state is NOT inferred — admins flip per-post archive
    flags on the dry-run screen instead. The ``wp_status`` raw
    string still rides along on each post dict so the wizard can
    show "WP: trash" / "WP: archived" chips and the admin can
    decide whether to land each one in the Archived bucket.

    Returns just ``is_draft`` (a bool). The is_archived second
    value used to ride this signature; callers should default to
    False and let the dry-run override drive it instead.
    """
    s = (raw or "").strip().lower()
    if not s:
        return False
    return s in ("draft", "private", "pending")


# ---------------------------------------------------------------------------
# Stash — short-lived JSON files keyed by an opaque token. Used to ferry
# parsed posts + admin mapping selections between wizard steps without
# pushing the whole payload through the form on every POST.
# ---------------------------------------------------------------------------

def _stash_dir():
    upload = current_app.config["UPLOAD_FOLDER"].rstrip("/")
    data_dir = os.path.dirname(upload)
    path = os.path.join(data_dir, "wp_import")
    os.makedirs(path, exist_ok=True)
    return path


def stash_save(token, payload):
    p = os.path.join(_stash_dir(), f"{token}.json")
    with open(p, "w") as f:
        json.dump(payload, f)
    return p


def stash_load(token):
    if not _valid_token(token):
        return None
    p = os.path.join(_stash_dir(), f"{token}.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def stash_delete(token):
    if not _valid_token(token):
        return
    p = os.path.join(_stash_dir(), f"{token}.json")
    if os.path.isfile(p):
        try:
            os.unlink(p)
        except OSError:
            pass


def stash_purge_old(max_age_seconds=86400):
    """Drop stash files older than 24h. Called opportunistically on
    every wizard entry so abandoned wizards don't accumulate."""
    d = _stash_dir()
    cutoff = time.time() - max_age_seconds
    try:
        for name in os.listdir(d):
            if not name.endswith(".json"):
                continue
            full = os.path.join(d, name)
            try:
                if os.path.getmtime(full) < cutoff:
                    os.unlink(full)
            except OSError:
                pass
    except OSError:
        pass


def new_token():
    return uuid.uuid4().hex


def _valid_token(token):
    return bool(token) and re.fullmatch(r"[a-f0-9]{16,64}", str(token)) is not None


# ---------------------------------------------------------------------------
# WordPress REST fetcher
# ---------------------------------------------------------------------------

def fetch_wp(site_url, user, app_password, *, max_posts=MAX_FETCH_POSTS):
    """Fetch posts + categories + tags via WP REST API.

    Returns ``(posts, categories, tags, error_msg)`` — on failure
    ``posts`` / ``categories`` / ``tags`` are None and ``error_msg`` is
    a human-readable string.

    Authentication uses HTTP Basic with the admin's WP "Application
    Password" (recommended) or username + password. Anonymous fetches
    work too — pass ``user=None`` and only published posts will be
    returned.
    """
    site_url = (site_url or "").strip().rstrip("/")
    if not site_url:
        return None, None, None, "WordPress site URL is required."
    if not site_url.startswith(("http://", "https://")):
        site_url = "https://" + site_url
    base = site_url + "/wp-json/wp/v2"
    auth = (user, app_password) if (user and app_password) else None

    cats_by_id = {}
    page = 1
    while True:
        try:
            r = requests.get(f"{base}/categories", auth=auth, timeout=DEFAULT_TIMEOUT,
                             params={"per_page": 100, "page": page},
                             headers={"User-Agent": USER_AGENT})
        except requests.RequestException as e:
            return None, None, None, f"Could not reach {base}/categories: {e}"
        if r.status_code == 404:
            return None, None, None, ("WP REST API not reachable at "
                                f"{base} (404). Make sure permalinks are not set to plain.")
        if r.status_code in (401, 403):
            return None, None, None, (f"Authentication failed ({r.status_code}). "
                                "Verify the username and Application Password.")
        if r.status_code != 200:
            break
        chunk = r.json()
        if not chunk:
            break
        for c in chunk:
            cats_by_id[c["id"]] = {
                "name": c.get("name", ""),
                "slug": (c.get("slug") or "").strip(),
                "description": _strip_html(c.get("description") or "").strip(),
            }
        if len(chunk) < 100:
            break
        page += 1

    # Tags (WP REST exposes tag taxonomies separately from categories).
    # Same pagination shape; failure to reach /tags is non-fatal — the
    # site might just have tags disabled. We zero-fill the dict and
    # carry on so the wizard can still run on category-only sites.
    tags_by_id = {}
    page = 1
    while True:
        try:
            r = requests.get(f"{base}/tags", auth=auth, timeout=DEFAULT_TIMEOUT,
                             params={"per_page": 100, "page": page},
                             headers={"User-Agent": USER_AGENT})
        except requests.RequestException:
            break
        if r.status_code == 400 and page > 1:
            break
        if r.status_code != 200:
            break
        chunk = r.json()
        if not chunk:
            break
        for t in chunk:
            tags_by_id[t["id"]] = {
                "name": t.get("name", ""),
                "slug": (t.get("slug") or "").strip(),
            }
        if len(chunk) < 100:
            break
        page += 1

    posts = []
    page = 1
    # When authenticated we also request `trash` so WP-trashed posts (the
    # closest built-in equivalent of "archived") surface in the wizard.
    # Custom plugin-registered statuses with names containing "archive"
    # are surfaced opportunistically via _classify_wp_status — if they're
    # publicly queryable they come through under the publish branch; if
    # not, the admin would need to register them as REST-queryable on
    # their WP site. Fallback retries without trash if WP rejects it
    # (older versions or sites that hide trash from REST).
    statuses_with_trash = "publish,draft,private,pending,trash" if auth else "publish"
    statuses_basic = "publish,draft,private,pending" if auth else "publish"
    statuses = statuses_with_trash
    trash_dropped = False
    while len(posts) < max_posts:
        try:
            r = requests.get(f"{base}/posts", auth=auth, timeout=DEFAULT_TIMEOUT,
                             params={"per_page": 50, "page": page,
                                     "_embed": "1", "status": statuses,
                                     "orderby": "date", "order": "desc"},
                             headers={"User-Agent": USER_AGENT})
        except requests.RequestException as e:
            return None, None, None, f"Could not fetch posts: {e}"
        # WP returns 400 ("rest_invalid_param") when a status name isn't
        # accepted (e.g. trash on a hardened install). Drop trash and
        # retry once on the same page so we still get publish/draft.
        if r.status_code == 400 and not trash_dropped and statuses == statuses_with_trash:
            statuses = statuses_basic
            trash_dropped = True
            continue
        if r.status_code == 400 and page > 1:
            # WP returns 400 ("rest_post_invalid_page_number") when paginated
            # past the last page — treat as end-of-list.
            break
        if r.status_code in (401, 403):
            return None, None, None, (f"Authentication failed ({r.status_code}). "
                                "Verify the username and Application Password.")
        if r.status_code != 200:
            break
        chunk = r.json()
        if not chunk:
            break
        for p in chunk:
            posts.append(_normalize_rest_post(p, cats_by_id, tags_by_id))
        if len(chunk) < 50:
            break
        page += 1

    cats = sorted(
        ({"name": v["name"], "slug": v.get("slug", ""), "description": v.get("description", "")}
         for v in cats_by_id.values() if v.get("name")),
        key=lambda c: c["name"].lower(),
    )
    tags = sorted(
        ({"name": v["name"], "slug": v.get("slug", "")}
         for v in tags_by_id.values() if v.get("name")),
        key=lambda t: t["name"].lower(),
    )

    # Legacy ACF-REST fallback. When the modern /wp/v2/posts endpoint
    # returned no ACF data on any post, try the older /acf/v3/posts/<id>
    # namespace once per post (this is the route exposed by the
    # standalone "ACF to REST API" plugin and by ACF Pro on sites that
    # haven't enabled show_in_rest on each field group). We cap the
    # follow-up requests so a hundred-post import doesn't fan out into
    # a hundred extra GETs.
    if posts and not any(p.get("acf") for p in posts):
        fb = _acf_fallback_fetch(site_url, auth, posts)
        if fb:
            for p in posts:
                payload = fb.get(p.get("wp_id"))
                if payload:
                    p["acf"] = _flatten_acf(payload)

    return posts, cats, tags, None


def _acf_fallback_fetch(site_url, auth, posts, *, max_lookups=200):
    """Per-post fetch of /acf/v3/posts/<id> for sites that don't expose
    ACF on the standard /wp/v2/posts route. Returns ``{wp_id: acf_dict}``;
    silently returns ``{}`` when the namespace 404s on the first probe so
    sites without the legacy plugin pay one cheap request total.
    """
    base = site_url.rstrip("/") + "/wp-json/acf/v3/posts"
    out = {}
    for i, p in enumerate(posts[:max_lookups]):
        pid = p.get("wp_id")
        if not pid:
            continue
        try:
            r = requests.get(f"{base}/{pid}", auth=auth,
                             timeout=DEFAULT_TIMEOUT,
                             headers={"User-Agent": USER_AGENT})
        except requests.RequestException:
            return out
        if r.status_code == 404 and i == 0:
            return {}     # legacy namespace not installed
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        acf = (data or {}).get("acf") or {}
        if isinstance(acf, dict) and acf:
            out[pid] = acf
    return out


def _normalize_rest_post(p, cats_by_id, tags_by_id=None):
    """Reduce a WP REST post object to the importer's flat dict shape."""
    cat_ids = p.get("categories") or []
    cat_names = [cats_by_id[cid]["name"] for cid in cat_ids
                 if cats_by_id.get(cid) and cats_by_id[cid].get("name")]

    tag_ids = p.get("tags") or []
    tag_names = []
    if tags_by_id:
        tag_names = [tags_by_id[tid]["name"] for tid in tag_ids
                     if tags_by_id.get(tid) and tags_by_id[tid].get("name")]

    img_url = None
    embedded = p.get("_embedded") or {}
    media = (embedded.get("wp:featuredmedia") or [None])[0]
    if isinstance(media, dict):
        img_url = (media.get("source_url")
                   or ((media.get("media_details") or {}).get("sizes") or {})
                   .get("full", {}).get("source_url"))

    author_name = None
    authors = embedded.get("author") or []
    if authors and isinstance(authors[0], dict):
        author_name = (authors[0].get("name") or "").strip() or None

    title = (p.get("title") or {}).get("rendered") or ""
    excerpt = (p.get("excerpt") or {}).get("rendered") or ""
    body = (p.get("content") or {}).get("rendered") or ""

    is_draft = _classify_wp_status(p.get("status"))

    # Full WP publish timestamp — stored as an ISO string so the
    # commit phase can parse it into a real datetime for
    # ``published_at`` on the resulting row, preserving the original
    # post date through the import. ``date`` (YYYY-MM-DD only) stays
    # for the existing event_starts_at fallback.
    raw_date = p.get("date") or p.get("date_gmt") or ""
    # ACF custom fields — modern ACF (≥5.11) appends an `acf` key to the
    # standard /wp/v2/posts response when each field group has
    # `show_in_rest` enabled. We capture it raw here; the importer's
    # ACF mapper (`_extract_acf_map`) walks the dict, flattens nested
    # group fields, and resolves recognised field names to our Post
    # columns at commit time.
    acf_raw = p.get("acf") or {}
    if not isinstance(acf_raw, dict):
        acf_raw = {}
    return {
        "key": f"wp-{p.get('id')}",
        "wp_id": p.get("id"),
        "title": _strip_html(title),
        "slug": (p.get("slug") or "").strip(),
        "summary": _strip_html(excerpt).strip()[:500],
        "body_html": body,
        "categories": cat_names,
        "tags": tag_names,
        "author_name": author_name,
        "date": raw_date[:10],
        "datetime": raw_date,
        "featured_image_url": img_url,
        "is_draft": is_draft,
        "wp_status": p.get("status") or "",
        "url": p.get("link") or "",
        "acf": _flatten_acf(acf_raw),
    }


def _flatten_acf(d, prefix=""):
    """Recursively flatten an ACF payload into a flat dict whose keys are
    dotted paths (``event_details.start_date``) and whose values are
    scalars / lists / dicts left intact at the leaf. Nested groups are
    the most common ACF nesting; repeater rows are kept as lists of
    dicts under their parent name (the mapper can read either form).

    Empty strings / ``False`` / ``None`` are pruned so the resolver
    never matches an empty leaf when a richer alias exists. Filters out
    WP-internal helper keys (``_<name>``) that ACF emits for sibling
    metadata."""
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        if v is None or v == "" or v is False:
            continue
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            # Nest one level deep for groups; also stamp the parent
            # path so a mapper looking for "event_details" can pick up
            # the whole sub-dict.
            out[path] = v
            for sk, sv in _flatten_acf(v, prefix=path + ".").items():
                out[sk] = sv
        else:
            out[path] = v
    return out


def _strip_html(s):
    if not s:
        return ""
    import html as _html
    txt = re.sub(r"<[^>]+>", "", str(s))
    return _html.unescape(txt).strip()


# ---------------------------------------------------------------------------
# CSV parser — accepts either WP All Export's "Posts" CSV or a generic
# WordPress CSV with `Title`, `Categories`, `Date`, `Content`, etc.
# ---------------------------------------------------------------------------

def parse_csv(file_obj, *, max_posts=2000):
    """Parse a WordPress posts CSV. Returns
    ``(posts, categories, tags, err)`` — categories and tags are
    each lists of ``{name, slug, description?}`` dicts. The CSV is
    expected to carry a ``Categories`` column (pipe / comma / semi-
    colon delimited); tags can ride in a separate ``Tags`` column.
    Sites that store everything in a single ``Tags`` column still
    parse — those values just become categories on the WordPress
    side, then map to whichever target the admin picks."""
    try:
        raw = file_obj.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            file_obj.seek(0)
            raw = file_obj.read().decode("latin-1")
        except UnicodeDecodeError:
            return None, None, None, "Could not decode the CSV — expected UTF-8."
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return None, None, None, "CSV is empty or has no header row."

    has_separate_tags = any(
        (h or "").strip().lower() in ("tags", "post_tag", "post tags")
        for h in (reader.fieldnames or [])
    )
    posts = []
    cats_set = set()
    tags_set = set()
    for i, row in enumerate(reader):
        if i >= max_posts:
            break
        title = _csv_field(row, "Title", "post_title", "Post Title").strip()
        if not title:
            continue
        if has_separate_tags:
            # New shape — Tags column is a real WP tag list.
            cats_raw = _csv_field(row, "Categories", "post_category", "Category")
            tags_raw = _csv_field(row, "Tags", "post_tag", "post tags")
        else:
            # Legacy fallthrough — Tags column was synonymous with
            # Categories. Keep historical behavior so an old CSV
            # doesn't suddenly start dropping rows on the tag side.
            cats_raw = _csv_field(row, "Categories", "post_category", "Category", "Tags")
            tags_raw = ""
        cat_names = [c.strip() for c in re.split(r"[|;,]", cats_raw or "") if c.strip()]
        tag_names = [t.strip() for t in re.split(r"[|;,]", tags_raw or "") if t.strip()]
        for c in cat_names:
            cats_set.add(c)
        for t in tag_names:
            tags_set.add(t)
        date_raw = _csv_field(row, "Date", "post_date", "Published", "Publish Date")
        date_iso = ""
        datetime_iso = ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(date_raw[:19], fmt)
                date_iso = parsed.date().isoformat()
                # Only emit a datetime when the source had real time
                # info; date-only formats round-trip back to date_iso.
                if fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    datetime_iso = parsed.isoformat()
                else:
                    datetime_iso = date_iso
                break
            except (ValueError, IndexError):
                continue
        body = _csv_field(row, "Content", "post_content", "Body")
        excerpt = _csv_field(row, "Excerpt", "post_excerpt", "Summary").strip()
        author = _csv_field(row, "Author", "post_author").strip() or None
        slug = _csv_field(row, "Slug", "post_name", "URL Slug").strip()
        img_url = _csv_field(row, "Featured Image", "Image URL", "Attachment URL").strip() or None
        status = _csv_field(row, "Status", "post_status").strip()
        permalink = _csv_field(row, "Permalink", "URL", "Link").strip()
        is_draft = _classify_wp_status(status)
        # Harvest ACF / custom-field-style columns. We sniff for two
        # patterns: explicit ``acf_<name>`` prefix (WP All Export's
        # default for ACF fields) and any column whose name appears in
        # the mapper's known-alias set (so an admin who exports raw
        # field names without the prefix still lands their data in the
        # right slot). Built-in WP columns are excluded so a column
        # named ``Title`` doesn't get smuggled into the ACF dict.
        acf_csv = {}
        for col, val in row.items():
            if not col:
                continue
            v = (val or "").strip() if isinstance(val, str) else val
            if not v:
                continue
            key = None
            lcol = col.strip().lower()
            if lcol.startswith("acf_"):
                key = col.strip()[4:]
            elif lcol.startswith("acf:"):
                key = col.strip()[4:]
            elif lcol.startswith("meta:"):
                key = col.strip()[5:]
            elif lcol in _ACF_ALIAS_SET and lcol not in _CSV_BUILTIN_COLS:
                key = col.strip()
            if key:
                acf_csv[key] = v
        posts.append({
            "key": f"csv-{i+1}",
            "wp_id": None,
            "title": title,
            "slug": slug,
            "summary": excerpt[:500],
            "body_html": body,
            "categories": cat_names,
            "tags": tag_names,
            "author_name": author,
            "date": date_iso,
            "datetime": datetime_iso,
            "featured_image_url": img_url,
            "is_draft": is_draft,
            "wp_status": status,
            "url": permalink,
            "acf": acf_csv,
        })
    if not posts:
        return None, None, None, ("No rows with a Title column. Make sure the CSV has a "
                                  "header row including Title (or post_title).")
    cats_list = [{"name": n, "slug": "", "description": ""} for n in sorted(cats_set)]
    tags_list = [{"name": n, "slug": ""} for n in sorted(tags_set)]
    return posts, cats_list, tags_list, None


def _csv_field(row, *keys):
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return ""


# ---------------------------------------------------------------------------
# Plan compile + apply
# ---------------------------------------------------------------------------

def compile_plan(posts, mapping):
    """Walk every post and produce an action dict per post.

    Each action is ``{target, post, slug, conflict}`` — ``target`` is one
    of the TARGETS values, ``slug`` is the resolved unique-within-target
    slug, ``conflict`` is None when the slug doesn't clash with any
    existing row (or "slug-exists" when it does).

    Slug conflict resolution: rather than rejecting clashing posts, the
    apply phase auto-suffixes ``-2``, ``-3``, etc. via the same uniqueness
    helpers Stories/Posts already use. ``conflict`` is reported here so
    the dry-run preview can call out the rename to the admin.
    """
    from .models import Story, Post, BlogPost
    actions = []
    by_slug = {
        "stories":       {s.public_slug for s in Story.query.all()},
        "announcements": {p.public_slug for p in Post.query.filter(Post.is_announcement.is_(True)).all()},
        "events":        {p.public_slug for p in Post.query.filter(Post.is_event.is_(True)).all()},
        "blog":          {bp.public_slug for bp in BlogPost.query.all()},
    }
    for p in posts:
        target = (mapping.get(p["key"]) or "skip").strip()
        if target not in TARGETS or target == "skip":
            actions.append({"target": "skip", "post": p, "slug": None, "conflict": None})
            continue
        slug = _slugify((p.get("slug") or "") or (p.get("title") or ""))
        conflict = "slug-exists" if (slug and slug in by_slug.get(target, set())) else None
        actions.append({"target": target, "post": p, "slug": slug, "conflict": conflict})
    return actions


def _slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:200] or None


def _unique_slug(base, used):
    """Auto-suffix a slug with ``-2``, ``-3``, … until it doesn't appear
    in ``used`` (the in-process tracking of already-claimed slugs for the
    current target table). Mutates ``used`` to claim the resolved slug.
    """
    if not base:
        return None
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def apply_plan(actions, *, dry_run=True, image_cb=None, created_by=None,
               category_meta=None, tag_meta=None, archive_keys=None,
               field_mapping=None, count_inline=True):
    """Walk a compiled plan and either render a preview (dry_run=True)
    or commit it (dry_run=False).

    ``category_meta`` and ``tag_meta`` are optional ``{name → {slug,
    description?}}`` dicts harvested from the source (WP REST or CSV).
    They drive how blog-targeted rows wire into ``BlogCategory`` /
    ``BlogTag``: matching by slug first, then case-insensitive name;
    net-new rows are created when neither matches.

    Returns ``{counts, rows, warnings}``:
      counts.{stories,announcements,events,blog,skipped,renamed,
              image_failed,blog_categories_created,blog_tags_created,
              blog_categories_matched,blog_tags_matched}
      rows  — list of {target, id (None on dry-run), title, slug,
                       image_status, was_renamed,
                       categories (blog-only list of names),
                       tags (blog-only list of names)}
      warnings — list of "post X: …" strings the UI surfaces in red.
    """
    from .models import db, Story, Post, BlogPost, BlogCategory, BlogTag

    counts = {"stories": 0, "announcements": 0, "events": 0, "blog": 0,
              "skipped": 0, "renamed": 0, "image_failed": 0,
              "archived": 0, "drafts": 0,
              "inline_images_downloaded": 0, "inline_images_failed": 0,
              "blog_categories_created": 0, "blog_tags_created": 0,
              "blog_categories_matched": 0, "blog_tags_matched": 0,
              "acf_fields_applied": 0, "acf_rows_enriched": 0}
    rows = []
    warnings = []

    used_slugs = {
        "stories":       {s.public_slug for s in Story.query.all()},
        "announcements": {p.public_slug for p in Post.query.filter(Post.is_announcement.is_(True)).all()},
        "events":        {p.public_slug for p in Post.query.filter(Post.is_event.is_(True)).all()},
        "blog":          {bp.public_slug for bp in BlogPost.query.all()},
    }

    # Pre-load existing blog taxonomy rows so the resolver can match by
    # slug or name without an N+1 query per post. Slug index wins; name
    # index is the case-insensitive fallback. Same indexes get mutated
    # when the resolver creates new rows so the next post in the loop
    # picks up the row we just added.
    cat_meta = category_meta or {}
    tag_meta = tag_meta or {}
    if not dry_run:
        cat_by_slug = {c.slug: c for c in BlogCategory.query.all() if c.slug}
        cat_by_lname = {(c.name or "").lower(): c for c in BlogCategory.query.all()}
        tag_by_slug = {t.slug: t for t in BlogTag.query.all() if t.slug}
        tag_by_lname = {(t.name or "").lower(): t for t in BlogTag.query.all()}
    else:
        # Dry-run: read-only previews — track which slugs / names exist
        # so the count of "would create" is accurate without committing.
        cat_by_slug = {c.slug: True for c in BlogCategory.query.all() if c.slug}
        cat_by_lname = {(c.name or "").lower(): True for c in BlogCategory.query.all()}
        tag_by_slug = {t.slug: True for t in BlogTag.query.all() if t.slug}
        tag_by_lname = {(t.name or "").lower(): True for t in BlogTag.query.all()}

    # Track names already attributed to a "would create" outcome during
    # this dry-run so two posts that share a never-before-seen tag
    # don't both show up as +1 created.
    dry_seen_cats = set()
    dry_seen_tags = set()

    for a in actions:
        t = a["target"]
        p = a["post"]
        if t == "skip":
            counts["skipped"] += 1
            rows.append({"target": "skip", "id": None, "title": p["title"],
                         "slug": None, "image_status": None, "was_renamed": False,
                         "categories": [], "tags": [], "acf_applied": []})
            continue

        # Resolve final slug (auto-suffix on conflict).
        base = a.get("slug") or _slugify(p["title"])
        final_slug = _unique_slug(base, used_slugs.setdefault(t, set()))
        was_renamed = bool(base and final_slug and final_slug != base)
        if was_renamed:
            counts["renamed"] += 1

        # Featured image — image_cb may return either a single
        # stored-filename string (legacy shape) or a (stored, original)
        # tuple (new richer shape so the inline rewriter can build
        # public URLs). Featured image only needs the stored value.
        img_filename = None
        img_status = None
        url = p.get("featured_image_url") or None
        if url:
            if dry_run:
                img_status = "would-download"
            elif image_cb:
                try:
                    cb_result = image_cb(url)
                    if isinstance(cb_result, tuple) and cb_result:
                        img_filename = cb_result[0]
                    else:
                        img_filename = cb_result
                    img_status = "downloaded" if img_filename else "skipped"
                except Exception as e:  # noqa: BLE001
                    counts["image_failed"] += 1
                    warnings.append(f"{p['title'][:60]} — image download failed: {e}")
                    img_status = "failed"

        # Inline images in the post body — walk every <img src/srcset>
        # and rewrite to a freshly-downloaded /pub/<filename> copy so
        # the imported post no longer depends on the source WP site.
        # On dry-run we just count (skip the actual download); on
        # commit the rewriter mutates the body HTML in place.
        body_html = p.get("body_html") or ""
        if body_html and "<img" in body_html.lower():
            if dry_run and count_inline:
                # Heuristic count of <img src=…>/srcset URLs that
                # would be downloaded — exercise the same skip-prefix
                # rules and srcset-splitting logic the real rewriter
                # uses so the preview total matches commit reality.
                try:
                    from bs4 import BeautifulSoup
                    soup_preview = BeautifulSoup(body_html, "html.parser")
                    seen_urls = set()
                    def _maybe_add(u):
                        u = (u or "").strip()
                        if not u: return
                        if any(u.lower().startswith(pfx) for pfx in _INLINE_SKIP_PREFIXES):
                            return
                        seen_urls.add(u)
                    for img in soup_preview.find_all("img"):
                        _maybe_add(img.get("src"))
                        srcset = img.get("srcset") or ""
                        for part in srcset.split(","):
                            bits = part.strip().split()
                            if bits:
                                _maybe_add(bits[0])
                    counts["inline_images_downloaded"] += len(seen_urls)
                except ImportError:
                    pass
            elif image_cb:
                body_html = rewrite_inline_images(
                    body_html, image_cb, counts, warnings, p.get("title", ""))

        # Build the row
        try:
            d = datetime.strptime(p["date"], "%Y-%m-%d").date() if p.get("date") else None
        except (ValueError, TypeError):
            d = None

        row_categories = []
        row_tags = []
        acf_applied = []

        is_archived = bool(archive_keys and p.get("key") in archive_keys)
        is_draft = bool(p.get("is_draft"))
        # Resolve the original WP publish timestamp from the `datetime`
        # field (full ISO) when available, falling back to `date`
        # (YYYY-MM-DD → midnight). NULL when neither parses so the
        # save handler can default to "now" upstream.
        published_at = None
        for raw in (p.get("datetime"), p.get("date")):
            if not raw:
                continue
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
                try:
                    published_at = datetime.strptime(raw[:19], fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if published_at:
                break
        # Resolve the user-defined (or legacy-auto) custom-field mapping
        # for this target up front so EVERY post type — not just events /
        # announcements — can pick up extra fields. ``mapped`` is
        # {dest_col: coerced_value}; ``mapped_cols`` is the applied list
        # for the preview. ``resolved_summary`` lets a dedicated summary
        # field override the WP excerpt.
        mapped, mapped_cols = _extract_target_fields(
            p.get("acf") or {}, t, field_mapping)
        acf_applied = [{"col": c, "value": _acf_preview_value(mapped.get(c))}
                       for c in mapped_cols]
        resolved_summary = (
            mapped.get("summary")
            or ((p.get("summary") or None) and p["summary"][:500] or None)
        )

        if t == "stories":
            row = Story(
                title=p["title"][:255],
                # Only persist explicit slug when the slug differs from
                # the title-derived default — keeps Story.public_slug
                # tracking the title on subsequent renames.
                slug=(final_slug if final_slug != _slugify(p["title"]) else None),
                summary=resolved_summary,
                body=(body_html or None),
                author_name=p.get("author_name"),
                story_date=d,
                published_at=published_at,
                featured_image_filename=img_filename,
                is_draft=is_draft,
                is_archived=is_archived,
                created_by=created_by,
            )
        elif t == "blog":
            row = BlogPost(
                title=p["title"][:255],
                slug=(final_slug if final_slug != _slugify(p["title"]) else None),
                summary=resolved_summary,
                body=(body_html or None),
                author_name=p.get("author_name"),
                published_at=(published_at or
                              (datetime.combine(d, datetime.min.time()) if d else None)),
                featured_image_filename=img_filename,
                is_draft=is_draft,
                is_archived=is_archived,
                created_by=created_by,
            )
        else:
            row = Post(
                title=p["title"][:255],
                slug=(final_slug if final_slug != _slugify(p["title"]) else None),
                summary=resolved_summary,
                body=(body_html or None),
                featured_image_filename=img_filename,
                is_announcement=(t == "announcements"),
                is_event=(t == "events"),
                event_starts_at=(mapped.get("event_starts_at") or
                                 (datetime.combine(d, datetime.min.time())
                                  if (t == "events" and d) else None)),
                published_at=published_at,
                is_draft=is_draft,
                is_archived=is_archived,
                created_by=created_by,
            )
        # Stamp every remaining mapped column onto the row. summary +
        # event_starts_at are already merged into the constructor above;
        # only touch columns that exist on the target model so a mapping
        # to an unknown column can't blow up with an AttributeError.
        for col, val in mapped.items():
            if col in ("event_starts_at", "summary"):
                continue
            if hasattr(row, col):
                setattr(row, col, val)
        if acf_applied:
            counts["acf_fields_applied"] += len(acf_applied)
            counts["acf_rows_enriched"] += 1

        if not dry_run:
            db.session.add(row)
            db.session.flush()
            row_id = row.id
        else:
            row_id = None

        # Resolve categories + tags for blog-targeted posts. We do this
        # AFTER the post row is flushed so the M2M tables have a real
        # parent id to FK against. On dry-run we just count would-create
        # rows; on commit we actually upsert the BlogCategory / BlogTag
        # rows and attach them. The row's `categories` / `tags` summary
        # always tracks the source names so the preview / done page can
        # surface what came along — even when the resolver was a no-op
        # because it was a dry-run.
        if t == "blog":
            for name in (p.get("categories") or []):
                if not (name or "").strip():
                    continue
                resolved = _resolve_blog_category(
                    name, cat_meta.get(name) or {},
                    cat_by_slug, cat_by_lname,
                    dry_run=dry_run, dry_seen=dry_seen_cats, counts=counts,
                )
                if not dry_run and resolved is not None and resolved not in row.categories:
                    row.categories.append(resolved)
                row_categories.append(name)
            for name in (p.get("tags") or []):
                if not (name or "").strip():
                    continue
                resolved = _resolve_blog_tag(
                    name, tag_meta.get(name) or {},
                    tag_by_slug, tag_by_lname,
                    dry_run=dry_run, dry_seen=dry_seen_tags, counts=counts,
                )
                if not dry_run and resolved is not None and resolved not in row.tags:
                    row.tags.append(resolved)
                row_tags.append(name)

        rows.append({
            "target": t,
            "id": row_id,
            "key": p.get("key") or "",
            "title": row.title,
            "slug": final_slug,
            "image_status": img_status,
            "was_renamed": was_renamed,
            "categories": row_categories,
            "tags": row_tags,
            "is_archived": is_archived,
            "is_draft": is_draft,
            "wp_status": p.get("wp_status") or "",
            "acf_applied": list(acf_applied),
        })
        counts[t] += 1
        if is_archived:
            counts["archived"] += 1
        elif is_draft:
            counts["drafts"] += 1

    if not dry_run:
        db.session.commit()
    return {"counts": counts, "rows": rows, "warnings": warnings}


def _resolve_blog_category(name, meta, by_slug, by_lname, *,
                            dry_run, dry_seen, counts):
    """Look up an existing ``BlogCategory`` by slug then case-insensitive
    name; create one when neither matches. Mutates the index dicts so
    subsequent calls in the same plan see freshly-created rows.

    Dry-run mode never touches the DB — it returns ``None`` for every
    resolution but still updates ``counts`` so the preview totals match
    what the commit phase would do."""
    from .models import db, BlogCategory
    src_slug = (meta or {}).get("slug") or ""
    description = (meta or {}).get("description") or ""
    name = (name or "").strip()
    if not name and not src_slug:
        return None
    lname = name.lower()

    if dry_run:
        if src_slug and src_slug in by_slug:
            counts["blog_categories_matched"] += 1
            return None
        if lname and lname in by_lname:
            counts["blog_categories_matched"] += 1
            return None
        # Net-new — count once per name encountered in this plan.
        marker = src_slug or lname
        if marker not in dry_seen:
            dry_seen.add(marker)
            counts["blog_categories_created"] += 1
        return None

    # Commit path.
    existing = None
    if src_slug and src_slug in by_slug:
        existing = by_slug[src_slug]
    elif lname and lname in by_lname:
        existing = by_lname[lname]
    if existing is not None:
        counts["blog_categories_matched"] += 1
        return existing

    # Net-new — slugify the name when source didn't supply one. The
    # slug uniqueness sweep guards against a clash with a row already
    # in the DB whose slug just happens to match.
    base = src_slug or _slugify(name) or "category"
    used_slugs_set = set(by_slug.keys())
    final_slug = base
    n = 2
    while final_slug in used_slugs_set:
        final_slug = f"{base}-{n}"
        n += 1
    cat = BlogCategory(name=name[:120], slug=final_slug,
                       description=description or None)
    db.session.add(cat)
    db.session.flush()
    by_slug[cat.slug] = cat
    if cat.name:
        by_lname[cat.name.lower()] = cat
    counts["blog_categories_created"] += 1
    return cat


def _resolve_blog_tag(name, meta, by_slug, by_lname, *,
                       dry_run, dry_seen, counts):
    """Mirror of ``_resolve_blog_category`` for ``BlogTag``."""
    from .models import db, BlogTag
    src_slug = (meta or {}).get("slug") or ""
    name = (name or "").strip()
    if not name and not src_slug:
        return None
    lname = name.lower()

    if dry_run:
        if src_slug and src_slug in by_slug:
            counts["blog_tags_matched"] += 1
            return None
        if lname and lname in by_lname:
            counts["blog_tags_matched"] += 1
            return None
        marker = src_slug or lname
        if marker not in dry_seen:
            dry_seen.add(marker)
            counts["blog_tags_created"] += 1
        return None

    existing = None
    if src_slug and src_slug in by_slug:
        existing = by_slug[src_slug]
    elif lname and lname in by_lname:
        existing = by_lname[lname]
    if existing is not None:
        counts["blog_tags_matched"] += 1
        return existing

    base = src_slug or _slugify(name) or "tag"
    used_slugs_set = set(by_slug.keys())
    final_slug = base
    n = 2
    while final_slug in used_slugs_set:
        final_slug = f"{base}-{n}"
        n += 1
    tag = BlogTag(name=name[:80], slug=final_slug)
    db.session.add(tag)
    db.session.flush()
    by_slug[tag.slug] = tag
    if tag.name:
        by_lname[tag.name.lower()] = tag
    counts["blog_tags_created"] += 1
    return tag


# ---------------------------------------------------------------------------
# Image download — used as the ``image_cb`` for apply_plan and (with
# the sister ``_download_image_full``) for the inline-image rewriter.
# Dedupes via MediaItem content_hash so re-imports don't pile up
# redundant copies of the same image.
# ---------------------------------------------------------------------------

def _download_image_full(url, *, uploaded_by=None):
    """Download an image, dedupe by sha256, return ``(stored_filename,
    original_filename)``. The "stored" name is the UUID-prefixed
    filename actually written to disk (used for ``featured_image_*``
    columns); the "original" name is the public-URL slug surfaced via
    ``/pub/<filename>`` (used to rewrite inline ``<img src=…>``
    references in post bodies)."""
    from .models import db, MediaItem
    resp = requests.get(url, timeout=DEFAULT_TIMEOUT, stream=True,
                        headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    data = resp.content
    h = hashlib.sha256(data).hexdigest()
    media = MediaItem.query.filter_by(content_hash=h).first()
    if media:
        return media.stored_filename, media.original_filename
    parsed = urlparse(url)
    ext = (os.path.splitext(parsed.path)[1] or "").lower()
    if not ext or len(ext) > 6:
        # Pick from Content-Type when the URL didn't carry a usable ext.
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        ext = {
            "image/jpeg": ".jpg", "image/png": ".png",
            "image/webp": ".webp", "image/gif": ".gif",
        }.get(ctype, ".bin")
    stored = f"{uuid.uuid4().hex}{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    with open(os.path.join(upload_dir, stored), "wb") as f:
        f.write(data)
    original_raw = os.path.basename(parsed.path) or "wp-image"
    original = secure_filename(original_raw) or stored
    m = MediaItem(stored_filename=stored,
                  original_filename=original,
                  content_hash=h, size_bytes=len(data),
                  mime_type=resp.headers.get("Content-Type"),
                  uploaded_by=uploaded_by)
    db.session.add(m)
    db.session.flush()
    return stored, original


def download_image_to_uploads(url, *, uploaded_by=None):
    """Legacy single-return shim. Featured-image callsite uses this
    (returns the stored filename so ``featured_image_filename`` lands
    on the row directly)."""
    stored, _original = _download_image_full(url, uploaded_by=uploaded_by)
    return stored


# ---------------------------------------------------------------------------
# Inline image rewriter — finds <img src=…> + <img srcset=…> in a post
# body's HTML, downloads each unique URL, and rewrites the attribute
# values to /pub/<filename> so the imported post no longer depends on
# the source WP site staying online. Failures are non-fatal: the
# original URL stays put and a warning is added so admins can chase
# them up.
# ---------------------------------------------------------------------------

# URLs we shouldn't try to download — data: blobs are inline, http://
# protocol-relative paths might be intentional, blob: never resolves
# from the server side.
_INLINE_SKIP_PREFIXES = ("data:", "blob:", "javascript:", "#", "/pub/")


def rewrite_inline_images(html, image_cb, counts, warnings, post_title):
    """Walk every ``<img>`` in ``html`` and rewrite each ``src`` /
    ``srcset`` URL to a freshly-downloaded local copy via
    ``image_cb`` (which is the same callback ``apply_plan`` uses for
    the featured image — returning ``(stored, original)``).

    ``counts`` is mutated in place: ``inline_images_downloaded`` for
    each successfully rewritten URL, ``inline_images_failed`` for
    each download error. Failures keep the original URL in place so
    the post still renders (with a broken image) rather than losing
    the reference entirely. Returns the rewritten HTML."""
    if not html or "<img" not in html.lower():
        return html
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html
    soup = BeautifulSoup(html, "html.parser")
    # Per-batch URL → new public path cache so two posts that share an
    # image only download once. Survives across calls within the same
    # apply_plan thanks to image_cb's MediaItem dedupe, but the cache
    # makes the in-batch case cheap (no DB hit).
    cache = {}

    def _rewrite_one(url):
        url = (url or "").strip()
        if not url:
            return None
        if any(url.lower().startswith(prefix) for prefix in _INLINE_SKIP_PREFIXES):
            return None
        if url in cache:
            return cache[url]
        try:
            result = image_cb(url)
        except Exception as e:  # noqa: BLE001
            counts["inline_images_failed"] = counts.get("inline_images_failed", 0) + 1
            warnings.append(f"{(post_title or '')[:60]} — inline image download failed for {url[:80]}: {e}")
            cache[url] = None
            return None
        # image_cb returns (stored, original) — original is the public
        # URL slug. Older single-return shape (legacy callers) returns
        # just the stored filename and we can't build a public URL,
        # so log a warning and bail.
        if isinstance(result, tuple) and len(result) == 2:
            _stored, original = result
        else:
            cache[url] = None
            return None
        if not original:
            cache[url] = None
            return None
        new_url = "/pub/" + original
        cache[url] = new_url
        counts["inline_images_downloaded"] = counts.get("inline_images_downloaded", 0) + 1
        return new_url

    for img in soup.find_all("img"):
        src = img.get("src")
        new_src = _rewrite_one(src)
        if new_src:
            img["src"] = new_src
        # `srcset` carries comma-separated "<url> <descriptor>" pairs;
        # rewrite each url in place so responsive variants all point
        # at local copies.
        srcset = img.get("srcset")
        if srcset:
            new_parts = []
            changed = False
            for part in srcset.split(","):
                part = part.strip()
                if not part:
                    continue
                bits = part.split()
                if not bits:
                    new_parts.append(part)
                    continue
                u = bits[0]
                rewritten = _rewrite_one(u)
                if rewritten:
                    bits[0] = rewritten
                    changed = True
                new_parts.append(" ".join(bits))
            if changed:
                img["srcset"] = ", ".join(new_parts)
    # BeautifulSoup serializes back to a string. We use `unicode_attribute_set`
    # implicitly so attributes with quotes round-trip safely.
    return str(soup)
