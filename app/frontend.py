# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public-facing frontend blueprint.

When `SiteSetting.frontend_enabled` is True, requests to the root URL serve
a marketing/content homepage instead of bouncing straight to the login
screen. When the toggle is off, the root URL redirects to the admin login.

Admin pages remain at /tspro/* and the authenticated dashboard is at /tspro/.
"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from .models import SiteSetting, Meeting, FrontendNavItem

bp = Blueprint("frontend", __name__)

# ---------------------------------------------------------------------------
# Template library — ships layout presets for the major public-site regions.
# Each entry defines a template key, a display name, a description, and the
# Jinja partial path to include in frontend/base.html. Adding a new header
# layout is just a matter of dropping a template file into templates/frontend/
# headers/ and appending to HEADER_TEMPLATES.
#
# Settings (width mode, logo, nav, alert bars) are shared across every
# template so picking a new layout never wipes your content.
# ---------------------------------------------------------------------------
HEADER_TEMPLATES = [
    {
        "key": "classic",
        "name": "Classic",
        "description": "Sticky glassy header with a logo on the left and nav on the right. The first header we built — fluid opacity on scroll, Inter/Fraunces typography.",
        "partial": "frontend/headers/classic.html",
    },
    {
        "key": "dccma",
        "name": "DCCMA",
        "description": "Two-row layout inspired by dccma.com: a blue utility strip on top (helpline + hyperlist link), wide logotype on the left of the main row, and a row of primary nav links on the right. White-on-white with a soft hairline divider.",
        "partial": "frontend/headers/dccma.html",
    },
]

FOOTER_TEMPLATES = [
    {
        "key": "classic",
        "name": "Classic",
        "description": "Three-column footer with logo + tagline on the left, a short link list in the middle, and the copyright text on the right. Our original design.",
        "partial": "frontend/footers/classic.html",
    },
    {
        "key": "dccma",
        "name": "DCCMA",
        "description": "Fellowship-style footer with meeting-location cards, a contact block, and a secondary link row — inspired by dccma.com.",
        "partial": "frontend/footers/dccma.html",
    },
]

MEGAMENU_TEMPLATES = [
    {
        "key": "classic",
        "name": "Classic",
        "description": "Compact card-style dropdown: centered white panel with a soft shadow and subtle dividers between columns. Uses an inline arrow glyph after each link, no full-width color wash.",
        "partial": "frontend/megamenus/classic.html",
    },
    {
        "key": "dccma",
        "name": "DCCMA",
        "description": "Full-width colored panel inspired by dccma.com: bold bg color with rounded bottom corners, animated chevrons, and a hover-slide effect on each link.",
        "partial": "frontend/megamenus/dccma.html",
    },
]

HOMEPAGE_TEMPLATES = [
    {
        "key": "classic",
        "name": "Classic",
        "description": "Animated-blob hero, 4 quick-link cards, upcoming-meetings grid, about pillars, dark contact CTA. Our original homepage.",
        "partial": "frontend/homepages/classic.html",
    },
    {
        "key": "dccma",
        "name": "DCCMA",
        "description": "Fellowship hero with a serving-area statement, a Meetings / Literature / Fellowship three-up, Today's Meetings preview, and CTAs — inspired by dccma.com.",
        "partial": "frontend/homepages/dccma.html",
    },
]


def _template_meta(templates, key):
    for t in templates:
        if t["key"] == key:
            return t
    return templates[0]


def _site():
    return SiteSetting.query.first()


def _frontend_context(site):
    """Shared context values for every frontend page."""
    header_tpl = _template_meta(
        HEADER_TEMPLATES,
        (site.frontend_header_template if site else None) or "classic",
    )
    footer_tpl = _template_meta(
        FOOTER_TEMPLATES,
        (site.frontend_footer_template if site else None) or "classic",
    )
    homepage_tpl = _template_meta(
        HOMEPAGE_TEMPLATES,
        (site.frontend_homepage_template if site else None) or "classic",
    )
    megamenu_tpl = _template_meta(
        MEGAMENU_TEMPLATES,
        (site.frontend_megamenu_template if site else None) or "dccma",
    )
    nav_items = (FrontendNavItem.query
                 .order_by(FrontendNavItem.position, FrontendNavItem.id)
                 .all())
    return {
        "site": site,
        "header_template_partial": header_tpl["partial"],
        "header_template_key": header_tpl["key"],
        "footer_template_partial": footer_tpl["partial"],
        "footer_template_key": footer_tpl["key"],
        "homepage_template_partial": homepage_tpl["partial"],
        "homepage_template_key": homepage_tpl["key"],
        "megamenu_template_partial": megamenu_tpl["partial"],
        "megamenu_template_key": megamenu_tpl["key"],
        "nav_items": nav_items,
        "frontend_title": (site.frontend_title if site else None) or "Trusted Servants",
        "frontend_tagline": (site.frontend_tagline if site else None)
            or "A recovery fellowship portal.",
        "frontend_hero_heading": (site.frontend_hero_heading if site else None)
            or "You are not alone.",
        "frontend_hero_subheading": (site.frontend_hero_subheading if site else None)
            or "Find meetings, connect with your community, and take the next step in your recovery journey.",
        "frontend_about_heading": (site.frontend_about_heading if site else None)
            or "About the Fellowship",
        "frontend_about_body": (site.frontend_about_body if site else None) or "",
        "frontend_contact_heading": (site.frontend_contact_heading if site else None)
            or "Need Help Right Now?",
        "frontend_contact_body": (site.frontend_contact_body if site else None) or "",
        "frontend_footer_text": (site.frontend_footer_text if site else None) or "",
    }


@bp.route("/")
def index():
    site = _site()
    # If the entire module is disabled, nobody sees the public frontend —
    # not even an admin. They must re-enable it from the settings modal first.
    if not site or not site.frontend_module_enabled:
        return redirect(url_for("auth.login"))
    if not site.frontend_enabled:
        # Public toggle is off — only admins and frontend editors can preview
        # so they can keep building the site. Regular editors and viewers
        # get bounced like anonymous visitors.
        if not (current_user.is_authenticated and current_user.can_edit_frontend()):
            return redirect(url_for("auth.login"))
    # Preview a handful of the soonest-starting meetings for the homepage.
    meetings = (Meeting.query
                .filter(Meeting.archived_at.is_(None))
                .order_by(Meeting.name)
                .limit(6).all())
    ctx = _frontend_context(site)
    return render_template("frontend/index.html", meetings=meetings, **ctx)
