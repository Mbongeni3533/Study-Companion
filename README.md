# Study Companion

An AI study companion that turns a student's **own course material** into a topic
map, a realistic study plan and a hint-first coach. It works with the lectures,
slides and notes a student already has — no spoon-feeding, no invented content.

The whole product runs with **zero external services**: without an AI key the
coach falls back to a deterministic engine (retrieval, fill-in-the-blank quizzes,
graduated hints, plan generation). Add `ANTHROPIC_API_KEY` to upgrade the coach
and plan quality.

## What it does

1. **Upload material** — PDF, DOCX, PPTX, TXT, Markdown, CSV, HTML or pasted notes.
   Scanned (image-only) PDFs and photos are read with OCR when no text layer is
   found, so a photocopied handout still produces topics (see *OCR* below).
2. **Topic mapping** — headings first, keyword clustering second; each topic gets
   a summary, key terms, difficulty (1–5) and a share of the course.
3. **Study plan** — tasks (read / practice / quiz / review) spread across days
   around a daily minute budget, with per-topic links.
4. **Coach** — grounded in retrieved passages. Three hint levels: nudge, clue,
   full walkthrough. Quizzes and flashcards are generated from the material.
5. **Progress** — minutes studied, streaks, per-topic mastery and an exam
   readiness score driven by topic coverage × completed tasks.
6. **Student Resources Centre** — a section of the app (sidebar → *Resources*,
   also on the dashboard) with scholarships, research placements, career
   guidance and job boards, a career-path view narrowed to your field and
   country, a document library, and a thesis-writing agent. Content ships with
   the app as JSON, so it needs no key, no database and no second website.

## Project structure

```
study-companion-app/
├── backend/
│   ├── main.py                     # FastAPI app, static client, /health
│   ├── requirements.txt
│   ├── start.sh                    # dev server (reload)
│   ├── static/                     # bundled study client (no build step)
│   │   ├── index.html
│   │   ├── app.js                  # shell, routes, dashboard, course views
│   │   ├── styles.css
│   │   ├── resources.js            # Student Resources Centre view
│   │   ├── resources.css           # its styles, scoped to .rc-scope
│   │   ├── thesis-agent.js         # thesis-writing guide (client-side)
│   │   └── thesis-agent.css
│   └── app/
│       ├── content/resources/      # resources JSON + library markdown
│       │                           # (edit here; no build step)
│       ├── config.py               # settings from env / .env
│       ├── database.py             # SQLAlchemy engine + session
│       ├── models.py               # User, Course, Document, Chunk, Topic,
│       │                           # Task, ChatSession, Message, StudyLog
│       ├── schemas.py              # Pydantic request/response contract
│       ├── serializers.py          # readiness score, streaks, response builders
│       ├── routes/
│       │   ├── auth.py             # register / login / anonymous session
│       │   ├── documents.py        # courses, uploads, topics, search
│       │   ├── tasks.py            # plan generation and task tracking
│       │   ├── chat.py             # coach conversations
│       │   ├── progress.py         # minutes, streaks, readiness
│       │   └── resources.py        # /api/resources/* (static content)
│       ├── services/
│       │   ├── document_processor.py   # extraction + chunking
│       │   ├── topic_extractor.py      # topic map builder
│       │   ├── topic_service.py        # persistence of the topic map
│       │   ├── ai_provider.py          # optional coach provider (via local gateway)
│       │   ├── ai_coach.py             # rules engine + AI coach
│       │   └── payment_service.py      # billing hooks (phase 3)
│       └── utils/                  # auth, dependencies, text/retrieval
├── test_api.py                     # import + model smoke test
├── Dockerfile / Dockerfile.prod
├── docker-compose.yml
└── .env.example
```

## Quick start

```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
./start.sh            # http://localhost:8000
```

Copy `.env.example` to `.env` first if you want to set a JWT secret, a database
URL or an AI key. SQLite is created automatically at `backend/data/`.

Then open <http://localhost:8000> and either create an account or continue as a
guest. Interactive API docs: <http://localhost:8000/api/docs>.

## AI gateway

Coach model calls go through the open-source
[Respan Gateway](https://github.com/respanai/respan-gateway?utm_source=freebuff&utm_medium=paid&utm_campaign=respan-gateway&bfcid=bfc_1.eyJpZCI6Ijk1YWI1OTY3LTY1NDEtNGMwMS04MGU2LTllYjE5NzgxNjg1ZCIsImMiOiIyMDM2ODZkZS1mMzg0LTQ4NTQtYmViNC1hYzBiYWRmNmM1NTUiLCJrIjoiM2IxMGE4YmUtNzgyOS00MmJhLWFmNmEtYmI0YWUxZTRhY2Y4IiwiaWF0IjoxNzk0Mjg1MjY4fQ.vpa-nju8AiV6A5swLesChLIIA_fO7CBNW0pDqT9KaEM),
running in-process (`respan_gateway`, declared in `backend/requirements.txt`). There
is no server to start: `backend/app/services/ai_provider.py` opens a gateway per
model call and sends the Anthropic Messages request through its httpx transport.

- The coach asks for the `study-coach` route; the gateway resolves it to
  `ANTHROPIC_MODEL` (default `claude-sonnet-4-5`) with two tries.
- The provider key stays in the gateway config, read from `ANTHROPIC_API_KEY` in
  the ignored `.env` — it is not sent from the client, logged, or committed.
- `ANTHROPIC_BASE_URL` (optional) points the gateway at another endpoint, such as
  a local fixture or an already-authorized proxy. Empty means `api.anthropic.com`.
- Without a key the coach still answers with its rule engine, unchanged.

`python test_api.py` includes an offline check of that path: a local fixture
stands in for the provider and the check drives coach → provider → gateway → route
→ fixture. Observed output:

```text
✓ Gateway routing: route study-coach -> claude-sonnet-4-5 at the fixture, ['Osmosis']
```

A live Anthropic request was **not** verified here (no provider key in this
environment); with a real `ANTHROPIC_API_KEY` the normal app run below exercises
the same path against the real provider.

Run the app as usual:

```bash
cd backend && ./start.sh            # http://localhost:8000
```

## Deploy to Fly.io

The repository ships a `fly.toml` that runs the app from its `Dockerfile` on a
single machine with a 1 GB volume mounted at `/app/data`, so the SQLite database
and uploads survive restarts and redeploys.

```bash
curl -L https://fly.io/install.sh | sh   # install flyctl, then reopen the shell
fly auth signup                          # or: fly auth login

# App names are globally unique: if `study-companion` is taken, create another
# name and put that same name on the `app` line of fly.toml.
fly apps create study-companion
fly volumes create study_data --size 1 --region jnb

fly secrets set JWT_SECRET="$(openssl rand -hex 32)"
# Optional: switch the coach from the rules engine to the AI provider.
# fly secrets set ANTHROPIC_API_KEY=sk-ant-...

fly deploy
```

The first `fly deploy` builds the image (installing tesseract and the Python
dependencies), and prints the app's permanent `https://<name>.fly.dev` URL.

**Cost.** Fly has no free tier, but a personal organization's monthly bill under
$5 is waived, so this stays at $0 as long as usage stays small. The config stops
the machine when idle and wakes it on the next request, which keeps usage well
under the threshold; a 1 GB volume is $0.15/month of provisioned storage. A card
must be on file for the waiver to apply, and a bill of $5 or more is charged in
full with no partial credit.

**If uploads fail with `permission denied`,** Fly normally sets the volume's
ownership to the image's `appuser`, but you can fix it by hand once:

```bash
fly ssh console -C "chown -R appuser:appuser /app/data"
```

## Demo in 30 seconds

1. **New course** → e.g. "Cell Biology", exam date in a few weeks.
2. **Add material** → paste a few paragraphs of notes (or upload a lecture PDF).
3. **Generate plan** → 8 tasks across your week.
4. **Coach** → "quiz me on …" with the hint level set to *Nudge*.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Log in |
| `POST` | `/auth/anonymous-session` | Start as a guest |
| `GET` `PATCH` | `/auth/me` | Read / update profile and study goal |
| `POST` | `/documents/courses` | Create a course |
| `GET` | `/documents/courses` | List courses with counts and readiness |
| `GET` `PATCH` `DELETE` | `/documents/courses/{id}` | Course detail |
| `POST` | `/documents/courses/{id}/documents` | Upload a file (multipart) - returns a `processing` document |
| `GET` | `/documents/courses/{id}/documents/{doc_id}` | Document status + live progress (`progress_stage`, `progress_current`, `progress_total`) |
| `POST` | `/documents/courses/{id}/documents/paste` | Ingest pasted notes |
| `GET` | `/documents/courses/{id}/documents` | List documents |
| `GET` | `/documents/courses/{id}/documents/{doc_id}/chunks` | Read extracted passages |
| `DELETE` | `/documents/courses/{id}/documents/{doc_id}` | Delete a document |
| `GET` | `/documents/courses/{id}/topics` | Topic map |
| `POST` | `/documents/courses/{id}/topics/rebuild` | Recompute topics |
| `GET` | `/documents/courses/{id}/search?q=` | Passage search |
| `POST` | `/tasks/courses/{id}/generate` | Generate a study plan |
| `GET` | `/tasks/courses/{id}` | List course tasks |
| `GET` | `/tasks/today` | Tasks due today (or upcoming) |
| `PATCH` `DELETE` | `/tasks/{task_id}` | Update / remove a task |
| `POST` | `/chat/courses/{id}/sessions` | Start a coach conversation |
| `GET` | `/chat/courses/{id}/sessions` | List conversations |
| `GET` | `/chat/sessions/{session_id}` | Conversation with messages |
| `POST` | `/chat/sessions/{session_id}/messages` | Ask the coach |
| `GET` | `/progress/summary` | Dashboard aggregates |
| `GET` | `/progress/courses/{id}` | Per-course readiness and mastery |
| `POST` | `/progress/log` | Log study minutes manually |
| `GET` | `/resources/{section}` | Resources content: overview, scholarships, research, career, employment, library |
| `GET` | `/resources/career-path?field=&region=&performance=` | Field + locations + results band, composed from the stored dataset |
| `GET` | `/resources/library/{slug}` | One library document, rendered client-side |
| `GET` | `/resources/library/{slug}/download` | The same document as `text/markdown` |
| `GET` | `/health` | Liveness + configuration |

Auth is a bearer JWT (`Authorization: Bearer <token>`). The `/resources/*` routes
are public: they serve the same content to every student and hold no personal
data.

## How the pieces work

**Extraction & chunking** — parsers are optional imports, so a missing dependency
degrades to a clear per-document warning instead of a 500. Text is normalised,
split at headings, and packed into ~180-word overlapping chunks with the heading
carried along for citation.

**Topic mapping** — if at least half the chunks carry headings, sections become
topics. Otherwise chunks are clustered around their strongest shared keywords.
Difficulty comes from sentence length and rare-word density; weights are
normalised so the map shows what the course is mostly about.

**Coach** — retrieval ranks chunks against the question with a TF-IDF-style
score, then either calls Anthropic with those excerpts or runs the rule engine:
intent detection (explain / quiz / flashcards / summary / plan / hint) plus a
graduated hint level. It quotes the student's material and asks for a restatement
rather than producing an essay.

**Readiness** — `55% × topic coverage + 45% × completed tasks`, where a topic
counts as covered once a task linked to it is completed.

## Development

```bash
cd backend
../.venv/bin/python ../test_api.py          # import/model smoke test
../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

`DATABASE_URL` may point at PostgreSQL; SQLite is used otherwise. Uploads live in
`backend/data/uploads`. Set `DATA_DIR` to move both.

## Status

- [x] Auth: accounts, login, anonymous sessions, profile + study goal
- [x] Courses, uploads, extraction (PDF/DOCX/PPTX/text/HTML), chunking
- [x] OCR fallback for scanned PDFs and image uploads (`OCR_ENABLED`, `OCR_MAX_PAGES`)
- [x] Topic mapping with difficulty, keywords and weights
- [x] Plan generation and task tracking with study logs
- [x] Coach: retrieval, graduated hints, quizzes, flashcards, summaries
- [x] Progress: minutes, streaks, per-topic mastery, exam readiness
- [x] Bundled responsive web client
- [ ] Expo mobile client
- [ ] Spaced-repetition scheduling for reviews
- [ ] Payments and institution licensing
- [ ] Offline mode

## License

This project is proprietary. All rights reserved.
