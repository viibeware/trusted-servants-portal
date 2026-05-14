# SPDX-License-Identifier: AGPL-3.0-or-later
"""Timezone helpers.

The portal stores a single IANA timezone (e.g. ``America/Los_Angeles``)
on ``SiteSetting.timezone``. That tz controls anything that asks "what
day / time is it right now?" — most importantly the public meetings
block and the admin meetings dashboard, so the rendered "Today" matches
the fellowship's wall clock instead of the host machine's locale.

Helpers below are deliberately small and importable from anywhere
without dragging in Flask request context.
"""
from datetime import datetime, timezone


_ZONE_NAMES_CACHE = None


def available_timezone_names():
    """Sorted list of every IANA zone name installed on this host."""
    global _ZONE_NAMES_CACHE
    if _ZONE_NAMES_CACHE is None:
        try:
            from zoneinfo import available_timezones
            _ZONE_NAMES_CACHE = sorted(available_timezones())
        except ImportError:
            _ZONE_NAMES_CACHE = ["UTC"]
    return _ZONE_NAMES_CACHE


def _zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except (ImportError, Exception):  # noqa: BLE001
        return timezone.utc


def site_timezone(site):
    """Return the configured ``ZoneInfo`` (or UTC if unset/invalid)."""
    name = (getattr(site, "timezone", None) or "UTC").strip() or "UTC"
    return _zone(name)


def now_in(site):
    """Aware ``datetime`` for "right now" in the site's configured tz."""
    return datetime.now(tz=site_timezone(site))


def now_in_name(name):
    """Aware ``datetime`` in the named tz. Used by the Settings preview."""
    return datetime.now(tz=_zone(name or "UTC"))


def now_local_naive(site):
    """Return the current site-local datetime as a *naive* value
    (tzinfo stripped). Use this when stamping a model column whose
    storage convention is "naive datetimes are site-local" — e.g.
    ``Post.published_at``, which is also parsed naive from the
    HTML5 ``datetime-local`` form input the admin types into. Storing
    ``datetime.utcnow()`` instead would render at the wrong wall-
    clock time site-wide because the display layer treats the stored
    value as already-local."""
    return datetime.now(tz=site_timezone(site)).replace(tzinfo=None)
