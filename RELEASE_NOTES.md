# Release Notes

User-friendly, scannable summary of every Trusted Servants Pro version
bump. The deeper, version-by-version implementation log lives in
[CHANGELOG.md](CHANGELOG.md).

The same content appears in-app under **Settings → About** with the
release notes expanded by default and the changelog collapsed.

## 1.10.1 — 2026-05-14 — Polish pass: meetings list, About tab, post / event editor flow, container gutter

Quick refinements layered on top of 1.10.0 — a release-notes pane in the About tab, the missing desktop gutter restored, several meeting-page touches, and a stack of editorial-flow fixes for the announcements / events module.

- **Settings → About** now leads with a friendly **Release notes** pane (open by default) and tucks the dense Changelog underneath in a collapsed toggle.
- **Container padding — desktop** default flipped to `5vw` (was `0`) so every block that uses `.fe-container` carries a visible left/right gutter at all desktop widths.
- **Meetings list (Sidebar template)**: in-person and hybrid meetings show the location **name + address** at the top of the actions column.
- **Meetings list (Sidebar template)**: admin-curated **custom links** in the rail under the day filters — chevron-right for internal, external-link icon (with new-tab toggle) for external.
- **Backend meeting detail**: *View on Frontend ↗* button now appears whenever the Web Frontend module is enabled (was gated on public visibility), positioned right next to *Edit*.
- **Frontend meeting detail**: Files & Readings panel drops the file-description text under each link — just the title + arrow.
- **Homepage Meetings + Events blocks** dropped the inner `.fe-container` wrapper so their width / gutter is now controlled solely by the surrounding page-builder container — fixes the cards grid getting crushed when site-wide container padding adds on top of the parent's own gutter.
- **Announcements & Events admin**: every row + the post-edit page now have a **Duplicate** button — clones the post into a fresh Draft (title gets a "(copy)" suffix) so you can spin up next month's announcement / event using last month's fields as the seed.
- **Post slug auto-derives from the title when the title changes** on save (with `-2`/`-3`/… suffixes on collision). The slug input still wins when the title is unchanged, so you can rename the URL without touching the title.
- **Live title → slug preview**: typing in the Title field on the post-edit page now rewrites the URL field as you type, with a brief brand-tinted highlight so you can see the URL changing alongside the title.
- **Draft → publish stamps "Posted on" with the current time**: the first time a draft actually goes live, "Published on …" resets to "now" — no more relying on whatever back-date the admin keyed in earlier.
- **Publish + Move-to-Drafts on the post-edit page now save your in-progress edits**. Previously they only flipped the draft state and lost any unsaved changes — you'd have to click Save first, then Publish.
- **Drafts no longer pollute the URL-redirect history**: renaming a draft (or a pending submission) doesn't add a row to `EntitySlugHistory`. Only published posts log a redirect when their URL changes.
- **Auto-stamped post / story published-on times now honour the site timezone**. Previously the auto-stamp wrote UTC and the display rendered it as if local, so a draft published at 5 PM in California would show as 12 AM the next day. Re-save any affected posts (or click Publish again) to refresh the stored value.
- **Frontend export bundle no longer carries Posts** (announcements + events) — those are per-deployment editorial content, not look-and-feel. Pages, stories, navigation, layouts, fonts, icons, design tokens, and media still ride along as before.
- **Homepage side padding survives a frontend export round-trip**. The import path was silently rewriting any page integer column set to `0` (e.g. `full_padding_pct: 0` on a full-bleed page) back to the model's default — so the homepage's gutter reset to 4 % every time. All integer columns on Page now round-trip verbatim.
- **Meeting detail page: description prose caps at 75 % column width above 1024 px** for comfortable line length on wide monitors; tablets / landscape phones / split-screen (≤1024 px) still get the full width. Applied across all four detail templates (Classic, Minimal, Card Stack, Magazine).
- **Event website URL field accepts relative paths** (e.g. `/about-us`) so admins can point an event at a page on the same site without needing the full domain. Full URLs still work; the mobile URL keyboard still comes up.
- **Announcements + Events list pages sort by post date** — newest published at the top, descending. Applies to the Cards view, the GSR Summary view, and the events list. The homepage Upcoming Events block keeps its chronological "next event first" ordering.
- **GSR Summary subheading trimmed** to "Fellowship news, in brief."

## 1.10.0 — 2026-05-14 — Design tokens overhaul + hero button picker chrome

The deepest pass on the design tokens system to date — buttons and cards each split into two-column admin views with live previews above each column, and the hero block's button editor finally gets the same icon picker + colour cluster the rest of the admin uses.

- New **Surface — Darkmode** token controls the dark-mode page background site-wide.
- New per-button border / hover-border / hover-background tokens (8 colours + widths) for both Primary and Secondary styles, with live previews that repaint as you edit.
- New per-card hover-border tokens (Primary + Secondary) — the feature-card accent on hover is now admin-tunable.
- New Container padding tokens (desktop + mobile) — restored the lost 5% mobile gutter site-wide.
- Frontend Features block: each card now gets an inline button (Primary or Secondary, with editable label) instead of the whole card being a link, plus an optional section-level CTA.
- Hero modal button rows: icon picker for the before/after icons, full design-token colour clusters for every colour field.
- Custom links in the meetings sidebar: add internal or external links below the day filters with chevron / external-link icons + open-in-new-tab toggle.

## 1.9.1 — May 2026 — Frontend bundle is now a verbatim copy

Fixes two gaps in the frontend export/import where pages were silently reverting to model defaults on restore. Per-page spacing settings and the homepage designation now ride along correctly.

## 1.9.0 — May 2026 — Homepage is a Page now

The legacy homepage admin is retired. The public `/` root is now driven by whichever Page row you designate as the homepage, with the same page-builder editor you use for every other content page.

- Pick any Page as the homepage from the Pages list — one click flips the designation and publishes.
- Hero block edit modal gains dark-mode controls for the heading gradient and subheading colour.
- Container blocks: per-side border widths, hover border width, variable-driven hover effects.
- New per-page Features and FAQ blocks (verbatim copies of the homepage editors).
- New per-page Meetings list and Upcoming Events blocks.

## 1.8.6 – 1.8.8 — May 2026 — Library import wizard, frontend export coverage, public submission form

Frontend export bundle expanded to cover the full content surface (custom layouts, fonts, icons, hero buttons, media, every frontend SiteSetting). Library import wizard streamlines bringing existing material into a new install. Visitors can submit events and announcements at `/submissionform` for admin review.

## 1.8.5 — May 2026 — Cross-instance cookie isolation

Two TSP instances on the same hostname no longer step on each other's CSRF cookies, fixing a logout-loop scenario when running multiple deployments behind one domain.

## 1.8.4 — April 2026 — Literature Library, Printlist, Hyperlist, frontend search

Three new public surfaces and a global search modal land in one cycle.

- **/library** — public-facing Literature Library with per-item visibility toggles and admin Templates integration.
- **/printlist** + **/printlist.pdf** — branded, print-optimised meeting schedule.
- **/hyperlist** — accessibility-first plain-HTML index of every active meeting (no chrome, no JS, single small payload).
- Frontend-wide search modal — Cmd/Ctrl+K from anywhere, draggable trigger in the utility bar, extensible source registry covering meetings + events out of the box.
- Past-events archive at **/events/archive** with sidebar filter rail.

## 1.8.3 — April 2026 — Footer locations, Pro Tips, Inclusion block

Long polish cycle covering the meetings list, footer location cards, design-token expansion, and several dark-mode fixes.

- "Pro Tips" accordion at the bottom of **/meetings** with a GUI editor (icon picker on every row).
- Statement of Inclusion block for the homepage.
- Meeting Locations: split address fields, location notes, website URL, opened to frontend editors.
- Footer meeting-locations block: frosted-glass cards with first-class location features.
- Default appearance control (light / dark / follow system).
- Recovery Blue primary buttons adopt the meeting-page Zoom-button recipe by default.

## 1.8.0 – 1.8.2 — March 2026 — Meetings list, Live Meetings Bar, Utility Bar admin

The **/meetings** page becomes a three-template picker (Sidebar with day-filter rail, Directory with sticky toolbar, Week board with seven Mon→Sun columns). The Live Meetings Bar replaces the legacy Top Alert Bar, with admin grouping and mobile-aware swipe rails.

- Per-meeting Extended Content section — admin-tunable Markdown blocks below the schedule.
- Public meeting + event detail pages get an Edit shortcut for logged-in editors.
- Click-to-copy chips with a green "Copied!" tooltip.
- Settings → Timezone tab for explicit site-wide timezone control.
- Footer "Powered by Trusted Servants Pro" pill block.

## 1.7.0 – 1.7.17 — February 2026 — Announcements & Events, Design tokens, custom fonts/icons

The Announcements & Events module ships alongside a site-wide Design tokens system, custom font and icon libraries, daily SQLite snapshots, and reusable detail-page Templates.

- New **Upcoming Events** block on the homepage and a dedicated **/events** listing.
- Site-wide Design tokens — Brand, Accent, Surface, Text, Card, Buttons, Links — flow into every region of the public site.
- Recovery Blue theme rename + per-template appearance overrides.
- Custom fonts and custom icons libraries — upload your own and pick them from the same dropdowns as built-ins.
- Customizable public 404 + playful admin 404 page.
- Two-panel split block for side-by-side homepage sections with per-side padding.
- Per-module role permissions and the new Frontend editor role.
- Frontend favicon, OG fields, and meta-tag split (separate from the admin chrome).
- Daily SQLite snapshots saved to `/data/snapshots` with retention.

## 1.6.0 – 1.6.2 — January 2026 — Web Frontend module

The **Web Frontend** module lands — a swappable public marketing site driven by registry-defined templates, with mega menus, alert bars, full nav editor, and a module gate that splits enabled-vs-publicly-visible.

- Swappable templates per region (header, footer, homepage, meeting detail, etc.).
- Full navigation editor with mega menus, search, and admin-only preview banner.
- Frontend bundle import/export for portable site copies.
- Public-asset blueprint and pasted-font pipeline.
- Settings modal "Web Frontend" pane with refresh-on-save hook.
- Update-available banner notices same-version redeploys (image content hash).

## 1.4.0 — December 2025 — File Browser picker rebuild

The File Browser picker is rebuilt with sort + direction controls, preview-before-select, and URL-state preservation so deep-linked picker views survive a refresh.

## 1.3.7 – 1.3.13 — November 2025 — Security hardening + library authoring + lockouts

A long stretch of security hardening (CSRF, secure cookies, XSS, brute-force protection) lands alongside library reading authoring, per-username login lockouts, and an Access Requests redesign.

- CSRF protection, secure cookies, security headers, login brute-force protection.
- Library reading authoring — paste content as an alternative to file upload, with a Markdown editor + paper-styled lightbox.
- On-the-fly PDF download for any pasted reading.
- Per-username login lockout with a DB-backed state and admin-visible chips.
- Access Requests widget redesign + Customize Dashboard toggle.
- Mobile sidebar footer always visible; create user from an access request in one click.

## 1.3.0 – 1.3.6 — October 2025 — AGPLv3, drag-and-drop dashboard, OG previews

The project goes open source under AGPLv3. The dashboard becomes drag-and-drop with per-user widget customisation. Open Graph link previews ship for every share-worthy URL. Server Stats and Server Metrics widgets land for editors and admins.

- Open-source under AGPLv3 with attribution credit on the About page.
- Drag-and-drop dashboard with per-user customisation.
- Universal SVG icons + light mode default on fresh installs.
- Server Stats card with Online Now tile + per-role visibility.
- First-run setup wizard for fresh installs.
- Guided tour for viewers and editors.
- File Browser lightbox for previewing images and PDFs in place.
- Legacy WordPress redirects honoured automatically.

## 1.2 — September 2025 — Rebrand to Trusted Servants Pro

Project renamed from the early working title to Trusted Servants Pro. Third-party branding unbundled; sidebar logo now appears on the login screen.

## 1.1 — September 2025 — Login bot protection + unattended installer

Cloudflare Turnstile gates the login and access-request forms. The installer ships an unattended mode for one-line VPS deploys. HTTP cache headers tightened on auth-sensitive routes.

## 1.0 — August 2025 — First public release

The first public release — a complete portal for fellowship trusted servants covering meetings, libraries, file storage, accounts, Zoom credentials, intergroup info, and tech training.

- Meetings, Libraries & Readings, File Browser, Copy Link buttons.
- Roles & Access (admin / editor / viewer), Request Access flow.
- Zoom Accounts (encrypted credential storage) + Zoom Tech Training playbook.
- Themes (light, dark, neobrutal, cyberpunk, solarpunk) with a 3D login transition.
- Email / SMTP, data export / import, configurable session length.
- Responsive design from day one — every view ships dedicated mobile layouts.
