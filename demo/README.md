# TSP Pro — Interactive Demo

This directory contains everything needed to run the **public, interactive demo**
of TSP Pro: a marketing homepage that sells the product, plus a fully-loaded,
fully-editable instance of the app whose changes **reset per visitor**.

## What the demo is

When `TSP_DEMO_MODE=1` is set, the app behaves differently in three ways:

1. **A product marketing page** is served at `/` (the front door). It pitches
   TSP Pro and links into the live demo, which lives at **`/demo`**.
2. **Per-session isolation.** Every browser session gets its own private copy of
   the SQLite database and uploads, lazily copied from a read-only *golden* seed.
   A visitor can edit meetings, rewrite pages, flip modules, upload files, sign
   into the admin — and none of it persists or affects anyone else. Idle sessions
   are swept automatically (default 90 min), so everyone starts fresh.
3. **A seeded fellowship.** The golden DB is populated with a fictitious
   fellowship, **Meridian Recovery Collective** — meetings across time zones,
   literature libraries, events, announcements, recovery stories, a blog, a
   fellowships index, trusted servants, and content pages — so the demo looks
   real out of the box.

Nothing about production behaviour changes when `TSP_DEMO_MODE` is unset.

## Run it locally (Docker)

```bash
bash demo/run-demo.sh
```

Then open:

| Surface        | URL                                       |
| -------------- | ----------------------------------------- |
| Product page   | http://localhost:8090/                    |
| Live demo      | http://localhost:8090/demo                |
| Admin backend  | http://localhost:8090/demo/login-admin    |

Demo logins: **admin / admin**, **editor / editor**, **viewer / viewer**
(the banner also offers one-click admin sign-in).

Useful commands:

```bash
docker compose -f docker-compose.demo.yml logs -f     # follow logs
docker compose -f docker-compose.demo.yml down        # stop
docker compose -f docker-compose.demo.yml down -v     # stop + wipe golden seed (re-seeds on next boot)
```

## How visitors move through it

- A new visitor lands on the **product marketing page** at `/`.
- "Explore the live demo" takes them to `/demo` — the live fellowship site,
  where their private session is provisioned on first hit.
- "Open the admin backend" signs them in as the demo admin and opens `/tspro`.
- A slim banner on every app page offers **Demo home** (`/demo`), **Reset demo**
  (wipe their session), and **About TSP Pro** (back to the product page at `/`).

## Deploying the demo to a server

The demo is the same single container as a normal install — just with
`TSP_DEMO_MODE=1`. On any Docker host:

```bash
echo "TSP_SECRET_KEY=$(openssl rand -hex 32)" > .env
docker compose -f docker-compose.demo.yml up -d --build
```

Notes for a public/HTTPS host (Fly.io, Render, a VPS behind Caddy/nginx, etc.):

- Put a TLS terminator in front and forward to container port `8000`.
- When serving over **HTTPS**, drop `TSP_DEBUG=1` from the compose env so secure
  cookies are used; keep `TSP_ADMIN_PASSWORD=admin` so the demo creds still work.
  (`TSP_DEBUG=1` is only there to make cookies work over plain `http://localhost`.)
- The `/data` volume holds the golden seed plus per-session copies. Backing it
  with ephemeral storage (or periodically `down -v`) keeps the demo tidy.
- Tune `TSP_DEMO_SESSION_TTL_MIN` to control how long idle visitor sessions live.

## Files

| File                       | Purpose                                                        |
| -------------------------- | ------------------------------------------------------------- |
| `docker-compose.demo.yml`  | Demo compose file (sets `TSP_DEMO_MODE=1`).                    |
| `demo/run-demo.sh`         | One-command build + launch.                                   |
| `app/demo.py`              | Per-session DB + uploads isolation engine.                   |
| `app/demo_seed.py`         | Seeds the Meridian Recovery Collective golden dataset.        |
| `app/product.py`           | Product marketing blueprint + demo entry/reset routes.        |
| `app/templates/product/`   | Landing page + the per-page demo banner.                      |
| `app/static/css/product.css` / `js/product.js` | Marketing page styles + interactions.     |
