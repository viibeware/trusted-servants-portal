# Meet the new portal — everything your group needs, finally in one place (and fast)

For years our portal lived as a page on the group's WordPress site. It worked, in the way that a stack of mimeographed handouts works: information was there, eventually, if you were patient and didn't mind reading someone else's formatting choices from 2014.

That era is over. The portal has been rebuilt from the ground up as **Trusted Servants Pro** — a purpose-built, self-hosted application for recovery fellowships. It's fast. It's interactive. It remembers what you clicked last time. And everything you need to find your next meeting, pull up a reading, grab a Zoom link, or look up an OTP code is two clicks away from wherever you are.

![Login screen with animated particle background](./docs/screenshots/01-login.png)
*Placeholder: login screen with the animated background effect.*

## The speed difference is not subtle

The old WordPress portal was a beautiful museum. Click a link, wait for WordPress to render a PHP page, wait for the theme to load, wait for the plugins to weigh in, wait for the sidebar to figure itself out, wait for the ads — there were no ads, but it *felt* like there were ads.

**The new portal renders a page in under a second on most connections.** Navigating between Meetings, Libraries, and the File Browser is instant. The dashboard loads your personalized view before you can finish blinking. Previewing a PDF or image in the File Browser pops it up in a modal right where you are — no new tab, no page reload, no "wait, where did that go?"

Part of that is technology (Flask + SQLite, served by gunicorn, reverse-proxied by Caddy, all of it running in a single Docker container). But mostly it's the result of a design that doesn't ship a content-management system to every reader just so they can see a list of meetings.

![Dashboard showing widgets and stats](./docs/screenshots/02-dashboard.png)
*Placeholder: dashboard view with the role card, server stats, and recent-files widgets.*

## From read-only page to self-service portal

The biggest shift isn't visible, but it'll be the one you notice most.

The old portal was a bulletin board. Somebody with admin rights updated it when they had time. If a meeting's Zoom info changed at 2:45pm and the meeting was at 3:00pm, you were out of luck unless you could get a text through to the right person.

The new portal is self-service. Every meeting has its Zoom meeting ID, passcode, and direct join link on its own page with a **Copy Link** button. Every online meeting that uses a shared Zoom host account shows the host credentials right on the page — with a reveal button, obviously, so it's not sitting in plain text on screen — and also the OTP email credentials so you can grab the one-time code when Zoom asks for it. You don't have to call anyone. You don't have to wait for someone to update a PDF. You just click.

![Meeting detail page with Zoom info](./docs/screenshots/03-meeting-detail.png)
*Placeholder: meeting detail page showing schedule table, Zoom credentials, and attached readings.*

## What editors and viewers can do today

This is the audience for this post, so let's get specific. Whether you're a trusted servant updating content or a member looking something up, here's what's in your hands now.

### Find any meeting in seconds

Open **Meetings** from the sidebar. Default view is a dense table, sorted by name. Want to sort by day or by type (in-person / online / hybrid)? One click. Want the card view? One click. Your preference is remembered in a cookie, so the next time you open the page, it's the way you left it.

Click into any meeting and you get the full picture: schedule grid (day + start + opens time + duration), Zoom info, physical location with a map link if it's in-person, the host account assignment, and every reading attached to the meeting. Copy-to-clipboard buttons are sprinkled everywhere something useful lives.

![Meetings list — table view with sort controls](./docs/screenshots/04-meetings-table.png)
*Placeholder: the meetings list in table view with the sort/direction controls visible.*

### Libraries: the readings your group actually uses

A **library** is a curated collection of readings, body text, and files. Meetings attach libraries — either the whole library or a granular selection of specific readings — so the readings you see on a meeting's page are exactly the ones that meeting uses that week.

As a viewer, you can open any library and browse its readings, see thumbnails, read inline body text, and download or share any attached file. As an editor, you can add, rename, reorder (drag-and-drop), and attach files from the central File Browser.

![Library view showing readings and thumbnails](./docs/screenshots/05-library.png)
*Placeholder: a library page with a few readings, thumbnails, and inline body text.*

### The File Browser — with real previews

Everything uploaded to the portal — images, PDFs, documents, videos — lives in the **File Browser**. Search by filename, sort by size or upload date, grid or table view.

The best part: click the filename of an **image or PDF** and it opens in a lightbox modal right on the page. No new tab, no download-then-open shuffle. Header has the filename, an Open-in-new-tab link, and a Download button. Escape closes it. Modifier-click still opens in a new tab if you want that.

![File Browser lightbox — PDF preview](./docs/screenshots/06-file-lightbox.png)
*Placeholder: the File Browser with the lightbox modal open, showing a PDF preview.*

Every file has a **Copy Link** button that gives you a clean, shareable, human-readable URL (`/pub/meeting-agenda.pdf`, not `/pub/4f8a...7e2c.pdf`). Paste it into a text, email, whatever — the recipient doesn't need to log in to read the file.

### Zoom Accounts and the weekly calendar

Zoom Accounts has its own sidebar entry now. Every shared Zoom host account is listed with its credentials (hidden by default, one-click reveal). Below the table, the **weekly calendar** shows every meeting slot assigned to every host, color-coded by account, with conflicts (two meetings on the same host at overlapping times) highlighted in red.

Each block shows the real occupancy window — from the opens time through the meeting end — so you see exactly when a host is in use, not just when the meeting officially starts.

Viewers see everything read-only. Editors see it read-only too (admins manage accounts), but the calendar is equally useful to everyone.

![Zoom Accounts calendar with hosts and slots](./docs/screenshots/07-zoom-calendar.png)
*Placeholder: the Zoom Accounts page with the weekly calendar below the accounts table.*

### Your role and capabilities are always visible

On the dashboard, a **Your Role and Server Stats** widget shows what you can do at a glance. Admin, editor, or viewer — there's a checkmarked list right there: "Create & edit meetings and libraries", "Upload & manage files", "View Zoom accounts (read-only)", and so on. If you've ever wondered whether a button is missing because you can't use it or because it doesn't exist, now you know.

### A guided tour the first time you log in

The first time a viewer or editor logs in, a friendly nine-step walkthrough lights up each part of the interface in turn — sidebar, dashboard, meetings, libraries, files, Zoom Accounts, settings, and help. It takes about a minute. You can skip it at any time, and it never fires again (stored in a browser cookie).

If you ever want to replay it, click the **?** (Help) button in the sidebar footer and hit **Take the tour**.

![Guided tour in action on the sidebar](./docs/screenshots/08-tour.png)
*Placeholder: the guided tour with its spotlight overlay highlighting a sidebar item.*

### Make it yours — themes, drag-and-drop dashboard

Open **Settings** (gear icon, bottom-left) and pick one of six themes: Light, Dark, Neobrutal Light, Neobrutal Dark, Cyberpunk, or Solarpunk. Your pick saves instantly. Not your vibe? Pick another. No "are you sure?" prompt.

On the dashboard, every widget is draggable — grab its handle and rearrange. Toggle widgets on and off from the Customize button up top. Your layout is per-account, so the admin's dashboard order doesn't push yours around.

![Theme picker with six swatches](./docs/screenshots/09-themes.png)
*Placeholder: the Appearance settings tab showing the six theme swatches.*

### Help, at the bottom of the sidebar, always

The **?** button in the sidebar footer opens a Help modal with two things: a **Take the tour** button (for replaying the walkthrough we mentioned), and contact info for the group's Public Information Chair (name, email, phone) if that's been filled in. That's it. No support forum to navigate, no FAQ to search.

## Why it matters

The portal used to be something you checked as a last resort because it was slow and you weren't sure the information was current. The new portal is something you keep a tab open on because it's fast, it's always current, and the thing you need is always two clicks away.

That's the point. A recovery fellowship doesn't need a fancy website. It needs its trusted servants and members to be able to find the right meeting, read the right material, host the right Zoom room, and reach the right person — **right now**, on a phone, on a laptop, on a tablet they borrowed.

That's what this is.

---

*Trusted Servants Pro is open source under the GNU AGPLv3. Self-host it, modify it, make it yours. Source: [github.com/viibeware/trusted-servants-pro](https://github.com/viibeware/trusted-servants-pro).*
