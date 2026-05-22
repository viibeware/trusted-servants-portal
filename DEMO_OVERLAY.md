# Demo overlay (the `demo` branch)

This branch is **`main` + a thin demo overlay**. It exists only on the `demo`
branch — `main` stays clean. Keep it in sync by merging `main` in:

```bash
cd /home/jason/tspro-demo      # the demo worktree (branch: demo)
git fetch
git merge main                 # pull every main change into the demo
```

Because the overlay is almost entirely **new files**, merges are usually
conflict-free. The only files shared with `main` are a handful of small,
clearly-marked edits (see below); a conflict can only happen if `main` changes
those exact lines.

## Demo-only files (pure additions — never on `main`)

```
app/demo.py                              per-session DB + uploads isolation engine
app/demo_seed.py                         seeds the demo fellowship (Meridian Recovery Collective)
app/product.py                           product marketing blueprint + demo entry routes
app/templates/product/landing.html       the marketing homepage
app/templates/product/_demo_banner.html  the per-page demo banner
app/static/css/product.css               marketing page styles (light + dark)
app/static/js/product.js                 marketing page interactions + theme toggle
app/static/img/product/*.png             real screenshots of the live demo (see regen below)
docker-compose.demo.yml                  demo deployment (sets TSP_DEMO_MODE=1)
demo/run-demo.sh                         one-command launch
demo/screenshots.js                      regenerates the marketing screenshots (puppeteer)
demo/README.md                           demo deployment docs
DEMO_OVERLAY.md                          this file
```

The marketing page uses the existing TS Pro logos (`app/static/img/logo_tspro_white.svg`
for dark, `logo_tspro_about.svg` for light) — those already ship on `main`, so they're
not part of the overlay.

### Regenerating the marketing screenshots

The screenshots in `app/static/img/product/` are captured from the running demo with a
headless browser. To refresh them after a UI change:

```bash
# with the demo running (e.g. on :8095):
docker run --rm --network host -w /home/pptruser \
  -e NODE_PATH=/home/pptruser/node_modules \
  -v "$PWD/demo/screenshots.js":/shot.js:ro \
  -v "$PWD/app/static/img/product":/out \
  ghcr.io/puppeteer/puppeteer:latest node /shot.js
```

Edit the `BASE` URL / shot list in `demo/screenshots.js` if your port differs.

## Shared files with overlay edits (the only merge friction)

Every edit is wrapped in `>>> TSP demo overlay … <<<` (or `{# TSP demo overlay #}`)
markers and is a **no-op on a normal install**, so they're safe and easy to spot.

| File | Edit | Why it's harmless on `main` |
|------|------|-----------------------------|
| `app/__init__.py` | 4 blocks behind `if demo_mode` (engine config, install/register, seed + analytics-refresh call, skip backups) | All gated on `TSP_DEMO_MODE`; off by default |
| `app/templates/base.html` | `{% include 'product/_demo_banner.html' ignore missing %}` | `ignore missing` → renders nothing without the partial |
| `app/templates/frontend/base.html` | same include | same |
| `app/templates/frontend/headers/classic.html` | `href="{{ home_url or url_for('frontend.index') }}"` | `home_url` is unset off-demo → falls back to `url_for` |
| `app/templates/frontend/headers/recovery-blue.html` | same | same |
| `app/static/css/frontend.css` | appended `.fe-pp .fe-hero` full-bleed rule (+ `overflow-x: clip`) so page-builder heroes span full width | Additive rule at EOF; only affects page-builder hero blocks |

## The bugfix

The first commit on this branch (`Fix file_type filter NameError…`) is **not
demo-specific** — it's a real bug in `app/__init__.py`'s `file_type` filter that
500s the public `/library` page for extensionless items. **Cherry-pick it onto
`main`:**

```bash
git switch main
git cherry-pick <sha-of-that-commit>   # `git log demo --oneline | grep file_type`
git switch -    # back to demo
```

After that, the demo branch and main share the fix and it won't show as a diff.

## Running the demo

```bash
cd /home/jason/tspro-demo
bash demo/run-demo.sh           # → http://localhost:8090  (product page; /demo = live demo)
```

`TSP_DEMO_MODE` is the only switch. With it off, this tree behaves exactly like `main`.
