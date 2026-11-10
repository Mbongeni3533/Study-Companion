# Student Resources Centre

The standalone site behind the **Student Resources Centre** tab in Study Companion.
(`content/` rather than `data/`: the repository root ignores `data/` for the app's
runtime database.)
It is a Cloudflare Worker that serves one page plus the JSON the page fetches.

Live: <https://site-6beba36387f34076a1e817544bb2a4a5.freebuff.page/resources>
(reached from the app at `backend/static/app.js` → `RESOURCES_URL`).

## What is here

| Path | What it is |
| --- | --- |
| `page/resources.html` | The page markup: hero, tabs, and the thesis guide panel. |
| `public/static/resources/` | Served assets: `styles.css`, `app.js`, the thesis agent, favicon. |
| `public/static/resources/thesis-agent.js` | The thesis guide agent (see below). |
| `public/static/resources/thesis-agent.css` | Agent styling, built on the tokens in `styles.css`. |
| `content/*.json` | Scholarships, research routes, careers, jobs, library metadata, overview. |
| `content/library/*.md` | Document text served by the library tab. |
| `content/career-path.json` | Field × region × performance-band dataset behind "My career path". |
| `worker/index.js` | Router: page, `/api/resources/*`, library downloads, static assets. |
| `worker/career-path.js` | Composes the career-path response from the dataset. |
| `worker/{data,page,career-path-data}.js` | **Generated.** Do not edit by hand. |
| `scripts/build.py` | Regenerates those three modules from `content/` and `page/`. |
| `manifest.json` | Deployment manifest listing the worker modules and asset directory. |
| `wrangler.jsonc` | Local preview config (`wrangler dev`). |

## Editing content

Edit `content/*.json` (or the markdown in `content/library/`), then regenerate:

```bash
python3 resources-site/scripts/build.py
```

Edit page markup in `page/resources.html` and run the same script — the worker
serves the page from the generated `worker/page.js`, because the assets layer
rewrites `/resources.html` to `/resources` and serving it as an asset loops.

## Local preview

```bash
cd resources-site
wrangler dev --port 3004            # needs wrangler installed
```

Open <http://127.0.0.1:3004/resources>. Run **one** `wrangler dev` at a time per
state directory: two instances sharing `.wrangler/state` crash on `SQLITE_BUSY`.

## Deploying

```bash
# from the repository root, with the site id from Sites
# site: Student Resources Centre — b8e41f6a-3d7c-4b2a-8e91-5f0c6d2a9e47 (preview)
```

Deploy with `sites_deploy` using `resources-site/manifest.json`. The preview
environment is the one the app links to, so a deploy there publishes immediately.

## The thesis guide agent

`thesis-agent.js` is a self-contained agent; it makes no network calls and stores
progress in `localStorage`.

- **Ten stages**, each with a goal, the deliverable it should produce, a checklist
  and the mistakes that cost students time: scope → question → literature →
  review → method → proposal → data → findings → write-up → submit and defend.
- **A dated plan** built from the student's level, field, submission deadline and
  hours per week, allocating each stage a week range and a milestone date.
- **Answers** from a fixed knowledge base of ~21 entries (gaps, search strategy,
  sampling, ethics, thematic analysis, statistics, referencing, similarity, viva,
  publishing, and more). It says so plainly when a question is outside that.
- **Progress** per checklist item, restored on the next visit, with a "what should
  I do next" answer drawn from the first unfinished item.

Matching uses whole-word-start keyword scoring (`(^|[^a-z])key`), so "search" does
not fire on "research" while "snowball" still matches "snowballing". When adding
an entry, give it the phrases a student would actually type, and check that the
stage's own suggestion chips resolve to it.
