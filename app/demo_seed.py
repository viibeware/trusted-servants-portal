# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed the golden demo dataset: the (fictitious) **Meridian Recovery
Collective** — a modern, inclusive, online-first recovery fellowship.

``seed_demo_data(app)`` is idempotent: it only populates an empty database
(detected by "no meetings yet"), so it's safe to call on every boot. It runs in
demo mode AFTER the normal boot seeders (admin user, homepage Page, layout
presets), against the golden DB (no request context ⇒ the demo connection
creator targets golden).

Everything here is invented for demonstration. Names, phone numbers, email
addresses, Zoom IDs, and meeting details are not real.
"""
import json
import os
import uuid
from datetime import datetime, timedelta, date

from flask import current_app
from werkzeug.security import generate_password_hash

from .colors import slugify
from .models import (
    db, User, SiteSetting, Meeting, MeetingSchedule, MeetingFile, MeetingLibrary,
    Location, Library, LibraryItem, Post, Story, BlogCategory, BlogTag, BlogPost,
    Fellowship, IntergroupOfficer, TrustedServantSubscriber, Page, FrontendNavItem,
)

FELLOWSHIP_NAME = "Meridian Recovery Collective"
TAGLINE = "Recovery without borders."

# Meridian palette — deep indigo + teal, modern and tech-forward.
BRAND = "#5145E5"
BRAND_DARK = "#4338CA"
ACCENT = "#14B8A6"
INK = "#0E1330"


# ── small block helpers (page / zoom-tech blocks_json schema) ───────────────
def _blk(type_, **data):
    return {"id": uuid.uuid4().hex[:8], "type": type_, "data": data}


def _section(title, blocks):
    return {"id": uuid.uuid4().hex[:8], "title": title or "", "_orphans": False,
            "blocks": blocks}


# ── brand asset ─────────────────────────────────────────────────────────────
def _write_logo():
    """Write the Meridian wordmark SVG into the (golden) uploads dir and return
    its stored filename, or None on failure."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="280" height="56" '
        'viewBox="0 0 280 56" fill="none">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BRAND}"/>'
        f'<stop offset="1" stop-color="{ACCENT}"/></linearGradient></defs>'
        '<circle cx="28" cy="28" r="20" fill="none" stroke="url(#g)" stroke-width="3"/>'
        '<path d="M8 28 H48 M28 8 V48 M14 16 Q28 28 14 40 M42 16 Q28 28 42 40" '
        'fill="none" stroke="url(#g)" stroke-width="2" opacity="0.85"/>'
        '<text x="60" y="36" font-family="Inter,Segoe UI,Arial,sans-serif" '
        f'font-size="26" font-weight="700" fill="{INK}">Meridian</text>'
        '</svg>'
    )
    try:
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        stored = f"{uuid.uuid4().hex}_meridian-logo.svg"
        with open(os.path.join(upload_dir, stored), "w", encoding="utf-8") as fh:
            fh.write(svg)
        return stored
    except OSError:
        return None


# ── users ───────────────────────────────────────────────────────────────────
def _seed_users():
    """Ensure the three demo roles exist with predictable credentials so the
    banner can advertise admin/admin, editor/editor, viewer/viewer."""
    wanted = [
        ("admin", "admin", "admin", "Alex Rivera (Webservant)", "webservant@meridianrecovery.example"),
        ("editor", "editor", "editor", "Jamie Chen (Editor)", "editor@meridianrecovery.example"),
        ("viewer", "viewer", "viewer", "Sam Patel (Member)", "member@meridianrecovery.example"),
    ]
    for username, password, role, name, email in wanted:
        u = User.query.filter_by(username=username).first()
        if u is None:
            u = User(username=username, email=email,
                     password_hash=generate_password_hash(password),
                     role=role, name=name)
            db.session.add(u)
        else:
            # First-boot seed: normalise to the advertised demo password/role.
            u.password_hash = generate_password_hash(password)
            u.role = role
            u.name = name
            u.email = email
    db.session.flush()
    return User.query.filter_by(username="admin").first()


# ── site settings / branding / modules ──────────────────────────────────────
def _seed_site(logo, admin):
    s = SiteSetting.query.first()
    if s is None:
        s = SiteSetting()
        db.session.add(s)
        db.session.flush()

    s.site_url = "https://demo.meridianrecovery.example"
    s.timezone = "America/New_York"
    # Skip the first-run setup wizard so the demo admin lands on the real
    # dashboard instead of the onboarding flow.
    s.setup_complete = True

    # Public frontend ON for anonymous visitors.
    s.frontend_module_enabled = True
    s.frontend_enabled = True

    # Branding.
    s.frontend_title = FELLOWSHIP_NAME
    s.frontend_tagline = TAGLINE
    s.frontend_tagline_enabled = True
    if logo:
        s.frontend_logo_filename = logo
        s.frontend_logo_width = 200
        s.footer_logo_filename = logo
        s.footer_logo_width = 180

    # Modern fellowship chrome.
    s.frontend_theme = "recovery-blue"
    s.frontend_default_theme = "system"
    s.frontend_header_template = "recovery-blue"
    s.frontend_megamenu_template = "recovery-blue"
    s.frontend_footer_template = "classic"
    s.frontend_mega_bg_color = BRAND_DARK
    s.frontend_mega_text_color = "#ffffff"

    # Recolour the theme to Meridian's palette via design-token overrides.
    s.frontend_design_json = json.dumps({
        "color_brand": BRAND,
        "color_accent": ACCENT,
        "color_link": BRAND,
        "color_link_hover": BRAND_DARK,
        "color_btn_primary_bg": BRAND,
        "color_btn_primary_hover_bg": BRAND_DARK,
        "color_btn_primary_text": "#ffffff",
    })

    # Showcase everything.
    s.posts_enabled = True
    s.posts_required_role = "editor"
    s.stories_enabled = True
    s.stories_required_role = "editor"
    s.blog_enabled = True
    s.blog_required_role = "editor"
    s.frontend_fellowships_enabled = True
    s.zoom_tech_enabled = True
    s.zoom_tech_required_role = "viewer"
    s.trusted_servants_enabled = True
    s.trusted_servants_required_role = "editor"
    s.intergroup_module_enabled = True
    s.frontend_site_index_enabled = True
    s.submission_form_enabled = True
    s.story_form_enabled = True
    s.contact_form_enabled = True

    # Public information contact.
    s.pic_name = "Public Info Desk"
    s.pic_email = "info@meridianrecovery.example"
    s.pic_phone = "+1 (555) 016-2049"
    s.contact_form_to = "info@meridianrecovery.example"
    s.contact_form_heading = "Reach the Meridian info desk"
    s.contact_form_subheading = ("Questions about meetings, service, or getting "
                                 "started? Send a note — a trusted servant will reply.")
    s.access_request_to = "info@meridianrecovery.example"

    # Utility bar (recovery-blue top strip).
    s.utility_bar_enabled = True
    s.utility_bar_bg_color = BRAND_DARK
    s.utility_bar_text_color = "#ffffff"
    s.utility_bar_left_json = json.dumps([
        {"kind": "text", "label": "Recovery without borders — meetings in every time zone"},
    ])
    s.utility_bar_right_json = json.dumps([
        {"kind": "link", "label": "Need help now?", "url": "/contact", "icon": "heart"},
        {"kind": "link", "label": "Newcomers", "url": "/newcomers", "icon": "info"},
    ])

    # Zoom & Tech hub content.
    s.zoom_tech_title = "Zoom & Tech Hub"
    s.zoom_tech_template = "standard"
    s.zoom_tech_blocks_json = json.dumps([
        _section("Hosting an online meeting", [
            _blk("paragraph", md=(
                "Every Meridian meeting runs the same way so members feel at home "
                "wherever they land. This hub collects the checklists and scripts "
                "our hosts and co-hosts use.")),
            _blk("list", ordered=False, items=[
                "Open the room 15 minutes early and admit from the waiting room.",
                "Spotlight the chairperson and mute on entry.",
                "Post the welcome + format link in chat.",
                "Keep a co-host ready to manage security.",
            ]),
        ]),
        _section("Security best practices", [
            _blk("callout", variant="info", title="Keep the room safe",
                 md=("Enable the **waiting room**, disable participant screen-share "
                     "by default, and keep at least one co-host watching chat. If "
                     "the room is disrupted, suspend participant activities and "
                     "re-admit known members.")),
            _blk("list", ordered=True, items=[
                "Waiting room: ON",
                "Screen share: host & co-host only",
                "Rename / annotate: off for participants",
                "Co-host removes, host re-secures",
            ]),
        ]),
    ])
    db.session.flush()
    return s


# ── locations ────────────────────────────────────────────────────────────────
def _seed_locations():
    locs = {}
    data = [
        ("Meridian Community Center", "in_person", "418 Lighthouse Ave", "Portsmouth", "NH", "03801"),
        ("Harbor Wellness Annex", "in_person", "27 Dockside Lane", "Portland", "ME", "04101"),
    ]
    for name, ltype, street, city, state, zc in data:
        loc = Location(name=name, location_type=ltype, street=street, city=city,
                       state=state, zip_code=zc,
                       address=f"{street}, {city}, {state} {zc}")
        db.session.add(loc)
        locs[name] = loc
    db.session.flush()
    return locs


# ── meetings ─────────────────────────────────────────────────────────────────
def _seed_meetings(locs, libraries):
    """Create a spread of online / hybrid / in-person meetings with schedules,
    (fake) Zoom credentials, and a few public scripts. Links the online meetings
    to the shared Meeting Scripts library so the public meeting pages have
    readings."""
    scripts_lib = libraries["Meeting Scripts"]

    def zoom(n):
        return (f"{810_000_0000 + n}", "meridian", f"https://zoom.us/j/{810_000_0000 + n}")

    M = [
        # name, type, days[(dow,start,dur)], location, blurb
        ("Sunrise Serenity", "online",
         [(d, "07:00", 30) for d in range(7)], None,
         "A gentle 30-minute meditation and reading to start the day. Daily, 7:00 AM ET."),
        ("Midday Reset", "online",
         [(d, "12:00", 60) for d in range(0, 5)], None,
         "A lunch-hour discussion meeting, Monday through Friday. Drop in for 15 minutes or stay the hour."),
        ("Newcomers Welcome", "online",
         [(0, "18:00", 60)], None,
         "Brand new? Start here. A patient, judgement-free room focused entirely on the first days of recovery."),
        ("Steps & Traditions Study", "hybrid",
         [(1, "19:00", 90)], "Meridian Community Center",
         "We read and discuss one step or tradition each week — in person and online together."),
        ("Women's Circle", "online",
         [(2, "19:30", 60)], None,
         "A women-only sharing meeting. Safe, supportive, and confidential."),
        ("Men's Stag", "online",
         [(3, "20:00", 60)], None,
         "A men-only discussion meeting."),
        ("Literature Hour", "online",
         [(4, "12:00", 60)], None,
         "Reading and reflection straight from the fellowship's literature."),
        ("Friday Night Speaker", "hybrid",
         [(4, "20:00", 75)], "Harbor Wellness Annex",
         "A featured speaker shares their experience, strength, and hope, followed by open sharing."),
        ("Saturday Morning Gratitude", "in_person",
         [(5, "09:00", 60)], "Meridian Community Center",
         "Coffee, connection, and a gratitude-focused topic. In person only."),
        ("Late Night Lifeline", "online",
         [(d, "23:00", 60) for d in range(7)], None,
         "When the rooms close and the night feels long, we're still here. Nightly, 11:00 PM ET."),
        ("Sunday Reflections", "online",
         [(6, "17:00", 60)], None,
         "Closing the week with a reflective, slower-paced discussion."),
        ("Young People in Recovery", "online",
         [(2, "18:00", 60)], None,
         "By and for younger members, but all are welcome."),
    ]

    for i, (name, mtype, days, locname, blurb) in enumerate(M, start=1):
        zid, zpc, zurl = zoom(i)
        m = Meeting(name=name, meeting_type=mtype, description=blurb)
        if mtype in ("online", "hybrid"):
            m.zoom_meeting_id, m.zoom_passcode, m.zoom_link = zid, zpc, zurl
            m.zoom_opens_time = days[0][1]
        if locname:
            loc = locs.get(locname)
            if loc:
                m.location = loc.address
                m.location_notes = f"Meets at {loc.name}."
        db.session.add(m)
        db.session.flush()
        for dow, start, dur in days:
            db.session.add(MeetingSchedule(
                meeting_id=m.id, day_of_week=dow, start_time=start,
                duration_minutes=dur))
        # Online meetings get the shared scripts library, publicly visible.
        if mtype in ("online", "hybrid"):
            db.session.add(MeetingLibrary(
                meeting_id=m.id, library_id=scripts_lib.id, mode="all",
                public_visible=True))
        # A couple of meetings get a public attachment.
        if name == "Newcomers Welcome":
            db.session.add(MeetingFile(
                meeting_id=m.id, category="scripts", title="Newcomers Welcome Script",
                body=("# Welcome\n\nWe're glad you're here. The only requirement for "
                      "membership is a desire to stop. You never have to share, and you "
                      "can keep your camera off.\n\n*Read by the chairperson at the start "
                      "of every Newcomers meeting.*"),
                public_visible=True, position=0))
        db.session.flush()
    return Meeting.query.count()


# ── libraries ────────────────────────────────────────────────────────────────
def _seed_libraries(admin):
    """Create public literature libraries with markdown 'reading' items so the
    /library page and the homepage library block have content."""
    libs = {}

    def make_lib(name, desc):
        lib = Library(name=name, description=desc, public_visible=True,
                      categories_required=False)
        db.session.add(lib)
        db.session.flush()
        libs[name] = lib
        return lib

    def item(lib, title, body=None, url=None, summary=None, pos=0):
        db.session.add(LibraryItem(
            library_id=lib.id, title=title, body=body, url=url, summary=summary,
            position=pos, public_visible=True, created_by=admin.id if admin else None))

    nl = make_lib("Newcomer Packet",
                  "Everything you need for your first meeting and first days.")
    item(nl, "Welcome to Meridian", pos=0, summary="Start here.", body=(
        "# Welcome to Meridian Recovery Collective\n\n"
        "If you think you might have a problem, you're in the right place. Meridian "
        "is a fellowship of people who help each other recover — online, in person, "
        "and everywhere in between.\n\n"
        "- **No dues or fees.** We're self-supporting through our own contributions.\n"
        "- **No requirement but a desire to stop.**\n"
        "- **You belong here.** All ages, backgrounds, faiths, and identities are welcome.\n\n"
        "The simplest next step: pick any meeting on the [schedule](/meetings) and just listen."))
    item(nl, "Is this for me? 20 questions", pos=1, summary="A self-check.", body=(
        "# 20 Questions\n\nMany of us found clarity by answering honestly:\n\n"
        "1. Do you use more than you intend to?\n2. Have you tried to stop and couldn't?\n"
        "3. Do you plan your day around using?\n4. Has it affected your relationships?\n"
        "5. Do you hide how much you use?\n\n*…and fifteen more. If you answered yes to "
        "a few, a meeting may help.*"))
    item(nl, "Your first 30 days", pos=2, summary="A gentle plan.", body=(
        "# The First 30 Days\n\n"
        "**Keep it simple.** A meeting a day, a phone number, and a willingness to come back.\n\n"
        "- Get to a meeting today.\n- Get one phone number.\n- Read a little each morning.\n"
        "- Be gentle with yourself.\n\nNinety meetings in ninety days is a tradition for a reason."))
    item(nl, "Online meeting etiquette", pos=3,
         summary="How online rooms work.", body=(
            "# Online meeting etiquette\n\n"
            "- Join a few minutes early and read the welcome in chat.\n"
            "- Mute yourself when you're not sharing.\n"
            "- Camera on or off — both are always welcome.\n"
            "- Share from your own experience; we avoid crosstalk and advice.\n"
            "- What's said here stays here. Anonymity is the spiritual foundation."))

    ms = make_lib("Meeting Scripts",
                  "Formats, chair guides, and checklists for trusted servants.")
    item(ms, "Online Meeting Format (Script)", pos=0, body=(
        "# Online Meeting Format\n\n"
        "**Chair:** Welcome to Meridian. My name is ___ and I'm an addict. "
        "This is the ___ meeting.\n\nLet's open with a moment of silence followed by "
        "the readings posted in chat…\n\n*(Full script continues — readings, "
        "introductions, sharing guidelines, and the close.)*"))
    item(ms, "Chairperson Guide", pos=1, body=(
        "# Chairperson Guide\n\nArrive early, set a warm tone, watch the clock, and "
        "make sure newcomers are welcomed first. Rotate sharing so quieter members "
        "get a chance."))
    item(ms, "Secretary Checklist", pos=2, body=(
        "# Secretary Checklist\n\n- Confirm host & co-host\n- Update the format with "
        "today's reader\n- Note the seventh-tradition link\n- Record the count for the "
        "group conscience"))

    sv = make_lib("Service Materials",
                  "Group conscience, treasury, and service-position guides.")
    item(sv, "Group Conscience Guide", pos=0, body=(
        "# Group Conscience\n\nThe group conscience is how we make decisions together. "
        "We seek substantial unanimity, protect the minority opinion, and put principles "
        "before personalities."))
    item(sv, "Treasurer Basics", pos=1, body=(
        "# Treasurer Basics\n\nKeep a prudent reserve, report monthly, and pass surplus "
        "to the next level of service. Transparency builds trust."))
    item(sv, "Service Positions Overview", pos=2, body=(
        "# Service Positions\n\n**Chair · Secretary · Treasurer · Webservant · Greeter.** "
        "Rotation keeps service healthy — most commitments run 3–6 months."))

    dr = make_lib("Daily Readings",
                  "Short reflections to carry through the day.")
    item(dr, "Just for today", pos=0, body=(
        "# Just for Today\n\nJust for today I will try to live through this day only, "
        "not tackling my whole life at once. Just for today I will be unafraid — "
        "especially unafraid to enjoy what is beautiful."))
    item(dr, "Acceptance", pos=1, body=(
        "# Acceptance\n\nAnd acceptance is the answer to all my problems today. When I "
        "am disturbed, it is because I find some person, place, thing, or situation "
        "unacceptable to me."))
    item(dr, "One day at a time", pos=2, body=(
        "# One Day at a Time\n\nWe didn't get here in a day, and we don't recover in a "
        "day. Progress, not perfection — one day at a time."))

    db.session.flush()
    return libs


# ── posts: events + announcements ────────────────────────────────────────────
def _seed_posts(admin):
    now = datetime.utcnow()

    def post(**kw):
        kw.setdefault("created_by", admin.id if admin else None)
        p = Post(**kw)
        db.session.add(p)
        return p

    # Events.
    post(title="Meridian Annual Online Convention",
         slug="annual-online-convention",
         summary="Three days of speakers, workshops, and marathon meetings — fully online.",
         body=("# Meridian Annual Online Convention\n\nJoin members from around the world "
               "for three days of recovery. Keynote speakers, topic workshops, a newcomers "
               "track, and 24-hour marathon meetings between sessions.\n\nRegistration is "
               "free; contributions welcome."),
         is_event=True, is_announcement=False, is_online=True,
         event_starts_at=now + timedelta(days=24, hours=10),
         event_ends_at=now + timedelta(days=26, hours=18),
         zoom_url="https://zoom.us/j/8100099001", zoom_meeting_id="8100099001",
         published_at=now - timedelta(days=2))
    post(title="Regional Service Workshop",
         slug="regional-service-workshop",
         summary="A hybrid afternoon on carrying the message: outreach, web service, and PI.",
         body=("# Regional Service Workshop\n\nAn interactive afternoon for current and "
               "future trusted servants. Bring your questions about online hosting, "
               "outreach, and public information."),
         is_event=True, is_announcement=False, is_online=False,
         location_name="Meridian Community Center",
         location_address="418 Lighthouse Ave, Portsmouth, NH 03801",
         event_starts_at=now + timedelta(days=12, hours=13),
         event_ends_at=now + timedelta(days=12, hours=17),
         published_at=now - timedelta(days=5))
    post(title="24-Hour Gratitude Marathon",
         slug="gratitude-marathon",
         summary="Around-the-clock meetings handed off across time zones for a full day.",
         body=("# 24-Hour Gratitude Marathon\n\nStarting at midnight ET, a continuous "
               "chain of one-hour meetings circles the globe. Drop in any hour — someone "
               "is always in the room."),
         is_event=True, is_announcement=False, is_online=True,
         event_starts_at=now + timedelta(days=40),
         event_ends_at=now + timedelta(days=41),
         published_at=now - timedelta(days=1))

    # Announcements.
    post(title="New meeting: Late Night Lifeline",
         slug="new-late-night-lifeline",
         summary="A nightly 11:00 PM ET meeting for the hardest hours.",
         body=("We've added **Late Night Lifeline**, a nightly online meeting at "
               "11:00 PM ET. When the other rooms close, this one is open."),
         is_announcement=True, is_event=False,
         published_at=now - timedelta(days=3))
    post(title="Our website just got a refresh",
         slug="website-refresh",
         summary="A cleaner schedule, a new literature library, and dark mode.",
         body=("The site has a fresh look: a clearer [meeting schedule](/meetings), a "
               "browsable [literature library](/library), and automatic dark mode. "
               "Feedback is always welcome via [contact](/contact)."),
         is_announcement=True, is_event=False,
         published_at=now - timedelta(days=8))
    post(title="Call for service: Outreach committee",
         slug="call-for-service-outreach",
         summary="Help carry the message — no experience required.",
         body=("The Outreach committee is looking for a few willing members. If you can "
               "spare an hour a week, we'd love your help reaching people who still "
               "suffer."),
         is_announcement=True, is_event=False,
         published_at=now - timedelta(days=14))
    db.session.flush()


# ── stories ──────────────────────────────────────────────────────────────────
def _seed_stories(admin):
    today = date.today()

    def story(title, author, sober_days, body, days_ago):
        db.session.add(Story(
            title=title, slug=slugify(title), author_name=author,
            summary=body.split("\n\n")[0][:200],
            body=body, sobriety_date=today - timedelta(days=sober_days),
            story_date=today - timedelta(days=days_ago),
            published_at=datetime.utcnow() - timedelta(days=days_ago),
            is_featured=(days_ago == 4), created_by=admin.id if admin else None))

    story("Finding a room that never closes", "Dana M.", 1460,
          ("I got sober in a city with one meeting a week. Then I found Meridian, and "
           "suddenly there was always a room open.\n\nThe first night I logged in I "
           "didn't say a word. I just listened, camera off, and cried a little. They "
           "told me to keep coming back. So I did.\n\nFour years later I chair the "
           "Sunrise meeting most mornings. The room that never closed is the reason "
           "I'm still here."), 4)
    story("From isolation to connection", "Sam R.", 730,
          ("Recovery online sounded lonely to me at first. I was wrong.\n\nThe people "
           "in these little squares became my closest friends. We celebrate "
           "anniversaries, we check in by text, we show up.\n\nTwo years in, I have a "
           "fellowship that spans three continents and a sponsor I've never met in "
           "person — and it works."), 18)
    story("Ninety meetings, ninety days, one screen", "Alex T.", 365,
          ("They suggested ninety meetings in ninety days. With Meridian I did it "
           "without leaving my apartment during a hard winter.\n\nSome days the noon "
           "meeting was the only thing that got me out of bed. One year today, and I'm "
           "grateful for every one of those ninety squares on the screen."), 30)
    db.session.flush()


# ── blog ─────────────────────────────────────────────────────────────────────
def _seed_blog(admin):
    cats = {}
    for name, color in [("Fellowship News", BRAND), ("Service", ACCENT), ("Wellness", "#F59E0B")]:
        c = BlogCategory(name=name, slug=slugify(name), color=color)
        db.session.add(c)
        db.session.flush()
        cats[name] = c
    tags = {}
    for name in ["online-meetings", "newcomers", "gratitude", "traditions", "service"]:
        t = BlogTag(name=name, slug=slugify(name))
        db.session.add(t)
        db.session.flush()
        tags[name] = t

    now = datetime.utcnow()

    def post(title, cat, tagnames, body, days_ago, featured=False, pinned=False, minutes=4):
        p = BlogPost(title=title, slug=slugify(title),
                     summary=body.split("\n\n")[0][:200], body=body,
                     author_name="Meridian Editorial", published_at=now - timedelta(days=days_ago),
                     is_featured=featured, is_pinned=pinned, reading_minutes=minutes,
                     created_by=admin.id if admin else None)
        db.session.add(p)
        db.session.flush()
        p.categories.append(cats[cat])
        for tn in tagnames:
            p.tags.append(tags[tn])

    post("Why an online-first fellowship works", "Fellowship News",
         ["online-meetings", "newcomers"],
         ("When we say *recovery without borders*, we mean it. An online-first "
          "fellowship meets people exactly where they are.\n\n"
          "## The room is always open\n\nTime zones become a feature, not a bug: somewhere "
          "in the world, a Meridian meeting is starting in the next hour.\n\n"
          "## Lower the barrier\n\nNo transport, no childcare scramble, no walking into a "
          "room full of strangers before you're ready. Camera off is always okay."),
         days_ago=2, featured=True, pinned=True, minutes=5)
    post("A beginner's guide to service", "Service",
         ["service", "traditions"],
         ("Service keeps us sober and keeps the doors open. Here's how to start.\n\n"
          "Pick one small commitment — greeter, reader, or timekeeper — and show up for "
          "it. That's the whole secret."),
         days_ago=9, minutes=4)
    post("Building a morning routine that sticks", "Wellness",
         ["gratitude"],
         ("Recovery is built one morning at a time.\n\nA reading, a few minutes of "
          "quiet, and a single meeting on the calendar can change the shape of a day."),
         days_ago=16, minutes=3)
    post("Anniversary spotlight: the Sunrise group turns three", "Fellowship News",
         ["gratitude", "online-meetings"],
         ("Three years ago a handful of early risers started meeting at 7 AM. Today the "
          "Sunrise group welcomes members from a dozen countries every morning."),
         days_ago=23, minutes=3)
    db.session.flush()


# ── fellowships index ────────────────────────────────────────────────────────
def _seed_fellowships():
    rows = [
        ("Open Path Recovery", True, None, None, "https://example.org/open-path"),
        ("Meridian en Español", True, None, None, "https://example.org/meridian-es"),
        ("Northern Lights Fellowship", False, "Canada", "Ontario", "https://example.org/northern-lights"),
        ("Southern Cross Recovery", False, "Australia", "New South Wales", "https://example.org/southern-cross"),
        ("Coastal Regional Fellowship", False, "United States", "New England", "https://example.org/coastal"),
    ]
    for i, (name, virtual, country, region, url) in enumerate(rows):
        db.session.add(Fellowship(name=name, is_virtual=virtual, country=country,
                                  state_region=region, url=url, sort_order=i))
    db.session.flush()


# ── intergroup officers + trusted servants ──────────────────────────────────
def _seed_people():
    officers = [
        ("Chair", "Jordan P.", "+1 (555) 016-3001", "chair@meridianrecovery.example"),
        ("Vice Chair", "Riley K.", "+1 (555) 016-3002", "vicechair@meridianrecovery.example"),
        ("Secretary", "Casey L.", "+1 (555) 016-3003", "secretary@meridianrecovery.example"),
        ("Treasurer", "Morgan S.", "+1 (555) 016-3004", "treasurer@meridianrecovery.example"),
        ("Webservant", "Taylor V.", "+1 (555) 016-3005", "web@meridianrecovery.example"),
    ]
    for i, (role, name, phone, email) in enumerate(officers):
        db.session.add(IntergroupOfficer(role=role, name=name, phone=phone,
                                         email=email, sort_order=i))
    servants = [
        ("Jordan P.", "outreach@meridianrecovery.example", "+1 (555) 016-4001"),
        ("Casey L.", "secretary@meridianrecovery.example", None),
        ("Taylor V.", "web@meridianrecovery.example", None),
        ("Priya N.", "events@meridianrecovery.example", "+1 (555) 016-4004"),
    ]
    for name, email, phone in servants:
        db.session.add(TrustedServantSubscriber(name=name, email=email, phone=phone))
    db.session.flush()


# ── content pages + homepage ─────────────────────────────────────────────────
def _seed_pages(s, libraries, blog_news_id):
    newcomer_lib = libraries["Newcomer Packet"]
    service_lib = libraries["Service Materials"]

    # About page.
    about_blocks = [
        _section("", [
            _blk("hero", heading="About Meridian", eyebrow="Our story",
                 subheading="A fellowship that meets you where you are — any hour, any place.",
                 tagline_enabled=True, heading_font="fraunces", heading_size_pct=120,
                 heading_grad_start=BRAND, heading_grad_end=ACCENT,
                 bg_style="gradient", bg_color=INK, bg_color_2=BRAND_DARK,
                 bg_gradient_angle=135, height_vh_desktop=44, height_vh_mobile=40,
                 buttons=[{"label": "Find a meeting", "url": "/meetings", "style": "primary"}]),
        ]),
        _section("Who we are", [
            _blk("paragraph", md=(
                "Meridian Recovery Collective is a fictitious fellowship created to "
                "demonstrate this portal. In our story, we're a worldwide community of "
                "people recovering together — online-first, inclusive, and open around "
                "the clock.\n\nThe only requirement for membership is a desire to stop. "
                "There are no dues or fees; we're self-supporting through our own "
                "contributions.")),
        ]),
        _section("What we believe", [
            _blk("features", items=[
                {"icon": "globe", "title": "Without borders",
                 "body": "Meetings across every time zone, so the room is always open."},
                {"icon": "heart-handshake", "title": "All are welcome",
                 "body": "Every age, background, faith, and identity has a seat here."},
                {"icon": "shield", "title": "Safe & anonymous",
                 "body": "Cameras off is always okay. What's shared here stays here."},
                {"icon": "users", "title": "Carried by service",
                 "body": "Members keep the doors open by helping the next person in."},
            ]),
        ]),
    ]
    _upsert_page("about", "About", about_blocks)

    # Newcomers page.
    newcomers_blocks = [
        _section("", [
            _blk("hero", heading="New here? Start with us.", eyebrow="Newcomers",
                 subheading="You don't have to have it figured out. Just show up — we'll take it from there.",
                 tagline_enabled=True, heading_font="fraunces", heading_size_pct=120,
                 heading_grad_start=BRAND, heading_grad_end=ACCENT,
                 bg_style="gradient", bg_color=BRAND_DARK, bg_color_2=ACCENT,
                 bg_gradient_angle=130, height_vh_desktop=46, height_vh_mobile=42,
                 buttons=[
                     {"label": "See the schedule", "url": "/meetings", "style": "primary"},
                     {"label": "Read the welcome packet", "url": "/library", "style": "ghost"},
                 ]),
        ]),
        _section("Your first meeting", [
            _blk("paragraph", md=(
                "Pick any meeting on the [schedule](/meetings) and join a few minutes "
                "early. Keep your camera off if you like. You never have to share — "
                "listening is enough.")),
        ]),
        _section("Start reading", [
            _blk("library", library_id=newcomer_lib.id, mode="all", sort="manual",
                 style="cards", columns=2, show_description=True, show_thumbnails=False,
                 title="Newcomer packet"),
        ]),
        _section("Meetings this week", [
            _blk("meetings", filter="next_7_days", max_count=6, group_by_day=False,
                 show_type_chip=True, show_schedule=True),
        ]),
    ]
    _upsert_page("newcomers", "Newcomers", newcomers_blocks)

    # Service page.
    service_blocks = [
        _section("Service keeps us going", [
            _blk("paragraph", md=(
                "Meridian runs entirely on volunteer service. Whether you have ten "
                "minutes or ten hours, there's a way to help carry the message.")),
        ]),
        _section("Service materials", [
            _blk("library", library_id=service_lib.id, mode="all", style="list",
                 show_description=True, title="Guides & checklists"),
        ]),
    ]
    _upsert_page("service", "Service", service_blocks)

    # Homepage — overwrite the auto-seeded "home" page with a rich layout.
    home_blocks = [
        _section("", [
            _blk("hero",
                 heading="Recovery without borders.",
                 eyebrow=FELLOWSHIP_NAME,
                 subheading=("Meetings in every time zone, a welcoming community, and the "
                             "next right step — whenever you're ready."),
                 tagline_enabled=True, heading_font="fraunces", heading_size_pct=135,
                 heading_grad_start="#ffffff", heading_grad_end="#C7D2FE",
                 subheading_font="inter", subheading_color="#E5E7FF",
                 text_dynamic=False,
                 bg_style="gradient", bg_color=INK, bg_color_2=BRAND,
                 bg_gradient_angle=140, height_vh_desktop=72, height_vh_mobile=64,
                 particle_enabled=True, particle_effect="stars",
                 particle_speed=80, particle_size=90,
                 buttons=[
                     {"label": "Find a meeting", "url": "/meetings", "style": "primary",
                      "custom_bg_color": ACCENT, "custom_text_color": "#06241F",
                      "icon_before": "calendar"},
                     {"label": "I'm new", "url": "/newcomers", "style": "ghost"},
                 ]),
        ]),
        _section("", [
            _blk("features",
                 heading="A fellowship built for how people actually live",
                 subheading="Online-first, always open, and run by the people who use it.",
                 items=[
                     {"icon": "globe", "title": "Every time zone",
                      "body": "Somewhere in the world, a Meridian meeting is starting within the hour."},
                     {"icon": "clock", "title": "Around the clock",
                      "body": "From Sunrise Serenity to Late Night Lifeline, the room is always open."},
                     {"icon": "heart-handshake", "title": "All are welcome",
                      "body": "The only requirement is a desire to stop. No dues, no fees, no judgement."},
                     {"icon": "book-open", "title": "Literature & tools",
                      "body": "A browsable library of readings, scripts, and service guides."},
                     {"icon": "video", "title": "Hybrid & in person",
                      "body": "Online rooms plus in-person meetings at our community centers."},
                     {"icon": "shield", "title": "Safe & private",
                      "body": "Cameras off is fine. Hosts keep every room secure."},
                 ]),
        ]),
        _section("", [
            _blk("meetings", filter="next_7_days", max_count=6, group_by_day=False,
                 show_type_chip=True, show_schedule=True),
        ]),
        _section("", [
            _blk("blog_list", category_id=blog_news_id, style="cards", columns=3,
                 sort="newest", max_items=3, show_image=False, show_date=True,
                 show_summary=True, title="From the blog",
                 subtitle="News, service, and reflections from the fellowship."),
        ]),
        _section("You don't have to do this alone", [
            _blk("callout", variant="info", title="Join a meeting today",
                 md=("Somewhere in the world, a Meridian meeting is starting within "
                     "the hour. **[See the full schedule →](/meetings)** or "
                     "[reach the info desk](/contact).")),
        ]),
    ]
    home = Page.query.filter_by(slug="home").first()
    if home is None:
        home = Page(slug="home", title="Home", template="standard",
                    is_published=True, layout_key="custom")
        db.session.add(home)
        db.session.flush()
    home.blocks_json = json.dumps(home_blocks)
    home.title = FELLOWSHIP_NAME
    # Boxed content (centered at max_width) while the hero block itself breaks
    # out to full-bleed via the `.fe-pp .fe-hero` rule added in frontend.css —
    # a full-width hero with comfortably centered content below.
    home.width_mode = "boxed"
    home.max_width = 1160
    db.session.flush()
    if s.homepage_page_id != home.id:
        s.homepage_page_id = home.id
    db.session.flush()


def _upsert_page(slug, title, blocks):
    p = Page.query.filter_by(slug=slug).first()
    if p is None:
        p = Page(slug=slug, title=title, template="standard", is_published=True,
                 layout_key="custom")
        db.session.add(p)
        db.session.flush()
    p.title = title
    p.blocks_json = json.dumps(blocks)
    p.is_published = True
    db.session.flush()
    return p


# ── navigation + footer ──────────────────────────────────────────────────────
def _seed_nav(s):
    if FrontendNavItem.query.count() == 0:
        items = [
            ("Home", "/demo"),
            ("Meetings", "/meetings"), ("Library", "/library"), ("Events", "/events"),
            ("Stories", "/stories"), ("Blog", "/blog"), ("Fellowships", "/fellowships"),
            ("About", "/about"), ("Contact", "/contact"),
        ]
        for i, (label, url) in enumerate(items):
            db.session.add(FrontendNavItem(position=i, style="text", label=label, url=url))

    s.frontend_footer_blocks_json = json.dumps({
        "brand": {"show": True, "show_logo": True,
                  "tagline": "Recovery without borders. A worldwide, online-first fellowship."},
        "columns": [
            {"title": "Meetings", "links": [
                {"label": "Full schedule", "url": "/meetings"},
                {"label": "Printable list", "url": "/printlist"},
                {"label": "Events", "url": "/events"},
            ]},
            {"title": "Get started", "links": [
                {"label": "Newcomers", "url": "/newcomers"},
                {"label": "Literature", "url": "/library"},
                {"label": "Stories", "url": "/stories"},
            ]},
            {"title": "Fellowship", "links": [
                {"label": "About", "url": "/about"},
                {"label": "Service", "url": "/service"},
                {"label": "Blog", "url": "/blog"},
                {"label": "Contact", "url": "/contact"},
            ]},
        ],
        "secondary_nav": [
            {"label": "Site index", "url": "/siteindex"},
            {"label": "Fellowships", "url": "/fellowships"},
        ],
        "copyright": "© {year} Meridian Recovery Collective (a fictitious demo fellowship). "
                     "Built on TSP Pro.",
    })
    db.session.flush()


# ── entry point ──────────────────────────────────────────────────────────────
def seed_demo_data(app):
    """Idempotently populate the golden demo dataset. No-op once meetings exist."""
    if Meeting.query.count() > 0:
        return
    app.logger.info("Seeding demo data: %s", FELLOWSHIP_NAME)
    logo = _write_logo()
    admin = _seed_users()
    s = _seed_site(logo, admin)
    locs = _seed_locations()
    libraries = _seed_libraries(admin)
    _seed_meetings(locs, libraries)
    _seed_posts(admin)
    _seed_stories(admin)
    _seed_blog(admin)
    _seed_fellowships()
    _seed_people()
    news = BlogCategory.query.filter_by(slug=slugify("Fellowship News")).first()
    _seed_pages(s, libraries, news.id if news else 0)
    _seed_nav(s)
    db.session.commit()
    app.logger.info("Demo data seeded.")
