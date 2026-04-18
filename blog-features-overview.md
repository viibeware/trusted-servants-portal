# Trusted Servants Pro: a tour of the portal

Trusted Servants Pro is a self-hosted portal built specifically for recovery fellowships — a single place to manage meetings, share readings and files, coordinate Zoom host accounts, and handle member access requests. It runs as one small Docker container on a modest server and is administered entirely from a web UI. No command line required after install.

Here's a walk through what's inside.

## Meetings, the way groups actually use them

Every meeting gets its own page with the information a member actually needs in the moment: the weekly schedule (unlimited slots, with "doors open" times), the meeting type (in-person, online, or hybrid), the address or Zoom details, and the readings the meeting uses. Zoom meeting IDs, passcodes, and join links sit right on the page with click-to-copy buttons and a reveal control for sensitive fields. For hybrid and online meetings, the OTP email credentials are embedded too — so members can pull the one-time code themselves without having to text an admin at 6:59pm.

Admins and editors can create, edit, archive, and restore meetings; attach libraries in "all" or "granular" mode so a meeting shows exactly the readings it uses; and drop documents, scripts, links, videos, and images onto any meeting.

## Libraries and readings

Libraries are ordered collections of readings — think step studies, traditions, a group's custom packet. Drag-and-drop reordering, inline edit, thumbnails, optional inline body text, and external-link entries cover most of what a group needs to publish without asking anyone to write HTML.

## A proper File Browser

Every upload across the app — meeting attachments, reading thumbnails, logos — is indexed into a single media library. Search it, sort it, switch between grid and table views, rename in place, upload with progress, and delete with a reference-count guard so a file in use can't be accidentally removed. Clicking an image or PDF opens it in a lightbox modal, right where you are, instead of kicking you off to a new tab.

**File management is self-service.** Any trusted servant with an editor role can upload new files, replace existing ones, rename, reorganize, and attach them to meetings and libraries — no admin needed to push a file up for them. The group's secretary can swap tonight's script, the literature chair can refresh a reading, the webservant can drop in a new logo, all from the same web UI, all without filing a ticket or waiting for someone with server access.

Public, human-readable file URLs at `/pub/<filename>` mean you can share a link without exposing any hashes or tokens.

## Zoom host accounts

Shared Zoom host accounts get their own module: credentials are stored encrypted with a local Fernet key, OTP email credentials live alongside, and a weekly assignment calendar automatically flags time conflicts when two meetings try to use the same account in overlapping slots. Members see the credentials they need on the meeting page; admins manage the accounts in one place.

## Access requests

A public Request Access form on the login screen captures the basics — name, contact, role(s), meeting of interest — and emails it to a configurable recipient list. An admin-only Access Requests page (with a pending-count badge on the sidebar) handles triage: mark handled, reopen, or delete.

## Login, themes, and branding

Six full palettes ship in the box, including Light, Dark, Neobrutal, Cyberpunk, and Solarpunk. The login screen features an animated particle background with nine selectable effects, speed and size sliders, mouse-reactive physics, and an optional 3D door-opening transition on successful sign-in. Everything — logos, colors, sidebar footer, login look — is configurable from Settings with no asset pipeline or rebuild.

## Mobile, dashboard, settings

The whole app has dedicated mobile layouts: stacked data cards replace wide tables, the sidebar becomes a slide-in drawer, Settings becomes a full-viewport modal with horizontally-scrollable tabs. The dashboard has a configurable widget grid (recent meetings, libraries, files, intergroup info, PIC contact, access requests) so each role sees what matters to them.

A first-run setup wizard walks new admins through password, PIC info, SMTP, theme, branding, and Turnstile in six steps. First-time non-admin members get a guided tour on the dashboard, replayable any time from the Help modal.

## Performance

The app is Flask + SQLAlchemy + SQLite, served by gunicorn and reverse-proxied by Caddy, all inside a single Docker container. There's no content-management system loading plugins on every page, no external database to round-trip, and no build step between "edit a setting" and "see it live." Pages render in well under a second on typical connections; navigating between Meetings, Libraries, and the File Browser feels instant; the dashboard and file lightbox open without a full page load. It's happy on 1 vCPU / 1 GB RAM for a small group, and scales comfortably from there.

## One-click data portability

Export produces a zip containing a VACUUM-copied database, every upload, and the encryption key. Import takes an export archive, backs up the current data to a timestamped folder, restores, re-runs migrations, and signs you out. Moving between servers — or keeping a tested backup — is a button.

## Security basics, done right

Role-based access (admin / editor / viewer) gates every edit route. Rich-text input is sanitized through a bleach allowlist. Zoom and SMTP passwords are encrypted at rest with a Fernet key derived from the server's secret. The one-command installer sets up TLS via Let's Encrypt, locks down the firewall, and keeps the container up to date with Watchtower.

## Getting started

```bash
docker compose up -d --build
```

That's the whole install on a laptop. For a production server on Ubuntu 24.04, `install.sh` provisions Docker, writes a hardened compose file, generates keys, configures Caddy for TLS, and installs Watchtower — all from one command.

Trusted Servants Pro is purpose-built for the people who keep fellowships running, and designed to stay out of their way. Spin it up, brand it, import your meetings, and hand it to your group.
