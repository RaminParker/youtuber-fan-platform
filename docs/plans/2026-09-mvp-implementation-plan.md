# MVP Implementation Plan — Creator Platform (Phase 0 + Phase 1)

> **Progress:** M0–M4 built, tested and reviewed (2026-09-11); M5–M9 not started. Per-milestone detail in §17.
>
> **Status:** draft for review · **Date:** 2026-09-10, revised 2026-09-11 after a full review against the manifest (14 findings; the changed passages are marked "§R" in `implementation-notes.html`) · **Source of truth:** `docs/manifest/creator-plattform-manifest.md` (the manifest). Every task below cites the manifest section it implements. What is not in the manifest is not built.
>
> **Scope:** the MVP as defined in manifest §6 (Phase 1), reached through the Phase 0 demo (manifest §10). Product 2 (briefings), the podcast connector, Whisper, payments, fan login and dashboards are explicitly out of scope.
>
> **Decisions taken with the owner on 2026-09-09/10** (not in the manifest yet; to be copied into manifest §13):
> - E-mail provider: **Resend**. Hosting: **Render** (Blueprint `render.yaml`).
> - **No Whisper in the MVP.** Two transcript implementations only (official OAuth captions, unofficial `youtube-transcript-api`). Videos without captions are skipped and the creator is notified. Whisper arrives with the podcast connector in Phase 2 (manifest §7.4 step 3 is Phase 2).
> - **Upload trigger: feed poll only** (every 6 hours). PubSubHubbub push (manifest §7.3) is deferred until after go-live: with a 48-hour minimum delay it shortens nothing a creator or fan can observe, and the hub proved unreliable during research (§18). It is purely additive later.
> - **No job-queue library.** The pipeline is a status machine in the database; one worker process runs due steps in a loop (manifest §7.8 lists procrastinate as a recommendation, not a decision; reasoning in §9 and `docs/ARCHITECTURE.md`).
> - **Summarisation is one LLM call** up to a configured transcript length; hierarchical map-reduce (manifest §7.5) is deferred until a real video exceeds the ceiling.
> - **E-mail variants are template-only.** One summary prompt always fills every `Summary` field; the templates decide what each variant shows. Manifest §7.6's per-variant prompt parameter is dropped so that a variant switch applies instantly to open mailings and summary pages without re-summarising, and demo mails can show all three variants from one analysis. Two limits, both in §8.4: a mailing whose preview has already gone out keeps the variant it was previewed with (payload freeze), and the `/s/` page always renders the full text regardless of the variant (manifest §7.6 "Teaser mit Volltext online").
> - **Only the worker runs pipeline steps.** The CLI ingests and reports; it never executes a step (a second runner would repeat expensive steps on the same row).
> - **Welcome link:** the confirm mail (= welcome mail) carries no link to the newest summary because summary pages must not reach unverified addresses; the page shown after confirmation carries it instead (manifest §6.1 wording differs).
> - **Unsubscribe is per creator** (token on the subscription), as the multi-creator data model in manifest §7.7 implies; a global "alle abbestellen" comes with the fan dashboard.
> - Language: all code, docstrings, comments, logs and technical docs in **English**; only `README.md` in German. User-facing texts (pages, mails) in German (manifest §3.4).
> - HTMX is included from the start (manifest §7.8). Feature voting on the landing page (§5.6) and logo upload are deferred; the logo is a URL (default: the YouTube channel avatar).
> - Documents live in `docs/`: plans in `docs/plans/`, concept documents in `docs/manifest/`.

---

## Table of contents

0. [Big picture — read this first](#0-big-picture--read-this-first)
1. [Problem and goal](#1-problem-and-goal)
2. [Acceptance criteria](#2-acceptance-criteria)
3. [Guiding principles for the code](#3-guiding-principles-for-the-code)
4. [Technology stack (final)](#4-technology-stack-final)
5. [Repository layout](#5-repository-layout)
6. [Configuration](#6-configuration)
7. [Data model](#7-data-model)
8. [Module design](#8-module-design)
9. [The pipeline: states, steps, worker](#9-the-pipeline-states-steps-worker)
10. [Web surface: routes and pages](#10-web-surface-routes-and-pages)
11. [E-mail: variants, framing, deliverability](#11-e-mail-variants-framing-deliverability)
12. [Logging, observability, cost control](#12-logging-observability-cost-control)
13. [Security and data protection](#13-security-and-data-protection)
14. [Testing strategy](#14-testing-strategy)
15. [Local development and deployment](#15-local-development-and-deployment)
16. [Documentation deliverables](#16-documentation-deliverables)
17. [Implementation steps (milestones)](#17-implementation-steps-milestones)
18. [Verified technical facts the plan relies on](#18-verified-technical-facts-the-plan-relies-on)
19. [Risks](#19-risks)
20. [Open questions](#20-open-questions)
21. [Review section](#21-review-section)

---

## 0. Big picture — read this first

**What we are building.** A service for YouTube creators. Fans of a creator enter their e-mail address on a small branded page. A few days after every new video, each fan receives one e-mail: a short, sober summary of what was said, with jump links into the video, one strong quote, and a picture of how the community reacted in the comments. The creator pays for it, does nothing after onboarding, and keeps full control through a preview mail with a "stop" link an hour before every send. Fans pay nothing and can leave with one click.

**Why it exists.** Creators cannot reach their audience outside the platform's algorithm and have no time to write newsletters. This service builds them an e-mail list and fills it automatically. The technical core — turn a public talk into a transcript, then into structured analysis, then into an output — is the same foundation that later carries podcasts and interview briefings; the MVP builds that core once, cleanly, for one creator on one source.

**What happens end to end.** The worker asks YouTube's public feed every six hours whether the pilot channel has a new video. A new video becomes an *appearance* row. The pipeline moves that row through a handful of states: fetch its metadata (skip shorts), fetch the transcript (official captions if the creator has connected YouTube, otherwise the unofficial caption library), ask the LLM for a structured summary, and schedule a *mailing* for publish date plus the creator's delay (default seven days, never less than 48 hours). Two hours before send time the worker fetches the top comments and asks the LLM for a sentiment picture. One hour before, the creator gets the exact mail with stop and postpone links. At send time the mail goes out to every confirmed subscriber, in batches, exactly once. Every step is a plain function that reads its row, does one thing, writes the new state — a crash anywhere resumes at the next loop.

**What the developer builds.** One Python repository, one deployment: a FastAPI web process (sign-up, confirmation, unsubscribe, the "online ansehen" page, the creator's settings page, the landing page, one webhook for bounces) and one worker process (the pipeline loop). PostgreSQL holds everything, including pipeline state. Two small abstractions keep later phases cheap: a source/transcript interface and an LLM gateway client. External services do the heavy lifting: YouTube's Data API, an LLM behind the Bifrost gateway, Resend for e-mail, Render for hosting. No queue framework, no frontend build, no admin UI — the operator uses a CLI and the logs.

**What is deliberately not built.** Podcasts, briefings for interviewers, Whisper transcription, payments, fan login and dashboards, push notifications from YouTube, multi-tenant self-service. All of them are additive later; none of them is needed to earn the first euro.

**How to read the rest.** §2 says when we are done. §3–§4 are the rules and the stack. §5–§8 describe the code you will write. §9 is the heart: the state machines and the worker. §10–§11 are the pages and the mails. §12–§16 are logging, security, tests, deployment and docs. §17 is the order of work, in ten milestones that each ship something. §18–§20 are the verified facts, the risks and the questions still open.

## 1. Problem and goal

Build the smallest platform that earns money (manifest §0, §6): one pilot creator on YouTube, whose fans sign up with an e-mail address and receive, a few days after each new video, an automatically generated summary plus a sentiment picture of the comments. The creator gets a preview with a stop window before each send, a settings page via magic link, and a CSV export of his list. A landing page sells the service to further creators.

Technically (manifest §7): a **modular monolith** in Python with one shared pipeline — *source → transcript → analysis → output* — cut cleanly enough that Phase 2 (podcast connector, briefings, multi-tenant self-service) adds files instead of rewriting them. Exactly two deliberate abstractions from day one: the **source/transcript interface** and the **LLM gateway** (manifest §7.1).

## 2. Acceptance criteria

Technical definition of done for the MVP (each milestone in §17 has its own, narrower criteria):

- [x] `uv run pytest` is green and `uv run ruff check` / `uv run ruff format --check` report nothing.
- [ ] `docker compose up` starts web, worker, Postgres and the LLM gateway locally; `git push` deploys to Render without manual steps (manifest §7.1 "one command to deploy").
- [ ] A new public upload on the pilot channel is detected by the feed poll, transcribed, summarised, scheduled, sentiment-enriched, previewed to the creator with a full stop window, and sent to all confirmed subscribers **exactly once**, without any manual step (manifest §1.5, §7.9).
- [ ] Every mail carries the two "fingerprints" (creator header, platform footer with the "automatisch erstellt" notice), an unsubscribe link, `List-Unsubscribe` headers and an "online ansehen" link; the online page carries the same notice (manifest §3.1, §7.6).
- [ ] Bounces and complaints reported by Resend deactivate the affected subscriber automatically (manifest §6.1).
- [ ] The creator can change delay, minimum length, variant, greeting/farewell, logo URL, accent colour and reply-to on the settings page; a changed delay reschedules unsent mailings (manifest §5.1 C, §7.6).
- [ ] The creator can export confirmed subscribers as CSV (e-mail + confirmation date only) (manifest §7.9).
- [x] All tunables listed in manifest §7.1 live in one `config/settings.toml`; secrets only in environment variables; per-creator values in the database override the file defaults.
- [ ] Structured logs make every pipeline step traceable by `appearance_id` / `mailing_id`, including LLM tokens and cost per call and YouTube quota units per call (§12).
- [x] `README.md` (German) lets a new developer run the project locally in under 15 minutes; `docs/ARCHITECTURE.md` explains the module cut, the state machines and the decisions.

Three of these hold as of 2026-09-11. The rest wait on milestones that are not built (the end-to-end
send on M6, bounce handling on M5, the settings page and the CSV export on M7) or on an environment
that does not exist yet (Render, the domain, the API keys) — see the Status lines in §17.

Business criteria (manifest §6.3) are tracked by the owner, not by this plan: a paying creator, measurable list growth, open rates above newsletter average, a spontaneous recommendation.

## 3. Guiding principles for the code

Taken from the project's code-style rules and manifest §7.1; listed here because they decide many small choices below.

- **One responsibility per module and function.** Small functions, early returns, descriptive names, `handle_*` for request/webhook handlers.
- **No abstraction without a second implementation** — except the two the manifest names: the source/transcript interface (`SourceConnector`, `TranscriptProvider`) and the LLM gateway (`LLMGateway`). Everything else, including the e-mail client and the YouTube API client, is a plain class; test fakes duck-type it, no Protocol needed.
- **Single source of truth.** Tunables in `settings.toml`, per-creator values in the DB, the product name in exactly one place (`settings.product.name`), status vocabularies as `StrEnum`s next to their tables, prompts and e-mail variants as files, log event names as constants.
- **Deletion over addition, boring over clever.** Stdlib first (`xml.etree`, `hmac`, `secrets`, `argparse`, `csv`, `tomllib`), then already-installed libraries, then new dependencies. Values that never change are module constants next to their single use, not configuration.
- **Deliberate shortcuts are marked** with a `# ponytail:` comment naming the ceiling and the upgrade path (manifest §7.1 "bewusste Abkürzungen werden im Code als solche markiert").
- **numpy-style docstrings** on public functions; comments explain *why*, never *what*; architecture reasoning goes to `docs/ARCHITECTURE.md`, never into comment blocks.
- **Idempotent by construction.** Every step re-checks the database state before acting; unique constraints, conditional status updates (§8.4) and one advisory lock, not application logic, guarantee "exactly once".
- **Logs are part of the feature.** A step without a log line at start and end is unfinished (§12).
- **Tests use fakes, not mocks.** External services are swapped through one documented seam (§8.6); nothing else is patched (§14).

## 4. Technology stack (final)

All versions verified on 2026-09-09/10 (see §18). Pin exact versions in `pyproject.toml` (`sqlalchemy<2.1`, FastAPI and Starlette pinned too); `uv.lock` is committed.

| Concern | Choice | Notes / deviation from manifest §7.8 |
|---|---|---|
| Language | Python **3.13** (`.python-version`), **uv** | 3.14 is Render's default but `youtube-transcript-api` pins `<3.15` and several libs only just added 3.14; 3.13 is the safe choice. |
| Web | **FastAPI** + **uvicorn** | Sync `def` endpoints with sync SQLAlchemy (documented, threadpool-backed). |
| Templates | **Jinja2** (pages and mails, one environment) + **HTMX** (vendored single file in `static/`) + handwritten CSS (Pico.css classless as base) | No build step. |
| DB | **PostgreSQL 17**, **SQLAlchemy 2** (sync, `postgresql+psycopg://`), **psycopg 3** (`psycopg[binary]`), **Alembic** | One DB for data, pipeline state and periodic-job bookkeeping. |
| Jobs | **No queue library.** `app/worker.py`: a loop that runs due pipeline steps and periodic jobs (§9). Worker is a separate process, as the manifest's "web process + worker process" prescribes. | Deviation from §7.8 (procrastinate): the state already lives in `appearances.status` / `mailings.status`; a queue would duplicate it and add four tables, a connector and LISTEN/NOTIFY semantics. |
| Config | **pydantic-settings** with `TomlConfigSettingsSource` + env | Priority: env > `.env` > `settings.toml` > defaults. |
| HTTP | **httpx** | YouTube Data API and captions, Google OAuth token endpoint, Resend, the LLM gateway. |
| YouTube | **httpx against the Data API REST endpoints** (API key; captions endpoints with the creator's OAuth token); **httpx against Google's OAuth endpoints** (authorize URL, code exchange, refresh); **youtube-transcript-api 1.2.4** (unofficial captions) | Deviation: `google-api-python-client`, `google-auth` and `google-auth-oauthlib` are not needed — four GET endpoints, one download and two token POSTs are simpler as plain httpx calls, and it removes about ten transitive packages. |
| LLM | **Bifrost** (`maximhq/bifrost:v2.1.1`, Docker) as gateway; the app speaks the OpenAI-compatible `/v1/chat/completions` with `provider/model` names and `response_format: json_schema` | Manifest §8. The app never imports a provider SDK. The gateway URL is one env value; without Bifrost the same client can point at any OpenAI-compatible endpoint. |
| E-mail | **Resend** via httpx (`/emails`, `/emails/batch`, webhooks) | Deviation: the `resend` SDK is not needed; two endpoints and a 15-line signature check. |
| CSS inlining | **css_inline** | Deviation: `premailer` has had no release since 2021; `css_inline` is maintained and 10× faster. |
| Rate limits | **slowapi** (in-memory storage) | Sign-up, magic-link request, contact form. Single web process in the MVP. Do not install the `[redis]` extra (obsolete pin). |
| Tokens/crypto | **itsdangerous** (signed session cookie via Starlette `SessionMiddleware`), **cryptography** Fernet/MultiFernet (OAuth refresh tokens at rest), `secrets` (URL tokens, OAuth state) | |
| Logging | **structlog** (JSON or console by setting, optional rotating file), **sentry-sdk** (optional, DSN from env) | |
| Quality | **pytest**, **ruff** (lint + format), GitHub Actions | |
| Hosting | **Render** Blueprint: web and worker from the **same Dockerfile** (`runtime: docker`, `0.5c-512mb` each), private service Bifrost (`runtime: image`), Postgres (`0.1c-256mb`, PG 17) | ≈ $27/month. Free tiers are unsuitable (free Postgres expires after 30 days; workers have no free tier; `preDeployCommand` needs a paid plan). |

Not used in the MVP, on purpose: async SQLAlchemy, Redis, procrastinate, feedparser (Phase 2, podcast), PyYAML (roadmap file is TOML, stdlib), Stripe (Phase 2), pgvector (Phase 3), Whisper (Phase 2), any DI or plugin framework.

## 5. Repository layout

Snapshot at planning time; after M0 `docs/ARCHITECTURE.md` is the authority for the layout.

```
youtuber-fan-platform/
├── README.md                     German. What this is, how to run it, where things are.
├── pyproject.toml                Project, dependencies, ruff + pytest config.
├── uv.lock
├── .python-version               3.13
├── .env.example                  Every secret/env var with a comment, no values. Authority for env vars.
├── .gitignore
├── Dockerfile                    THE build: one image for web and worker (uv sync --locked --no-dev), used locally and on Render.
├── docker-compose.yml            postgres, bifrost, web, worker.
├── render.yaml                   Render Blueprint (web, worker, bifrost, postgres).
├── alembic.ini
├── config/
│   ├── settings.toml             THE configuration file (manifest §7.1). Authority for tunables (commented).
│   ├── bifrost.json              Gateway config; provider key via env.ANTHROPIC_API_KEY, virtual key via env.LLM_GATEWAY_KEY; file-only mode.
│   └── roadmap.toml              Feature preview cards (manifest §5.6); read with stdlib tomllib.
├── migrations/                   Alembic environment and versions.
├── src/app/                      The application package (neutral name; the product name lives in settings only).
│   ├── __init__.py
│   ├── config.py                 Settings model, derived values, `get_settings()`.
│   ├── errors.py                 `TemporaryError` base class — the retry signal for §9.4; layer modules subclass it.
│   ├── log.py                    structlog setup, context helpers, event-name constants (not "logging.py": shadows the stdlib name).
│   ├── jinja.py                  THE Jinja environment (loader over templates/, globals, filters), used by mails and pages.
│   ├── services.py               `Services` container built from settings; `set_services()` is the one test seam.
│   ├── worker.py                 The worker loop: due pipeline steps + periodic jobs (§9).
│   ├── cli.py                    Operator commands (argparse, one function call per subcommand): onboard, backfill, process, demo-mails, poll, status, eval-prompts.
│   ├── db/
│   │   ├── engine.py             Engine, `SessionLocal`, `session_scope()`.
│   │   └── models.py             All ORM models and their StrEnum vocabularies (one file, ~10 tables).
│   ├── sources/                  Source connectors (manifest §7.3) — source-specific.
│   │   ├── base.py               `SourceConnector` Protocol, `ContentItem` and `Comment` dataclasses.
│   │   └── youtube/
│   │       ├── connector.py      `YouTubeConnector` (latest uploads, item details, comments).
│   │       ├── feed.py           Public Atom feed parsing (stdlib xml.etree).
│   │       ├── data_api.py       Thin httpx client for Data API + captions endpoints; QUOTA_UNITS constant.
│   │       └── oauth.py          Google OAuth via httpx: authorize URL, code exchange, refresh; Fernet at rest.
│   ├── transcripts/              Transcript layer (manifest §7.4) — the first deliberate abstraction.
│   │   ├── base.py               `TranscriptProvider` Protocol, `Transcript`/`Segment` dataclasses, error types.
│   │   ├── youtube_official.py   captions.list + captions.download with the creator's token; SRT parser.
│   │   ├── youtube_unofficial.py youtube-transcript-api with proxy config and timeout.
│   │   └── service.py            Provider chain per source; persists transcript + origin.
│   ├── analysis/                 Analysis layer (manifest §7.5) — source-independent.
│   │   ├── llm.py                `LLMGateway` Protocol, `BifrostGateway`, `Completion`; ledger + daily-cap functions.
│   │   ├── schemas.py            Pydantic models for structured outputs (`Summary`, `Section`, `KeyPoint`, `Sentiment`).
│   │   ├── prompts/              Versioned prompt files: summary_v1.md, sentiment_v1.md (variants are templates, not prompts).
│   │   ├── summarize.py          Transcript → `Summary` (prompt assembly, timestamp markers).
│   │   ├── comments.py           Heuristic comment filter (manifest §3.1 feature 2).
│   │   └── sentiment.py          Filtered comments → `Sentiment`.
│   ├── delivery/                 Output layer (manifest §7.6).
│   │   ├── email_client.py       `ResendClient` (send, send_batch, 429 handling) + webhook signature verify. Transport only.
│   │   ├── render.py             Composes `OutgoingEmail`s (sender, reply-to, headers, idempotency key) from templates; CSS inlining.
│   │   └── mailing.py            Mailing lifecycle: create/schedule, reschedule, stop/postpone, sentiment, preview, send in batches.
│   ├── jobs/
│   │   ├── steps.py              Pipeline step functions per status (§9.3) and periodic jobs; called by worker.py and cli.py.
│   │   └── schedule.py           Pure functions: `compute_send_at()`, `next_mailing_step()`, `retry_at()` — tested without DB.
│   ├── web/
│   │   ├── server.py             `create_app()`: middleware (request id, session, rate limit), routers, static.
│   │   ├── deps.py               `get_session`, `current_creator`.
│   │   └── routes/
│   │       ├── public.py         /, /impressum, /datenschutz, /kontakt, /health
│   │       ├── fan.py            /k/{slug}, confirm, unsubscribe, /s/{token}
│   │       ├── creator.py        login (magic link), settings, CSV export, OAuth start/callback, stop/postpone
│   │       └── webhooks.py       /webhooks/resend
│   ├── templates/
│   │   ├── email/                base.html, summary.html + summary.txt, confirm.html/.txt, creator_preview.html, creator_notice.html, magic_link.html/.txt, contact.txt
│   │   ├── pages/                base.html, landing.html, signup.html, confirmed.html, summary.html, creator_login.html, creator_settings.html, action_confirm.html, legal/impressum.html, legal/datenschutz.html, error.html
│   │   └── partials/             summary_body.html (per variant blocks), sentiment_box.html, platform_footer.html, example_mail.html (static snapshot for the landing page)
│   └── static/                   style.css, htmx.min.js, favicon
├── tests/
│   ├── conftest.py               Settings override, DB session per test, `Services` with fakes via `set_services()`.
│   ├── fakes.py                  FakeLLMGateway, FakeEmailClient, FakeTranscriptProvider, FakeYouTubeConnector (duck-typed; returns ContentItems/Comments, absent id = deleted).
│   ├── fixtures/                 feed.xml, video.json, comments.json, transcript.srt, example_summary.json, transcripts/ (prompt eval samples)
│   ├── unit/                     Pure logic: feed parsing, Resend signature, comment filter, schedule maths, SRT parser, settings, templates.
│   └── integration/              Against Postgres: ingest idempotency, DOI flow, mailing state machine, exactly-once send, webhooks.
└── docs/
    ├── ARCHITECTURE.md           Module cut, data flow, state machines, worker loop, "Decisions" section, "Where to find what".
    ├── runbooks/                 onboarding.md (creator onboarding step by step), operations.md (deploy, DNS, quotas, incidents, deletions).
    ├── plans/                    This file and later plans.
    └── manifest/                 Concept documents (source of truth).
```

Why `src/app` and not the product name: manifest §7 (intro) demands the name appear in exactly one place so renaming costs one line. The package name is neutral; `settings.product.name` is the one place.

## 6. Configuration

### 6.1 `config/settings.toml` (checked in, no secrets)

Exactly the tunables manifest §7.1 and §13 name, plus the few the code needs. Values below are the manifest defaults. Values that never change (Resend batch maximum 100, Data API page size 100, token length 32 bytes, the OpenAI-compatible path, provider order) are module constants next to their single use, not configuration (manifest §7.1 "keine Konfiguration für Werte, die sich nicht ändern").

```toml
[product]
name = "Klartext"          # the ONE place the product name lives (manifest §0)
domain = "klartext.tld"    # placeholder until decided (manifest §15); base URL, mail subdomain and mailboxes derive from it
timezone = "Europe/Berlin"

[schedule]                              # manifest §3.1 "Zeitversatz", §7.6 "Zeitplan pro Beitrag"
default_delay_hours = 168               # 7 days
min_delay_hours = 48
max_delay_hours = 720                   # 30 days; also caps "verschieben"
sentiment_lead_hours = 2                # comments fetched at T-2h
stop_window_minutes = 60                # creator preview at T-1h (30–60 min per manifest); never shortened
postpone_hours = 24                     # "verschieben" link

[content]
min_duration_seconds = 300              # manifest §3.1: 5 minutes, per creator overridable
backfill_count = 5                      # manifest §6.1 "Backkatalog beim Onboarding"; `cli backfill --count` overrides for demos
max_transcript_chars = 400000           # ≈ 10 h of speech; above → skip + notify (single-call summarisation ceiling)
transcript_languages = ["de", "en"]     # preference order for caption tracks

[comments]                              # manifest §3.1 feature 2, §13 "Kommentare"
max_count = 300
min_words = 5
drop_with_links = true
drop_channel_owner = true

[llm]                                   # manifest §8
model_summary = "anthropic/claude-sonnet-4-5"   # provider/model as Bifrost addresses it
model_sentiment = "anthropic/claude-sonnet-4-5"
max_output_tokens = 4000
timeout_seconds = 120
daily_cost_cap_cents = 500              # per creator per day (manifest §7.9)
summary_prompt_version = "v1"
sentiment_prompt_version = "v1"

[llm.prices_per_million_tokens]         # for the cost ledger; every model above must have an entry (validated at start-up)
"anthropic/claude-sonnet-4-5" = { input = 3.00, output = 15.00 }

[email]                                 # manifest §7.6
variants = ["compact", "detailed", "teaser"]
default_variant = "compact"
confirm_token_days = 7                  # unconfirmed sign-ups are deleted after this (manifest §7.9)
unsubscribed_retention_days = 30        # unsubscribed rows are deleted after this (manifest §9 deletion concept)
magic_link_minutes = 15
session_hours = 24
max_custom_text_chars = 300             # greeting / farewell (manifest §7.6 "wenige hundert Zeichen")

[web]
rate_limit_signup = "20/minute"         # per IP; deliberately loose, many fans share one mobile-carrier NAT IP
confirm_resend_minutes = 10             # per e-mail address: at most one confirm mail per address in this window (§10)
rate_limit_magic_link = "3/minute"
rate_limit_contact = "3/minute"

[worker]
loop_seconds = 60                       # how often the worker looks for due steps
feed_poll_hours = 6                     # upload detection latency; manifest §7.3 said daily, 6 h is free and shorter

[logging]
level = "INFO"
json = false                            # true in production (LOGGING__JSON=true); the setting alone picks the format
file = ""                               # e.g. "logs/app.log" for a local rotating file; empty = stdout only
```

### 6.2 Environment variables (secrets and per-environment values)

Rule: secrets and per-environment values are **flat** fields of a `Secrets` model read from env only; TOML tables are overridable via `TABLE__KEY` (`env_nested_delimiter="__"`). `.env.example` is the authority and carries a comment per variable.

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | app, worker, alembic | Render injects the internal URL via `fromDatabase` as `postgresql://` (the dashboard shows `postgres://`); `config.py` normalises both to `postgresql+psycopg://`. |
| `SECRET_KEY` | session cookie | Render `generateValue: true`. |
| `TOKEN_ENCRYPTION_KEYS` | OAuth refresh tokens (Fernet) | Comma-separated, first = current (MultiFernet rotation). |
| `BASE_URL` | links in mails and pages | Optional override; default `https://{product.domain}`; local `http://localhost:8000`. |
| `YOUTUBE_API_KEY` | Data API (metadata, comments, channel) | |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | official captions | |
| `TRANSCRIPT_PROXY_USERNAME`, `TRANSCRIPT_PROXY_PASSWORD` | unofficial transcripts from cloud IPs (Webshare rotating residential) | Empty locally. |
| `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | e-mail | |
| `LLM_GATEWAY_URL`, `LLM_GATEWAY_KEY` | LLM client **and** the Bifrost container | e.g. `http://bifrost:8080`; the Bifrost virtual key. `bifrost.json` sets `governance.virtual_keys[0].value = "env.LLM_GATEWAY_KEY"`, so app and gateway read the same variable and the value never appears in the file. |
| `ANTHROPIC_API_KEY` | Bifrost container only | Referenced as `env.ANTHROPIC_API_KEY` in `bifrost.json`; the app never sees it. |
| `BIFROST_SETUP_TOKEN` | Bifrost container only | Native Bifrost variable for the setup token that bootstraps the (never used) admin UI. |
| `DATABASE_URL_TEST` | `uv run pytest` (integration tests) | Locally `…/app_test` (docker-compose creates the second database with a one-line `CREATE DATABASE app_test;` init script); in CI it points at the Postgres service container. |
| `SENTRY_DSN` | optional error tracking | Empty = disabled. |
| `LOGGING__JSON`, `LOGGING__LEVEL` | logging | Nested override. |

Derived in `config.py` (properties, no config keys): `base_url`, `mail_domain = f"mail.{domain}"`, `sender_address = f"post@{mail_domain}"`, `support_email = f"hallo@{domain}"` — the last one overridable with an optional `SUPPORT_EMAIL` env var, because this address must be a mailbox somebody actually reads: it is the reply-to fallback for a creator who sets none (§8.4) and the recipient of every `/kontakt` relay (§10). Sending from a domain needs no MX record, receiving does, and the plan configures no receiving path anywhere; until a mailbox exists, `SUPPORT_EMAIL` points at an existing one, otherwise every contact-form mail hard-bounces against the sending reputation §11 protects. → §20.

### 6.3 Settings class

`app/config.py` holds one `Settings(BaseSettings)` with nested models per TOML table (`ProductSettings`, `ScheduleSettings`, …) and a flat `Secrets` model from env. `settings_customise_sources` returns `(init, env, dotenv, TomlConfigSettingsSource)` in that order — the pydantic docs' minimal example returns only the TOML source and would silently disable env overrides. Validation at start-up: `min_delay_hours ≥ 1`, `default ∈ [min, max]`, `default_variant ∈ variants`, `stop_window_minutes < sentiment_lead_hours*60`, and every model named in `llm.model_summary` / `llm.model_sentiment` has an entry in `llm.prices_per_million_tokens` (otherwise a model swap would either fail at the first call or silently book cost 0 and bypass the cap). `get_settings()` is `functools.lru_cache`d; tests call `get_settings.cache_clear()`.

Per-creator overrides (delay, min length, variant, branding, reply-to) live in the `creators` table and are read through one helper `effective_settings(creator)` so no code path reads the file default when a creator value exists. The settings form (§10) validates creator input against the same `min`/`max`/`variants` values from `settings` — one rule, two call sites, no second implementation.

## 7. Data model

Maps manifest §7.7 one-to-one; English names in code, manifest names in brackets. All timestamps `timestamptz` in UTC; display in `product.timezone`. IDs are integer primary keys; external identifiers are separate unique columns.

Vocabularies (`appearances.status`, `transcripts.origin`, `analyses.kind`, `subscriptions.status`, `mailings.status`, `subscribers.blocked_reason`, the `kind` of creator notices) are each one `enum.StrEnum` defined in `app/db/models.py` next to its table; the column is `VARCHAR` with a `CheckConstraint` built from `list(Enum)` (Alembic autogenerate mishandles native Postgres enums; migrations spell the values out because a migration is a snapshot). Steps, routes and templates compare against enum members, never literals. Transition sets (e.g. `MAILING_STOPPABLE`) are constants beside the enum. `skip_reason` and `last_error` are free text.

Every FK on the chain below `creators` (`sources.creator_id`, `appearances.source_id`, `transcripts/analyses/mailings.appearance_id`, `deliveries.mailing_id`, `deliveries.subscription_id`, `subscriptions.creator_id`, `subscriptions.subscriber_id`) is `ON DELETE CASCADE`; the ledger FKs on `llm_calls` are `ON DELETE SET NULL`. Deleting a creator or a subscriber on request is therefore one SQL statement in the runbook (manifest §7.9 "Export und Löschung"), not a CLI tree-walk.

| Table | Purpose (manifest term) | Key columns and constraints |
|---|---|---|
| `creators` | Customer for product 1 (*Creator*) | `slug` unique (sign-up URL), `name`, `contact_email` (login + notices), `reply_to_email` nullable, `logo_url`, `accent_color` (`#rrggbb`), `greeting_text`, `farewell_text`, `email_variant`, `send_delay_hours` nullable, `min_duration_seconds` nullable, `magic_link_token_hash` + `magic_link_expires_at` nullable, `created_at`. Nullable overrides = "use the file default". |
| `sources` | A YouTube channel (*Quelle*) | `creator_id`, `kind` (`youtube`), `external_id` (channel `UC…`), `title`, `oauth_refresh_token_enc` nullable, `oauth_granted_at`, `oauth_needs_reconsent` bool, `created_at` (feed entries published before it are ignored unless backfilled). Unique `(kind, external_id)`. |
| `appearances` | A video (*Auftritt*) — the central, source-independent object | `source_id`, `external_id` (video id), `title`, `url`, `published_at`, `duration_seconds` nullable, `status` (§9.1), `skip_reason` nullable, `is_backfill` bool, `view_token` unique (32 random bytes, url-safe), `attempts`, `next_attempt_at`, `last_error` (retry bookkeeping, §9.4), `created_at`. **Unique `(source_id, external_id)` — this is the idempotency guarantee** (manifest §7.9). |
| `transcripts` | (*Transkript*) | `appearance_id` unique, `origin` (`youtube_official` / `youtube_unofficial`) — stored because it is legally relevant (manifest §7.7), `language`, `is_generated` bool, `segments` jsonb `[{start, duration, text}]`, `fetched_at`. Plain text is derived on read (`Transcript.text`), not stored twice. |
| `analyses` | (*Analyse*) | `appearance_id`, `kind` (`summary` / `sentiment`), `prompt_version`, `model`, `content` jsonb (validated `Summary` / `Sentiment`), `created_at`. **Unique `(appearance_id, kind)`** — one current analysis per kind, written with `INSERT … ON CONFLICT DO UPDATE` (a sentiment refresh after postpone overwrites). `prompt_version` + `model` record what produced it (manifest §7.7 "versioniert nach Prompt/Modell"); comparing prompt versions happens in `cli eval-prompts`, not in the DB. `# ponytail: one analysis per kind; keep history when A/B-comparing prompts in production becomes a real task.` A missing `sentiment` row means "no sentiment" (comments disabled or sentiment step gave up). |
| `subscribers` | An e-mail address (*Abonnent*), can follow several creators | `email` unique (stored lower-cased), `blocked_at` + `blocked_reason` (`bounce` / `complaint`) nullable, `created_at`. Blocked rows are kept as the suppression list: a `complaint` block is permanent (re-signup sends nothing); a `bounce` block is lifted when the address later confirms a sign-up — the confirm mail got through, so the mailbox works again (§10). |
| `subscriptions` | Subscriber ↔ creator with double-opt-in state | `subscriber_id`, `creator_id`, `status` (`pending` / `confirmed` / `unsubscribed`), `confirm_token` unique, `confirm_expires_at`, `confirm_sent_at` (throttles confirm mails per address, §10), `confirmed_at`, `unsubscribe_token` unique (permanent, per creator), `unsubscribed_at`, `created_at`. Unique `(subscriber_id, creator_id)`. |
| `mailings` | One planned send per appearance (*Zustellung*, planned part) | `appearance_id` unique, `status` (§9.2), `send_at`, `stop_token` unique (rotated on every new schedule: postpone and delay change), `preview_sent_at`, `render_snapshot` jsonb nullable (the creator's rendering-relevant fields, frozen when the preview goes out — §8.4), `stopped_at`, `sent_at`, `recipient_count`, `attempts`, `next_attempt_at`, `last_error`, `created_at`. |
| `deliveries` | One row per recipient per mailing (*Zustellung*, per subscriber) — a send ledger, not analytics | `mailing_id`, `subscription_id`, `sent_at` nullable (null = pending). **Unique `(mailing_id, subscription_id)` — exactly-once per recipient.** `# ponytail: no delivered/bounced state, no provider message id; bounces block the subscriber by address, delivery/open rates come from the Resend dashboard (manifest §7.6). Add columns with the Phase-2 analytics dashboard.` |
| `llm_calls` | Cost ledger (manifest §7.9 "Kostenkontrolle") | `creator_id` nullable, `appearance_id` nullable, `purpose`, `model`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_cents` numeric, `duration_ms`, `ok` bool, `created_at`. |
| `job_runs` | Periodic-job bookkeeping | `name` primary key, `last_run_at`. Replaces a queue's cron tables. |

Not stored, on purpose: raw comments (fetched, filtered, summarised, discarded — manifest §7.9 "keine Rohdaten länger als nötig" and the YouTube API 30-day rule), raw audio/video (manifest §7.7), sign-up IP addresses, access tokens (only the encrypted refresh token), webhook event ids (every webhook write is set-to-value, so replays are no-ops).

## 8. Module design

### 8.1 Sources (`app/sources`)

```python
@dataclass(frozen=True)
class ContentItem:          # what every connector returns (manifest §7.3 "Ein Connector liefert immer dasselbe Ergebnis")
    external_id: str; title: str; url: str; published_at: datetime
    duration_seconds: int | None; is_public: bool; is_live_or_upcoming: bool; comments_disabled: bool

@dataclass(frozen=True)
class Comment: text: str; like_count: int; author_channel_id: str | None

class SourceConnector(Protocol):
    kind: str
    def latest_items(self, source_external_id: str, limit: int) -> list[ContentItem]: ...
    def item_details(self, external_ids: list[str]) -> list[ContentItem]: ...   # absent ids = deleted
    def comments(self, external_id: str, max_count: int) -> list[Comment]: ...   # empty for sources without comments
```

`YouTubeConnector` implements it with `data_api.py`: one function per endpoint, httpx, API key, `fields` parameter to keep payloads small, ISO-8601 duration parsed with a 10-line regex, ids chunked at 50. `videos.list` with `part=snippet,contentDetails,status,liveStreamingDetails` (same 1 unit) also reads `status.madeForKids` (comments are disabled by policy → skip the comment call); `ContentItem.published_at` is `liveStreamingDetails.actualStartTime` when present, otherwise `snippet.publishedAt` — for premieres and live streams `publishedAt` is the time the broadcast was scheduled, not the time it went live, and the delay must count from go-live. All Data API error mapping happens once, in the client's single request helper: httpx transport errors and timeouts, 5xx, 429, 403 `quotaExceeded` (the daily quota resets 09:00 CEST, §18 — the retry ladder simply waits it out) and 400 `processingFailure` → `TemporaryError`; 403 `commentsDisabled` → empty comment list; any other 4xx → permanent. Captions: 403 → `TranscriptUnavailable("forbidden")`, 404 → `TranscriptUnavailable("no_captions")` — never retried, each attempt costs 250 units. Latest uploads come from the `UU…` uploads playlist (the `UC→UU` substitution is folklore that works; on `playlistNotFound` fall back to `channels.list?part=contentDetails`), using `contentDetails.videoPublishedAt`. The captions endpoints (`captions.list`, `captions.download`) live in the same client, called with a bearer token instead of the key. `QUOTA_UNITS = {"videos.list": 1, "channels.list": 1, "playlistItems.list": 1, "commentThreads.list": 1, "captions.list": 50, "captions.download": 200}` sits next to the functions and every call logs `quota.youtube` with its units (§12).

`feed.py` parses the public Atom feed with `xml.etree` (namespaces `atom`, `yt`) into `FeedEntry(video_id, channel_id, title, published_at)`. Notes: the feed-level `yt:channelId` lacks the `UC` prefix — use the per-entry value; build watch URLs from `yt:videoId`; the feed holds only the 15 newest uploads (`# ponytail: a channel publishing >15 videos between two polls loses items; fall back to playlistItems when all 15 ids are unseen`).

`oauth.py` (httpx, ~40 lines): `authorization_url(state)` (urlencoded params: `access_type=offline`, `prompt=consent`, scope `youtube.force-ssl`, `include_granted_scopes=true`), `exchange_code(code) -> refresh_token`, `refresh_access_token(refresh_token) -> (access_token, new_refresh_token | None)` — both a POST to `https://oauth2.googleapis.com/token`. The refresh token is stored Fernet-encrypted; a new one returned by the token endpoint is persisted. A response with `error == "invalid_grant"` sets `oauth_needs_reconsent` and notifies the creator; inside `transcribe` the official provider then raises `TranscriptUnavailable("no_grant")` so the chain continues with the unofficial provider in the same run (not a retry). Other token-endpoint errors are temporary. The scope list in code must be identical to the console's consent-screen list, or Google shows the unverified-app screen.

Phase 2 adds `sources/podcast/` as a second implementation of the same Protocol; nothing below the connector changes.

### 8.2 Transcripts (`app/transcripts`)

```python
@dataclass(frozen=True)
class Segment: start: float; duration: float; text: str
@dataclass(frozen=True)
class Transcript:
    origin: str; language: str; is_generated: bool; segments: list[Segment]
    @property
    def text(self) -> str: ...

class TranscriptProvider(Protocol):
    origin: str
    def fetch(self, source: Source, item: ContentItem, languages: list[str]) -> Transcript: ...

class TranscriptUnavailable(Exception): reason: str        # no_captions, disabled, age_restricted, po_token, forbidden
class TranscriptTemporaryError(Exception): ...             # blocked ip, 429, network
```

`service.fetch_transcript(source, item)` tries `youtube_official` when the source has a usable OAuth grant, then `youtube_unofficial` (the chain is the list `get_services().transcripts`, built in that order in `services.py`), maps provider-specific exceptions to the two error types, and returns the first success. The origin is persisted with the transcript.

- `youtube_official.py`: `captions.list` (50 units) → pick track by language preference, prefer `trackKind=standard` over `ASR` → `captions.download?tfmt=srt` (200 units) → SRT parser (regex, stdlib) → `Transcript`. 403 on the chosen track → `TranscriptUnavailable("forbidden")` so the chain falls through. Quota budget per video: 250 units, spent **once per video, not once per attempt** — the provider is offered while the source has a usable grant and `appearances.official_captions_declined` is false, a flag set in its own committed session when the official provider says no for good (so the 250-unit lesson survives the rollback of a step that then failed temporarily). The shared retry counter must *not* stand in for this flag: it is incremented by any step's temporary failure, and the realistic one here is the **unofficial** provider's IP block — so gating on it would disable official captions for a creator who connects YouTube precisely because the first attempt failed.
- `youtube_unofficial.py`: `YouTubeTranscriptApi(proxy_config=WebshareProxyConfig(...) if configured, http_client=session_with_timeout).fetch(video_id, languages)`. Runs in the worker (sync, one fresh instance and session per call — the library is not thread-safe and mutates the session it is given). Video ids are validated with `^[A-Za-z0-9_-]{11}$` first. Exception mapping: `RequestBlocked`/`IpBlocked`/`YouTubeRequestFailed` → temporary; `NoTranscriptFound`/`TranscriptsDisabled`/`AgeRestricted`/`PoTokenRequired`/`VideoUnavailable` → unavailable with the exception name as reason. Timeout is injected through a `requests.Session` subclass overriding `request()` (a mounted adapter would be replaced by the proxy config's own retry adapter). The Webshare account must be the "Residential" package; free/datacenter tiers are blocked by YouTube. Known gap: the library talks to YouTube as the Android client and may not see a manually uploaded caption track, silently falling back to ASR — one more reason the official provider comes first.

### 8.3 Analysis (`app/analysis`)

The LLM gateway (the second deliberate abstraction, manifest §8) knows nothing about the database:

```python
@dataclass(frozen=True)
class Completion: result: BaseModel; model: str; tokens_in: int; tokens_out: int; duration_ms: int

class LLMGateway(Protocol):
    def complete_json(self, *, model: str, system: str, user: str, schema: type[BaseModel]) -> Completion: ...
```

`BifrostGateway` POSTs to `{LLM_GATEWAY_URL}/v1/chat/completions` (`Authorization: Bearer {LLM_GATEWAY_KEY}`) with `response_format={"type": "json_schema", "json_schema": {...schema.model_json_schema()...}}`, parses `choices[0].message.content` into the Pydantic model (one retry with the validation error appended on failure), reads `usage.prompt_tokens`/`completion_tokens` (`.get(…, 0)` — omitted when zero; `total_tokens` is always present) and returns a `Completion`.

Ledger and cap are two plain functions in the same file, called by `summarize.py` and `sentiment.py`: `assert_under_cap(session, creator_id, settings)` raises `CostCapExceeded` when the creator's `llm_calls` sum for the current calendar day in `product.timezone` (`cli status` uses the same boundary) ≥ `daily_cost_cap_cents` — the worker treats it as "wait for the reset", not as a retry attempt (§9.4); `record_call(completion | error, purpose, creator_id, appearance_id)` writes the `llm_calls` row (also on failure, `ok=false`) with the cost from `prices_per_million_tokens`, **in its own short-lived session, committed immediately**. It must not join the caller's transaction: a step that pays for a summary and then fails on the analysis upsert or the mailing insert would otherwise roll back the record of the money it just spent, and ten retries (§9.4) would re-pay against a ledger that never grew — defeating the one mechanism that exists to stop exactly that (manifest §7.9 "ein Kostendeckel pro Tag verhindert Überraschungen durch Endlosschleifen"). Tests for the cap run against real code with a fake gateway.

Prompts are Markdown files under `analysis/prompts/`, loaded once, with `str.format` on a handful of named fields; the version is part of the file name and stored on the analysis. Prompt content rules (manifest §3.1, §8): sober tone, no distortion, no clickbait, summary in the language of the video, timestamps only from the provided markers, one strong quote verbatim.

Structured outputs (manifest §7.5 "als strukturierte Daten"):

```python
class KeyPoint(BaseModel): text: str; timestamp_seconds: int | None
class Section(BaseModel): title: str; key_points: list[KeyPoint]
class Summary(BaseModel):
    language: str; headline: str; core_message: str        # two sentences
    key_points: list[KeyPoint]                              # 3–5, always filled
    sections: list[Section]                                 # 2–4, always filled; templates decide what to show
    quote: str; quote_timestamp_seconds: int | None
class Sentiment(BaseModel):
    overall: str; agreed: list[str]; disagreed: list[str]; questions: list[str]; comment_count_used: int
```

`summarize.py` builds the user prompt from the transcript as `[mm:ss] text` lines (the model cites these markers; jump links become `{url}&t={seconds}s`) and calls the gateway with the one variant-independent summary prompt (length rules for every field live in `summary_v1.md`, so the compact block stays under 300 words). Ceiling: one call up to `content.max_transcript_chars`; above that the appearance is skipped and the creator notified (`# ponytail: single-call summarisation; add map-reduce chunking when a real video exceeds the ceiling`).

`comments.py` (pure function, unit-tested): drop `< min_words`, drop containing URLs, drop `author_channel_id == source.external_id`, dedupe by normalised text (copy-paste spam), cap at `max_count`. `sentiment.py` feeds the survivors (text + like count only) to the sentiment prompt. No comments (disabled, made for kids, or none pass the filter) → no `Sentiment`; templates render the box only when present (manifest §3.1 "Features degradieren sauber").

### 8.4 Delivery (`app/delivery`)

```python
@dataclass(frozen=True)
class OutgoingEmail:
    from_: str; to: str; reply_to: str; subject: str; html: str; text: str
    headers: dict[str, str]; idempotency_key: str | None; tags: dict[str, str]
```

`render.py` composes every mail: `render_summary_mail(creator, appearance, summary, sentiment, subscription: Subscription | None) -> OutgoingEmail` and siblings for confirm, preview, notice, magic link, contact relay. It fills `from_` = `"{creator.name} via {product.name} <{sender_address}>"`, `reply_to` = the creator's reply-to or `support_email` (no `noreply`, manifest §7.6), `headers` = `List-Unsubscribe: <{base_url}/abmelden/{subscription.unsubscribe_token}>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, and the idempotency key, format `{purpose}/{ids}`: batches `mailing/{mailing_id}/{first_delivery_id}`, creator preview `preview/{mailing_id}/{stop_token}` (the token rotates with every new schedule, so a new schedule gets a new preview while retries of one preview share the key even if `send_preview` pushes `send_at` between attempts), notices `notice/{kind}/{appearance_id}`; confirm, magic-link and contact mails carry none (a resend there is intended). `subscription=None` is the creator preview: no `List-Unsubscribe` headers, and the footer's per-subscription sentence is replaced by "Vorschau für {creator} — so sehen deine Abonnenten die Mail" with the stop/postpone action bar on top. HTML goes through `css_inline.inline(html, load_remote_stylesheets=False)`; the text part is rendered from a `.txt` template (no HTML stripping heuristics). The M4 header/sender tests assert on the `OutgoingEmail` captured by the fake.

**Payload freeze.** Every mail of one mailing is rendered from `mailings.render_snapshot` — the creator's `name`, `email_variant`, `greeting_text`, `farewell_text`, `reply_to_email`, `logo_url` and `accent_color`, copied onto the row in the same statement that sets `preview_sent` (§9.2). It buys two things at the price of one jsonb column. First, the fans get exactly the mail the creator saw and chose not to stop — without it, a settings change inside the stop window silently sends something else than what was previewed, which is the whole point of manifest §3.1's "Vorschau mit Stopp-Fenster". Second, a batch retried up to ~23 h later (§9.4) carries a byte-identical payload under its stable `Idempotency-Key`; what Resend does with a repeated key and a changed body is undocumented (§18), and this design never finds out. The alternative — putting a body hash in the key — was rejected: it turns a changed body into a legitimately new request and therefore into a second mail for recipients whose first attempt had in fact succeeded, trading the manifest's hardest promise away for a column. A variant switch still applies instantly to every mailing before its preview and to every summary page; changing a previewed mail means stopping or postponing it, which rotates the token and produces a fresh preview with a fresh snapshot.

`ResendClient` (`email_client.py`) is transport only: `send(mail) -> str` and `send_batch(mails) -> list[str]` (provider ids, same order) map `OutgoingEmail` 1:1 to the API payload and add the `Idempotency-Key` header. A 429 is inspected before retrying: `rate_limit_exceeded` → wait `retry-after`; `daily_quota_exceeded` / `monthly_quota_exceeded` → raise (temporary; the step retries later and the operator is alerted). Batches are strict (the SDK's "permissive" mode has no server-side counterpart): any other non-2xx logs the response body at ERROR and raises; nothing is marked sent and the mailing step retries (§9.4). `# ponytail: one address that passes sign-up validation but is rejected by Resend blocks the mailing until the operator blocks the subscriber; add per-address handling only if that happens.` `verify_webhook_signature(body, headers, secret) -> bool` is the 15-line stdlib svix check.

`mailing.py` holds the lifecycle functions used by the steps and the routes (§9); mailing status is written only here. Every transition is one conditional statement, `UPDATE mailings SET … WHERE id = :id AND status = :expected`, and the caller checks the rowcount: 0 rows means another writer (stop/postpone route, reschedule, or a step) moved the row first; the caller logs `mailing.transition_lost` (expected, actual) and returns without further side effects. This is what lets the web process and the worker write the same row without a lock between them.

### 8.5 Jobs (`app/jobs`, `app/worker.py`)

`worker.py` is the worker process: `while True: run_due_steps(now); run_periodic_jobs(now); sleep(settings.worker.loop_seconds)`, with structured logging around each step and Sentry capture on unexpected exceptions. `# ponytail: one sequential worker and the only step runner (the CLI ingests, never runs steps); add SELECT … FOR UPDATE SKIP LOCKED and a second worker when one channel's volume is no longer enough.` `run_due_steps(now)` selects, per status, rows whose `next_attempt_at IS NULL OR <= now` and calls the step function for that status with the same `now` (§9.3); steps never call `datetime.now()` themselves, which is what makes the stepped-clock tests in §14 possible. `run_periodic_jobs` reads `job_runs` and runs a job when `last_run_at` is older than its interval (`feed_poll_hours`, daily cleanup). Steps stay thin: the work is one call into the owning layer module (`transcripts.service`, `analysis.summarize`/`sentiment`, `delivery.mailing`); appearance status is written only by the steps in `jobs/steps.py`, mailing status only by `delivery/mailing.py`, which steps and routes both call.

`schedule.py` contains the pure maths, tested without a database:

```python
def compute_send_at(published_at, delay_hours, now, min_delay_hours) -> datetime:
    # The 48 h minimum counts from the moment the video became public, which is never later
    # than `now` at scheduling time — so the floor is now + min_delay, not a separate lead value.
    return max(published_at + timedelta(hours=delay_hours), now + timedelta(hours=min_delay_hours))

def next_mailing_step(mailing, now, schedule) -> str | None:
    # 'prepare_sentiment' when status == scheduled and now >= send_at - sentiment_lead
    # 'send_preview'      when status == sentiment_ready and now >= send_at - stop_window
    # 'send'              when status == preview_sent and now >= send_at and now >= preview_sent_at + stop_window,
    #                     or status == sending (resume)
    # None otherwise

def retry_at(attempts, now) -> datetime:   # now + 5 min * 2**(attempts-1), capped at 6 h (§9.4)
```

### 8.6 Web (`app/web`) and shared infrastructure

`create_app()` wires: request-id middleware (binds structlog contextvars — anyio copies the context into the threadpool, so `def` endpoints see it), `SessionMiddleware` (signed cookie, `SECRET_KEY`, `session_hours`), slowapi limiter, routers, static files. `app/jinja.py` builds **the** `jinja2.Environment` once (`FileSystemLoader` over `templates/`, `autoescape=select_autoescape(["html"])` so `.txt` twins stay unescaped, globals `product`, `base_url`, `roadmap`, filters `local_datetime`/`local_date` in `product.timezone`); mails and pages share it and the partials (summary body, sentiment box, platform footer), so mail and page cannot drift. HTMX is used for the sign-up form's inline response and the settings form's save feedback (`hx-post`, partial templates). Error pages are branded and say something useful.

`services.py` builds the concrete clients lazily, once per process: `Services(youtube: SourceConnector, transcripts: list[TranscriptProvider], llm: LLMGateway, email: ResendClient)` behind `get_services()` (module-level cache, built from `get_settings()` on first call). The connector level is injected, never the raw Data API client; `transcripts` is the provider chain in order. The public Atom feed GET in `feed.py` is a plain httpx call and not a Services member; its parsing is unit-tested from `fixtures/feed.xml` and the poll's filter through `ingest_item`. Routes and steps call `get_services()` directly — steps take only ids and `now`, so this accessor is the one seam through which fakes enter. The module exposes exactly one override, `set_services(services | None)`, used only by `tests/conftest.py` (`# ponytail: process-global override; switch to explicit injection if a second process model ever appears`). This is the entire dependency-injection story.

`cli.py` is argparse plus one function call per subcommand; the operations live in the owning layer (`onboard` → `sources/youtube/connector.py` + `db`; `backfill`/`process`/`poll` → `jobs/steps.py`; `demo-mails`/`eval-prompts` → `delivery/render.py` and `analysis`; `status` → one query module in `jobs/steps.py`). `backfill`, `process` and `poll` only **ingest** (`ingest_item` → `detected`); they never call a step function — the worker is the single process that runs steps, and a second runner would repeat the same expensive step on the same row. Progress is watched with `cli status`; locally the worker started by `docker compose up` picks the rows up within `worker.loop_seconds`. The CLI tests exercise the layer functions, not argparse.

## 9. The pipeline: states, steps, worker

Implements manifest §7.6 "Zeitplan pro Beitrag" and §7.9 idempotency with a status machine in the database and one worker loop (ADR-style reasoning in `docs/ARCHITECTURE.md` → "Decisions").

### 9.1 Appearance status (transition table)

| From | To | Trigger (step) | Note |
|---|---|---|---|
| — | `detected` | `ingest_item` (feed poll, backfill, `cli process`) | Insert `ON CONFLICT DO NOTHING`; the poll re-seeing an entry is a no-op. |
| `detected` | `enriched` | `enrich` | Public, not live/upcoming, duration ≥ creator minimum; title/url/published_at overwritten from `videos.list` (feed titles are provisional; creators edit titles; `published_at` = `actualStartTime` for premieres and streams, so a premiere parked in `detected` for weeks still gets the full delay from go-live). |
| `detected` | `detected` | `enrich` | Item returned but not public yet (upcoming premiere, live, private before publication): `skip_reason='not_public_yet'`, `next_attempt_at = now + 6 h`, `attempts` not counted. The step re-checks every 6 h (1 quota unit) for as long as it takes — a premiere three weeks out is exactly the video a creator promotes most; the row leaves `detected` only when the video is public (→ `enriched`) or gone (→ `unavailable`). No cleanup rule, no special timer. |
| `detected` | `detected` | `enrich` | Public, but `duration_seconds` is missing or `0` — a livestream VOD reports `contentDetails.duration = PT0S` until YouTube has finished processing it. Treated exactly like `not_public_yet`: `skip_reason='no_duration_yet'`, `next_attempt_at = now + 6 h`, `attempts` not counted. Without this row the naive `duration < minimum` comparison drops the pilot's stream recording into terminal `skipped_short`, silently and without a notice. |
| `detected` | `skipped_short` | `enrich` | Duration **known** and below the creator's minimum. Terminal, creator not notified (expected for shorts). |
| `detected` | `unavailable` | `enrich` | Item not returned (deleted). Terminal. |
| `enriched` | `transcribed` | `transcribe` | Transcript row written with origin. |
| `enriched` | `skipped_no_transcript` | `transcribe` | Permanent `TranscriptUnavailable`. Terminal, creator notified. |
| `transcribed` | `analyzed` | `summarize` | Summary analysis written. Backfill row: comments fetched, filtered and the sentiment analysis upserted in the same step (the video is old, its comments are final — manifest §7.6's "kurz vor dem Versand" has no send to wait for); any error there → WARNING `mailing.sentiment_skipped(reason)`, no sentiment row, no retry. Otherwise a mailing is created in the same transaction (§9.2). |
| `transcribed` | `skipped_too_long` | `summarize` | Transcript above `max_transcript_chars`. Terminal, creator notified. |
| any non-terminal | `failed` | any step, on the last allowed attempt (§9.4) | Terminal, creator notified, operator alerted (Sentry). |
| `analyzed` (page live) | `unavailable` | `send` re-check, or `cleanup` re-check of recently sent videos | Video deleted or made private after processing: summary page → 410, open mailing → `cancelled` (manifest §7.9). |

### 9.2 Mailing status (transition table)

| From | To | Trigger | Note |
|---|---|---|---|
| — | `scheduled` | `summarize` | `send_at = compute_send_at(published_at, delay, now, min_delay_hours)`, fresh `stop_token`. |
| `scheduled` | `sentiment_ready` | `prepare_sentiment` at `send_at − sentiment_lead` | Re-checks the video is public (1 unit), fetches ≤ 300 comments, filters, LLM sentiment, upserts the analysis. No usable comments → `sentiment_ready` without a sentiment row. Temporary errors retry with the short ladder (5, 10, 20 … min) **but never past the preview deadline**: when `retry_at(attempts, now) ≥ send_at − stop_window`, the step gives up and sets `sentiment_ready` without sentiment, WARNING `mailing.sentiment_skipped(reason)`. The mail must not stall on the comment box, and this step never reaches `failed`. |
| `scheduled` | `cancelled` | `prepare_sentiment` | Video no longer public. Appearance → `unavailable`. |
| `sentiment_ready` | `preview_sent` | `send_preview` at `send_at − stop_window` | Sets `send_at = max(send_at, now + stop_window)` **before** sending so a late pipeline never shortens the stop window; sends; then the conditional `sentiment_ready → preview_sent` update with `preview_sent_at = now` and `render_snapshot` (§8.4) written in the same statement. If a postpone won in between (0 rows), the preview that went out carries the rotated-away token (its links are dead) and the mailing is re-previewed at the new time. |
| `preview_sent` | `sending` | `send` when `now ≥ send_at` **and** `now ≥ preview_sent_at + stop_window` | One `videos.list` re-check first (not public → `cancelled`); then, in one transaction, the conditional `preview_sent → sending` update (0 rows — the creator stopped or postponed during the re-check — → return, nothing inserted, nothing sent) and `deliveries` rows inserted for all `confirmed` subscriptions of unblocked subscribers — the recipient set is a snapshot at send start; later confirmations go to the next mailing. |
| `sending` | `sent` | `send` (same run or a resumed run) | Batches of `BATCH_SIZE = 100` pending deliveries `ORDER BY id`; each batch `send_batch` with key `mailing/{mailing_id}/{first_delivery_id}`, then `sent_at` set on those rows in one transaction. No pending rows left → `sent`, `sent_at`, `recipient_count`. Resend dedups a repeated batch by key for 24 h, so a crash between the API call and the commit cannot double-send. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `stopped` | creator stop link | Terminal. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `scheduled` | creator postpone link | `send_at += postpone_hours`, capped at `published_at + max_delay_hours` (beyond the cap the confirmation page offers only "stoppen"); `stop_token` rotated so older preview links die (manifest §7.9 "einmal verwendbar"); sentiment is refreshed at the new `T−2h`. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `scheduled` | creator changed `send_delay_hours` in settings | Only when the delay value changed **and** the new `send_at` differs; status falls back to `scheduled` only from `sentiment_ready`/`preview_sent`; `stop_token` rotated exactly as on postpone (one rule: a new schedule is a new token and a new preview). Saving a greeting touches no mailing. Logged as `mailing.rescheduled` with old/new. |
| `sending` | — | — | Never stopped or rescheduled: the send has begun. |
| `sentiment_ready` / `preview_sent` / `sending` | `failed` | `send_preview` or `send` after `MAX_ATTEMPTS` temporary errors (§9.4) | Terminal for the automation; operator alerted (Sentry), creator notified. Recovery is manual and documented in the runbook: fix the cause, then `UPDATE mailings SET status = '<previous state>', attempts = 0` — a half-sent mailing resumes from `sending` and skips the deliveries already marked. |

**Concurrency guard for `send`:** the step holds a **session-level** advisory lock for its whole duration — `SELECT pg_try_advisory_lock(mailing_id)` on a dedicated connection (`engine.connect()`, outside the session used for the transactions) taken before the snapshot transaction, `pg_advisory_unlock` in `finally`; not acquired → log and return. A transaction-scoped lock would be released by the first commit and leave the batch loop unprotected. If the worker dies, Postgres releases the lock with the connection. This covers the only realistic overlap — Render's zero-downtime deploy runs the old and the new worker for about a minute — and the resumed run then selects only rows with `sent_at IS NULL`.

Timeline for a video published at `P` with creator delay `D` (default 7 days): `T = compute_send_at(P, D, now, min_delay_hours)`; sentiment at `T − 2 h`; preview at `T − 60 min`; send at `T`. The worker loop (every 60 s) evaluates `next_mailing_step()` for open mailings; nothing is scheduled ahead of time, so changing `send_at` needs no cancellation logic.

### 9.3 Steps and periodic jobs (`jobs/steps.py`)

| Function | Selected rows | Does | Errors |
|---|---|---|---|
| `ingest_item(session, source, entry, allow_backlog=False)` | called by `poll_feeds`, `backfill`, `cli process` (the latter two with `allow_backlog=True`) | Derives `is_backfill = entry.published_at < source.created_at` from the data, never from the caller; inserts the appearance with a fresh `view_token`; a backlog entry is ignored unless `allow_backlog` (a first poll must never mail the back catalogue). A post-onboarding upload is therefore mailed regardless of whether the poll or `backfill` sees it first. The flag is re-evaluated once in `enrich`, after `published_at` has been replaced by `actualStartTime`: a premiere scheduled before onboarding that goes live after it is no back-catalogue video, so `is_backfill` is cleared when the corrected `published_at >= source.created_at`. Without that line the pilot's first premiere — typically the newest uploads-playlist entry at onboarding, hence ingested by `backfill` — would get a summary page and never a mail. | — |
| `enrich(appearance_id, now)` | `status = detected`, due | `item_details` → transitions per §9.1. | temporary → retry |
| `transcribe(appearance_id, now)` | `status = enriched`, due | Provider chain (§8.2), transcript row. | temporary → retry (blocked IPs, 429); permanent → `skipped_no_transcript` + notice |
| `summarize(appearance_id, now)` | `status = transcribed`, due | Length check, cap check, LLM summary, analysis upsert; then mailing creation, or for backfill the comment fetch + sentiment now (§9.1). | gateway errors → retry; `CostCapExceeded` → wait 6 h, `attempts` not counted (§9.4) |
| `prepare_sentiment(mailing_id, now)` | `next_mailing_step == 'prepare_sentiment'` | §9.2 row. | temporary → retry until the preview deadline, then proceed without sentiment; `CostCapExceeded` → skipped with reason `cost_cap` |
| `send_preview(mailing_id, now)` | `'send_preview'` | Renders the exact fan mail for the creator (`subscription=None`, §8.4) with the action bar on top (stop / postpone links, valid until `T`); sends to `contact_email`. | temporary → retry |
| `send(mailing_id, now)` | `'send'` | §9.2 rows (`sending` → `sent`). | temporary → retry; the mailing stays `sending` and resumes |
| `notify_creator(session, creator, kind, context)` | called by steps | Sends a `creator_notice` mail (`kind` ∈ `no_transcript`, `too_long`, `oauth_reconsent`, `failed`). | — |
| `poll_feeds(now)` | periodic, every `feed_poll_hours` | Fetches each source's public Atom feed (15 newest entries), `ingest_item` for each. `# ponytail: the 6-hourly poll is the only upload trigger; add PubSubHubbub push when a creator needs sub-hour detection.` | logged, next run |
| `cleanup(now)` | periodic, daily | Deletes `pending` subscriptions whose `confirm_expires_at < now` and `unsubscribed` ones whose `unsubscribed_at` is older than `unsubscribed_retention_days` (subscribers without remaining subscriptions and without `blocked_at` too); re-checks with `videos.list` (chunks of 50, 1 unit each) **every appearance in `analyzed`**, regardless of mailing state and age, and marks deleted/private ones `unavailable` — a mailing-bound selector would never reach a backfill row, which by §9.5 gets no mailing at all and whose `/s/` page is exactly what the confirmation page hands every new fan (§10); for one channel this is a handful of 1-unit calls a day (manifest §7.9 "nachträglich gelöschte Beiträge"; also keeps stored API data consistent per YouTube API policy). | logged, next run |

### 9.4 Retries and failure

Steps raise `TemporaryError` (`app/errors.py`; `TranscriptTemporaryError`, the Data API and OAuth temporary errors and the Resend quota error subclass it — the worker catches exactly this one type) or a permanent error (mapped to a terminal status immediately). On a temporary error the worker sets `attempts += 1`, `next_attempt_at = retry_at(attempts, now)` and `last_error`, where `retry_at` waits `5 min × 2^(attempts−1)` capped at 6 h: 5, 10, 20, 40, 80, 160, 320 min, 6 h, 6 h — nine waits, ≈ 23 h in total for `MAX_ATTEMPTS = 10`, inside the 48 h minimum delay. After the last attempt the row becomes `failed` (appearance, or mailing for `send_preview`/`send`), the operator is alerted and the creator notified. `prepare_sentiment` uses the same ladder but stops at the preview deadline (§9.2) and never fails. Successful steps reset `attempts` to 0. `CostCapExceeded` is the one temporary condition that is not a retry: like `not_public_yet` (§9.1) the worker sets `next_attempt_at = now + 6 h`, leaves `attempts` unchanged and logs WARNING `llm.cost_cap_hit` — the row waits for the daily reset and never reaches `failed`. This is the whole retry system: two columns and one function.

### 9.5 Backfill (manifest §6.1)

`cli backfill <slug> [--count N]` (default `content.backfill_count`, 10–20 for the Phase 0 demo): `latest_items(limit=N)` via the uploads playlist (1 unit) → `ingest_item(..., allow_backlog=True)` → the CLI returns; the worker runs pre-onboarding items to `analyzed` (with the sentiment produced at backfill time instead of at `T−2h`) and creates no mailing, while an item published after `source.created_at` that the poll has not seen yet is ingested as a normal upload and mailed. `cli status` shows progress. Summary pages — with sentiment box — exist from day one; the confirmation page links to the newest one (rule in §10).

## 10. Web surface: routes and pages

Three areas in one app (manifest §5.1). All pages: one font family, one accent colour (the creator's on fan pages, ours on the landing page), real labels, keyboard-usable, contrast-checked (manifest §5.5). Every state-changing link from an e-mail lands on a confirmation page and acts on POST — corporate and Gmail link scanners prefetch GET links.

| Route | Area | Method | Behaviour |
|---|---|---|---|
| `/` | A | GET | Landing page from `landing.html`: promise + "Gespräch vereinbaren" button, three steps, a real example mail (static snapshot `partials/example_mail.html`, produced once by `cli demo-mails` from a pilot video), price tiers written in the template (numbers from the owner; nothing else consumes them), feature preview from `config/roadmap.toml` (`[[features]]` with title/benefit/status: live / in progress / planned), trust section, FAQ (manifest §5.5). |
| `/kontakt` | A | POST | Rate-limited; relays the message to `support_email`; HTMX inline confirmation. |
| `/impressum`, `/datenschutz` | A | GET | Static templates; text provided by the owner (must mention YouTube API services and Google's privacy policy). |
| `/health` | ops | GET | `{"status": "ok"}` after a `SELECT 1`; Render health check (without it Render only probes the TCP port). |
| `/k/{slug}` | B | GET | Sign-up page in the creator's branding: logo, name, greeting, three sentences, one e-mail field, one button (manifest §5.1). Unknown slug → 404 page. |
| `/k/{slug}` | B | POST | Rate-limited. Validates and normalises the address, then by subscription state: none or `unsubscribed` → row becomes `pending` with a fresh `confirm_token` and `confirm_expires_at`; `pending` → same, token refreshed; **`confirmed` → nothing changes** (status, tokens), only the confirm mail is sent again — its link lands on the "Dabei!" page. The public form can therefore never demote a fan. A subscriber blocked for `complaint` gets no mail at all; one blocked for `bounce` gets the confirm mail (if it bounces again, nothing changes). Independently of the IP limit, at most one confirm mail per address per `web.confirm_resend_minutes`, checked against `subscriptions.confirm_sent_at`: the IP limit alone lets one attacker drive thousands of confirm mails a day at a third party's mailbox, and those spam complaints land on the sending subdomain the whole platform shares (manifest §11). A throttled request changes nothing and answers normally. Always answers "Schau in dein Postfach" (no enumeration). |
| `/k/{slug}/bestaetigen/{token}` | B | GET | Looks the subscription up by `confirm_token`; `pending` and not expired → `confirmed`, `confirmed_at = now`, and a `bounce` block on the subscriber is lifted (the mail got through); already `confirmed` → no-op. Both show the branded "Dabei!" page with a link to the newest summary page, if any — *newest* = the appearance with the latest `published_at` whose status is `analyzed` and which either `is_backfill` or has a mailing in `sent`; open, `stopped` and `cancelled` mailings are excluded, so the page can never hand out a summary before the list receives it or after the creator stopped it (manifest §3.1 "Original zuerst"). The token is **kept** (confirming is idempotent, so a scanner prefetch followed by the real click shows the same page); expired → page with a new sign-up link. Confirm stays GET (a prefetch confirming a sign-up the person requested is acceptable and common). |
| `/abmelden/{token}` | B | GET | One-button confirmation page. |
| `/abmelden/{token}` | B | POST | Unsubscribes that subscription (per creator; manifest §7.7); also the RFC 8058 one-click endpoint (form-encoded `List-Unsubscribe=One-Click`). Always 200. |
| `/s/{view_token}` | B | GET | "Online ansehen" page: creator branding, the **full** summary — the `detailed` block, independent of the creator's mail variant (shared partial) — sentiment box, video link, "Auch abonnieren" link to `/k/{slug}`, the platform footer partial with the "Automatisch erstellt … kein Ersatz für das Original" notice and Impressum/Datenschutz, `X-Robots-Tag: noindex, nofollow` + meta robots, no navigation, no archive (manifest §3.1, §5.1, §7.9). `unavailable` → 410 page. Otherwise the page renders as soon as a `summary` analysis exists, independent of mailing state: the token is the only gate (256 bit, §13) and circulates only through sent mails, the creator preview and the confirmation-page link, so the preview's "Online ansehen" link works before send. `# ponytail: no per-state visibility check; add one if tokens ever leave those three channels.` The page deliberately does **not** mirror `creator.email_variant`: manifest §7.6 names the third variant "Teaser mit Volltext online", so a teaser mail's "weiterlesen" link must arrive at the full text — a page mirroring the variant would show the same teaser plus a link to itself, and the full summary would exist nowhere. The variant governs the mail only. |
| `/creator/login` | C | GET/POST | E-mail form; POST rate-limited; if the address belongs to a creator, sends a magic link (`magic_link_minutes`, hashed token in DB). Always the same response. |
| `/creator/login/{token}` | C | GET | Renders a one-button "Anmelden" page (does not consume the token). |
| `/creator/login/{token}` | C | POST | Validates hash + expiry, clears the token (single use), sets the session cookie, redirects to `?next=` (settings by default; the OAuth start during onboarding). |
| `/creator/einstellungen` | C | GET/POST | Session required. Form: delay (within min/max), min length, variant (radio with a one-line description each; real previews via `cli demo-mails --send-to`), greeting, farewell (plain text, ≤ `max_custom_text_chars`), logo URL, accent colour, reply-to. Saving applies the reschedule rule from §9.2 and shows a HTMX confirmation. Also shows: list size, OAuth status with a "YouTube verbinden" button, the sign-up link to copy. |
| `/creator/abonnenten.csv` | C | GET | Session required. `email,confirmed_at` of confirmed subscriptions (manifest §7.9). |
| `/creator/youtube/verbinden` | C | GET | Session required. Stores a random `state` in the session and redirects to Google (§8.1). |
| `/creator/youtube/callback` | C | GET | Checks `state`, exchanges the code, verifies the granted channel matches the source (`channels.list?mine=true`, 1 unit), stores the encrypted refresh token, clears `oauth_needs_reconsent`. |
| `/creator/abmelden` | C | POST | Ends the session. |
| `/m/{stop_token}/stoppen`, `/m/{stop_token}/verschieben` | C | GET → confirm page, POST → action | Valid only while the mailing is in `MAILING_STOPPABLE`; the token is the credential, single-purpose, rotated on postpone and reschedule, dead once the mailing is sent. The POST is the same conditional update (`… WHERE stop_token = :token AND status IN MAILING_STOPPABLE`); 0 rows → the page says the mail is already being sent (or was already stopped), never "gestoppt". Past the postpone cap the page offers only "stoppen". |
| `/webhooks/resend` | hooks | POST | Raw body; verifies the `svix-*` signature (HMAC-SHA256, 5-minute window, any of the `v1,` signatures); `email.bounced` (Permanent) / `email.complained` → `UPDATE subscribers SET blocked_at = COALESCE(blocked_at, now()), blocked_reason = COALESCE(blocked_reason, :reason) WHERE email = :email`; every other event ignored. No dedup table: writes are set-to-value, so at-least-once delivery and dashboard replays are no-ops. Always 200. |

Onboarding itself (contract, OAuth link, branding) runs by conversation and CLI in the MVP (manifest §5.1 C): `cli onboard --slug --name --email --channel-id` creates creator + source, resolves the channel (title, avatar as default logo) and prints the sign-up URL; the creator logs in himself via `/creator/login` with the onboarded `contact_email` and connects YouTube from the settings page; `cli backfill <slug>` processes the back catalogue.

## 11. E-mail: variants, framing, deliverability

Implements manifest §7.6 exactly.

**Fixed frame (platform fingerprint)** in `email/base.html`: sender display name `"{creator} via {product}"`; subject `"{creator}: {video title}"`; header with logo, name, accent colour and the fixed line "Zusammenfassung für Abonnenten von {creator}"; the creator's greeting; the variant body; the creator's farewell; the platform footer partial: "Du bekommst diese Mail, weil du dich am {confirmed_at} über {base_url}/k/{slug} für die Zusammenfassungen von {creator} eingetragen hast. Automatisch erstellt mit {product} — kein Ersatz für das Original." followed by Abmelden · Online ansehen · Impressum · Datenschutz. The same footer partial renders on the summary page.

**Variants** are blocks in `partials/summary_body.html` selected by name (compact: two-sentence core message, 3–5 key points with jump links, one quote, sentiment box, video link, < 300 words; detailed: sections with key points each; teaser: core message + quote + "weiterlesen" to the online page, which always shows the full text — manifest §7.6 "Teaser mit Volltext online", see §10), all rendered from the same `Summary` — switching the variant on the settings page applies instantly, without re-summarising, to every mailing that has **not yet been previewed**; a previewed mailing keeps the variant its `render_snapshot` froze (§8.4), and the `/s/` page is unaffected either way. One `summary.txt` serves all variants (core message, key points, quote, links). A fourth variant = one template block + one line in `settings.email.variants`.

**Creator texts**: greeting and farewell are plain text, length-limited, escaped by Jinja autoescape, inserted at fixed positions. No placeholders, no editor (manifest §7.6).

**Other mails**: confirm/welcome (double opt-in: the confirm button and one sentence of what comes next; no summary link before confirmation), creator preview (fan mail with the action bar on top), creator notice (one template with a `kind` switch), magic link, contact relay.

**Deliverability**: dedicated sending subdomain `mail.<domain>` in Resend (SPF on the return-path subdomain, DKIM CNAMEs, `_dmarc` with `p=none` first), open/click tracking **off** in the MVP unless the owner decides otherwise after reading the privacy implications (§20). Every mail has `List-Unsubscribe` + `List-Unsubscribe-Post`. Bounce/complaint webhooks block the address for all creators. Resend's free tier caps at 100 mails/day and allows sends only to the account owner's address until the domain is verified — DNS first, Pro plan before the list passes ~100 subscribers.

## 12. Logging, observability, cost control

Manifest §7.8 "Beobachtbarkeit" and the owner's explicit requirement for important, transparent log files.

- **structlog** configured in `app/log.py` at process start (web, worker, CLI) before any logger is used: `merge_contextvars` first, ISO UTC timestamps, level, logger name, `dict_tracebacks`; renderer `JSONRenderer` when `settings.logging.json`, else `ConsoleRenderer(colors=sys.stderr.isatty())` — the setting alone picks the format, the TTY only decides colour. Stdlib loggers (`uvicorn`, `sqlalchemy.engine` at WARNING, `httpx`) are routed through `ProcessorFormatter` so every line has the same shape. Optional `RotatingFileHandler` when `settings.logging.file` is set (local development; on Render stdout is the log stream).
- **Context**: the request-id middleware binds `request_id`, `path`, `creator_slug` (when resolvable); the worker binds `step`, `attempt`, `appearance_id` / `mailing_id` / `creator_id` before the first log line of a step. Identify people by ids, never by e-mail address, in logs.
- **Event vocabulary** (constants in `app/log.py`, so grep works — the constants file is the authority, ARCHITECTURE.md describes only the naming scheme): `item.detected`, `item.skipped` (reason), `item.failed`, `transcript.fetched` (origin, language, is_generated, segments, chars, duration_ms), `transcript.unavailable` (reason), `llm.call` (purpose, model, prompt_version, tokens_in, tokens_out, cost_cents, duration_ms, ok), `llm.cost_cap_hit`, `mailing.scheduled` (send_at), `mailing.sentiment_ready` (comments_used), `mailing.sentiment_skipped` (reason), `mailing.preview_sent`, `mailing.batch_sent` (size, first_delivery_id), `mailing.sent` (recipients, duration_ms), `mailing.stopped` / `postponed` / `rescheduled` / `cancelled` / `failed`, `subscription.created` / `confirmed` / `unsubscribed`, `subscriber.blocked` (reason), `webhook.resend` (type, signature_ok), `feed.polled` (source, entries, new), `worker.tick` (due counts, duration_ms), `step.retry` (attempt, next_attempt_at, error), `quota.youtube` (endpoint, units).
- **Levels**: INFO for step boundaries and counts, WARNING for skips, retries, bad signatures, cost cap, DEBUG for payload sizes and provider responses (never bodies with PII), ERROR with traceback for exhausted retries → Sentry when `SENTRY_DSN` is set (`sentry-sdk` with the FastAPI and logging integrations; `send_default_pii=False`).
- **Cost control** (manifest §7.9, §11): `llm_calls` is the ledger; `assert_under_cap` refuses calls above `daily_cost_cap_cents` per creator; `cli status` prints today's cost per creator with one `SUM … GROUP BY`. YouTube quota is not counted in code (`# ponytail: per-process counters lie across web and worker; the Google Cloud console graphs quota`) — every call logs its units, so `grep quota.youtube` gives the number when needed.
- **Operational visibility without a dashboard**: `cli status` prints per creator: list size, pending/confirmed, open mailings with `send_at`, status and attempts, appearances in `failed` with `last_error`, today's LLM cost, last feed poll and cleanup run. That, the Render logs and Sentry are the MVP's monitoring (manifest: "genug, um nachts zu schlafen").

## 13. Security and data protection

Manifest §7.9 and §9 (technical part only; contracts and legal texts are the owner's).

- **Tokens**: all URL tokens from `secrets.token_urlsafe(32)` (256 bit); magic links stored hashed (SHA-256), 15 minutes, consumed on POST only; stop/postpone tokens rotate on postpone and reschedule and die with the mailing; confirm tokens expire with the pending sign-up (7 days); unsubscribe tokens are permanent per subscription (must always work).
- **Webhooks**: Resend signature on raw bytes with constant-time compare, 5-minute replay window; every write is set-to-value, so replays are harmless; always 200.
- **OAuth**: only the refresh token is stored, Fernet-encrypted with `MultiFernet` (rotation supported); access tokens are held in memory for the call; `invalid_grant` marks the source for re-consent and notifies the creator; `state` in the session. Redirect URIs must be HTTPS on a real domain (or `localhost`). The Google Cloud project must be **verified for the sensitive scope** before the pilot's grant can outlive 7 days (Testing status expires refresh tokens after 7 days) — a task in M0, not an afterthought (§17, §19). Revocation is done by the creator in his Google account; `invalid_grant` handling covers it.
- **Sessions**: signed cookie (`SessionMiddleware`, `HttpOnly`, `Secure` in prod, `SameSite=Lax`), 24 h; state-changing creator forms are POST from same-site pages (Lax cookie is the CSRF defence; no third-party embedding).
- **Rate limits**: slowapi on sign-up, magic-link request, contact form; uvicorn `--proxy-headers --forwarded-allow-ips='*'` on Render so the real client IP is used.
- **Data minimisation**: no raw comments stored, no IPs, unconfirmed sign-ups deleted after 7 days, unsubscribed subscriptions after 30 days, deliveries keep only `sent_at`; CSV export limited to e-mail + confirmation date; deletions by FK cascade with one SQL statement per case in the runbook (creator after the contractual grace period, a fan on request).
- **Visibility**: summary pages send `X-Robots-Tag: noindex, nofollow` and a meta tag, are not in any sitemap, and 410 when the video is gone.
- **Secrets**: never in the repo; `.env` is git-ignored; Render `sync: false` for all keys; `bifrost.json` references keys via `env.`; Bifrost runs as a Render **private service** (not internet-reachable) with `enforce_auth_on_inference: true` + one virtual key (declared in `bifrost.json` with `value: "env.LLM_GATEWAY_KEY"` and an explicit `allowed_models`, without which every request is refused with `model_blocked`) and a setup token from `BIFROST_SETUP_TOKEN`, so neither the inference routes nor the bundled web UI are open. **Governance needs a config store** — §18's file-only note was wrong, see there — so the service gets a small disk. The go-live checklist includes a smoke test that a request without the key gets 401.
- **Dependencies**: exact pins in `uv.lock`; `uv sync --locked` in Docker and CI.

## 14. Testing strategy

Manifest §10: "jede Aufgabe ... mit einem Test, der zeigt, dass sie funktioniert". House rules: testable code, and `uv run pytest` green before anything counts as done.

- **Unit tests** (no I/O, fast): Atom feed parsing from fixtures; Resend signature verification (known-good vectors); ISO-8601 duration parsing; SRT parsing; comment filter; `compute_send_at`, `next_mailing_step` and `retry_at` across edge cases (delay reduced below elapsed time, worker down across `T` — preview must still get its full stop window, postpone at the cap, premiere with `published_at` weeks in the past → `send_at ≥ now + min_delay_hours`); two attempts of one preview with `send_at` pushed in between yield the same idempotency key, a rotated token a new one; a mailing whose creator changes variant and greeting after `preview_sent` renders byte-identically from its `render_snapshot` (§8.4); settings loading and validation errors (including a model without a price entry); template rendering of all three variants with and without sentiment (snapshot the text part), footer notice present in mail and page; cost computation; `OutgoingEmail` composition (sender, reply-to fallback, headers, idempotency keys).
- **Integration tests** (Postgres from `docker compose`, `DATABASE_URL_TEST`, one transaction per test rolled back; `set_services()` with fakes): ingest twice → one appearance; full chain detected → analyzed by calling `run_due_steps(now)` with `FakeTranscriptProvider` + `FakeLLMGateway`; premiere stays `detected` and enriches on the next run; DOI flow through `TestClient` (sign-up → confirm mail captured by `FakeEmailClient` → confirm → CSV export contains the address); already-confirmed re-signup resends the confirm mail; unsubscribe GET/POST; mailing state machine driven by `run_due_steps` with a stepped clock (`now` is a parameter everywhere); **exactly-once**: `send` interrupted after the first batch (fake raises) and re-run → each subscription has exactly one `sent_at`; two `send` runs started concurrently → one delivery per subscription; bounce webhook blocks the subscriber and later mailings exclude him; a replayed webhook changes nothing; delay change reschedules only when the value changed and rotates the stop token; stop link blocks the send; stop committed between `send`'s load and its `sending` write (the fake `videos.list` commits the stop from a second session) → nothing sent, `mailing.transition_lost` logged, the same for postpone vs `send_preview`; postpone shifts, caps, rotates the token and refreshes sentiment; video made private before send → cancelled; magic link: GET twice does not invalidate, POST once does; backfill creates no mailings but writes a sentiment, and a post-onboarding upload ingested by `backfill` is still mailed; a bounced address that confirms again is unblocked, a complained one gets no mail; cleanup deletes pending and unsubscribed rows, marks a private sent video unavailable and a deleted backfill video too (its `/s/` page then answers 410); the recipient snapshot at send start includes neither a `pending` subscription, nor one unsubscribed after the mailing was scheduled, nor one confirmed after the snapshot was taken — exactly one `deliveries` row and exactly one recipient at the fake.
- **Fakes** in `tests/fakes.py` duck-type the real classes; no `unittest.mock` patching of internals.
- **Prompt regression** (manifest §8 "Prompts sind Produkt"): `cli eval-prompts` runs the real gateway on the 3–5 fixed transcripts in `tests/fixtures/transcripts/` and writes the rendered mails to `out/` for eyeballing; run manually before changing a prompt version; not part of CI (costs money).
- **CI**: GitHub Actions workflow with a Postgres service container: `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`. Runs on every push and PR.

## 15. Local development and deployment

### 15.1 Local (manifest §7.1 "Lokal startet alles mit docker compose up")

`docker-compose.yml`: `postgres:17` (volume), `maximhq/bifrost:v2.1.1` (mounts `config/bifrost.json` to `/app/data/config.json`; the official image already listens on `0.0.0.0`; env `ANTHROPIC_API_KEY`, `LLM_GATEWAY_KEY`, `BIFROST_SETUP_TOKEN` from `.env`; `BIFROST_SKIP_WRITE_CHECK=1` because the mount is read-only; a Postgres init script creates `app_test` for `DATABASE_URL_TEST`), `web` and `worker` built from the `Dockerfile` with the source mounted for reload (`uvicorn --reload` / `python -m app.worker`). `make`-free: `uv run` commands are documented in the README (`uv run alembic upgrade head`, `uv run app <command>`, `uv run pytest`). Upload detection locally: `cli poll <slug>` or the worker's periodic poll; no tunnel needed.

### 15.2 Production (Render Blueprint)

`render.yaml` (single environment, one region, private network):

- `web`: `runtime: docker`, `dockerfilePath: ./Dockerfile`, `plan: 0.5c-512mb` (paid plans are required for `preDeployCommand`), `preDeployCommand: uv run alembic upgrade head`, `dockerCommand: uv run uvicorn app.web.server:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`, `healthCheckPath: /health`, `autoDeployTrigger: commit`.
- `worker`: `type: worker`, same Dockerfile, `dockerCommand: uv run python -m app.worker`.
- `bifrost`: `type: pserv`, `runtime: image`, `image.url: docker.io/maximhq/bifrost:v2.1.1` (linux/amd64, ≈ 86 MB), config injected via `BIFROST_CONFIG_B64` (official Render guide pattern), `ANTHROPIC_API_KEY`, `LLM_GATEWAY_KEY` and `BIFROST_SETUP_TOKEN` `sync: false` (`LLM_GATEWAY_KEY` also on web and worker via `fromService`), `APP_PORT`/`PORT` = 10000, health `/health`, and a **1 GB disk at `/app/data`** for the config store the governance handler requires (§18). `logs_store.enabled=false` stays: the request log is not wanted, and our own `llm_calls` ledger is the record that matters. Image services do not redeploy on tag changes — bumping the version is a YAML edit; Bifrost migrations are one-way, another reason to keep it stateless.
- `databases`: `plan: 0.1c-256mb`, `postgresMajorVersion: "17"` (must be explicit; the default is the newest major and cannot be changed later), `ipAllowList: []`; `DATABASE_URL` via `fromDatabase.connectionString` (internal URL, `postgresql://` scheme; normalised in `config.py`). Connection limit is 100 on this plan; the SQLAlchemy pool of 5 per process is far below.
- Secrets as `sync: false` env vars (prompted only on the first Blueprint apply and ignored on later syncs — add new ones in the dashboard); `SECRET_KEY` via `generateValue: true`; `LOGGING__JSON=true`. Blueprint sync runs only on pushes that change `render.yaml`; code pushes deploy via each service's own trigger.
- Domain: `<domain>` → web service; `mail.<domain>` records in the DNS provider as printed by Resend; `_dmarc` TXT.

Deploy = `git push` to `main`. Rollback = Render "rollback to previous deploy". The runbook `docs/runbooks/operations.md` lists the one-time setup (Google Cloud project + OAuth consent + verification, YouTube API key, Resend domain, DNS, Render Blueprint, Sentry) and the recurring checks (quota, costs, failed rows).

## 16. Documentation deliverables

One authority per topic, everything else links there:

- **Configuration**: the comments in `config/settings.toml` and `.env.example`. README and ARCHITECTURE only point to them.
- **Layout and architecture**: `docs/ARCHITECTURE.md` (English): "Where to find what" entry section, the module cut with the two abstractions, the data model, the two transition tables, the worker loop and retry rule, the exactly-once mechanics, the transcript provider chain and its legal notes, the e-mail frame, the log naming scheme, and a **Decisions** section (one short entry each: modular monolith; transcript providers and why no Whisper in the MVP; LLM gateway and OpenAI-compatible client; status-driven worker loop instead of a queue; poll-only trigger). No separate ADR folder — one place.
- **Log events**: the constants in `app/log.py`.
- `README.md` (German): what the platform does in five sentences, folder map, local start in five commands, the CLI, link to this plan and to `docs/ARCHITECTURE.md`, how to run tests and lint.
- `docs/runbooks/onboarding.md`: the exact steps to onboard a creator (contract, `cli onboard`, branding, creator login + YouTube connect, `backfill`, first preview) — manifest §3.1 "Wie der Creator das erlebt".
- `docs/runbooks/operations.md`: one-time setup, deploy, DNS/e-mail, quotas, cost review, deletions (creator, fan), incident cheatsheet (mailing stuck in `sending`, rows in `failed`, OAuth re-consent, IP blocked).
- Docstrings (numpy style) on every public function and Protocol.

## 17. Implementation steps (milestones)

Each milestone is deployable, has a test that proves it, and is small enough for one or two working sessions (manifest §10 "kleine Schritte"). Tick the boxes as work completes. Effort is in focused sessions (≈ half a day each), a guide, not a promise (manifest: no calendar).

**Marking.** `[x]` is built *and* covered by a passing test. `[ ]` is not started.
A **Status** line under each milestone records when it was finished and what could
not be verified — a "Done when" that needs a real API key or a real channel stays
open until it has been run against one, however green the tests are.

### M0 — Foundation (≈ 3 sessions)
- [x] `uv init`, `pyproject.toml` with pinned dependencies and ruff/pytest config, `.python-version`, `.gitignore` additions (`.env`, `logs/`, `out/`).
- [x] `config/settings.toml` + `app/config.py` (`Settings`, derived values, validation, `get_settings`). Test: TOML loads, env overrides, invalid delay fails at start-up, a configured model without a price entry fails at start-up.
- [x] `app/log.py` (structlog, JSON/console by setting, optional file, stdlib routing, event constants). Test: a log call renders the bound context.
- [x] `app/db/engine.py`, `app/db/models.py` (all tables and enums from §7), Alembic env, first migration. Test: `alembic upgrade head` on an empty DB, `downgrade base` works.
- [x] `app/jinja.py`, `app/services.py` (with `set_services`), `app/worker.py` loop skeleton (runs nothing yet), `app/web/server.py` with `/health`.
- [x] `Dockerfile`, `docker-compose.yml` (postgres, bifrost, web, worker), `.env.example`, `render.yaml`, GitHub Actions CI.
- [x] `README.md` (German) updated, `docs/ARCHITECTURE.md` skeleton with the Decisions section.
- [ ] **External setup started now because of lead times:** Google Cloud project, YouTube Data API key, OAuth client (web), consent screen with `youtube.force-ssl`; domain decision; Resend account + sending subdomain; Render account; Webshare residential proxy account.
- **Done when:** `docker compose up` serves `/health`, CI is green with the tests above.
- **Status: done, 2026-09-11.** `docker compose up` serves `/health` with a real `SELECT 1`; `alembic upgrade head` and `downgrade base` both verified against PostgreSQL 17. The external-setup box stays open: the LLM-provider and Resend accounts exist, the Google Cloud project, the YouTube API key, the domain, the Render account and the Webshare proxy do not. CI has not run yet — the repository has no commit on this branch.

### M1 — YouTube source and feed poll (≈ 2 sessions)
- [x] `sources/base.py`, `sources/youtube/data_api.py` (videos.list, channels.list, playlistItems.list, commentThreads.list; `QUOTA_UNITS` log), `feed.py`, `connector.py`.
- [x] `app/errors.py`; `jobs/schedule.py` — the pure, DB-free maths of §8.5, pulled forward from M6 because the worker's retry rule needs `retry_at()` here and M3 needs `compute_send_at()`; `jobs/steps.py`: `ingest_item`, `enrich`; `poll_feeds` periodic job; `run_due_steps`/`run_periodic_jobs` in the worker with the retry rule (§9.4); `cli onboard --slug --name --email --channel-id` (creator + source, title and avatar-as-default-logo via `channels.list`, prints the sign-up URL), `cli process <slug> <video_id>`, `cli poll <slug>`.
- [x] Tests: feed fixture parses; duration regex; ingest idempotency (two inserts → one row); poll ignores pre-onboarding entries while `backfill` ingests them as backfill and post-onboarding ones as normal; enrich sets `skipped_short` / `unavailable` / `enriched` / stays `detected` for a premiere from `FakeYouTubeConnector` items, and a premiere that went live is `enriched` with `published_at = actualStartTime`; `retry_at()` ladder arithmetic and retry bookkeeping after a temporary error; `enrich` leaves a row in `detected` when the duration is missing or `0`, and clears `is_backfill` when the corrected `published_at` is at or after `source.created_at`; onboarding creates creator + source with the channel avatar as default logo.
- **Done when:** after `cli onboard` for the pilot channel, `cli poll` creates appearances with correct durations and skips shorts, and the worker loop picks them up.
- **Status: built and tested, acceptance open, 2026-09-11.** Every box is covered by tests against fakes and real feed fixtures, including the retry ladder and the two `enrich` edge cases the review added. The acceptance criterion itself needs a YouTube API key and the pilot's channel id, neither of which exists yet, so no appearance has ever been created from live data.

### M2 — Transcript layer, creator login, OAuth (≈ 3 sessions + spike)
- [ ] **Spike (30 min, on an own channel):** does `captions.download` return the ASR track for the owner? Record the answer in ARCHITECTURE.md → Decisions. It decides whether the official provider covers auto-captions or only uploaded ones.
- [x] `transcripts/base.py`, `youtube_unofficial.py` (proxy config, timeout session, exception mapping), `youtube_official.py` (captions via `data_api.py`, SRT parser), `service.py` (chain).
- [x] Magic-link login: `/creator/login` GET/POST, `/creator/login/{token}` GET (page) / POST (consume, session), `deps.current_creator`, `magic_link` template — pulled forward from the creator area because the OAuth start needs a session.
- [x] Minimal delivery slice, pulled forward from M4 because this milestone already ships two mail-sending features: `delivery/email_client.py` with `ResendClient.send()` only (no batch, no 429 ladder, no signature check), `delivery/render.py` with `render_notice_mail` and `render_magic_link_mail`, and `templates/email/base.html`. Without it M2's own test has no `OutgoingEmail` to capture and the magic link cannot be delivered.
- [x] `sources/youtube/oauth.py` + `/creator/youtube/verbinden` and `/callback`; `transcribe` step; `notify_creator` + `creator_notice` template.
- [x] Tests: SRT parser; chain skips official without grant; permanent vs temporary mapping; transcript persisted with origin; a second `transcribe` attempt on the same row issues no captions call (§8.2); notice mail captured by the fake on permanent failure; magic link GET twice keeps the token, POST consumes it; OAuth callback rejects a wrong state and stores an encrypted token for a matching channel.
- **Done when:** `cli process` followed by the running worker stores a transcript for a pilot video locally (unofficial) and, once the pilot has connected YouTube, via the official provider.
- **Status: built and tested, acceptance open, 2026-09-11.** Both providers, the chain, the magic-link login and the OAuth round trip are covered by tests; the library's exception names and constructor signature were checked against the installed package rather than trusted. No transcript has been fetched from YouTube itself. **The spike is blocked** on a Google Cloud project — until it runs, whether the official provider covers auto-generated tracks is unknown, and §19's mitigation stands.

### M3 — Analysis (≈ 2 sessions)
- [x] `analysis/llm.py` (`BifrostGateway`, `Completion`, ledger + cap functions), `schemas.py`, prompts v1 (summary, sentiment), `summarize.py`, `comments.py`, `sentiment.py`; `summarize` step; `delivery/mailing.py` with the create/schedule function only, pulled forward from M6 — the step creates the mailing with `compute_send_at()` from M1's `schedule.py`, or for backfill produces the sentiment right away.
- [x] `cli eval-prompts` + three sample transcripts (one German talk, one English interview, one very short) under `tests/fixtures/transcripts/`.
- [x] Tests: comment filter cases; gateway parses JSON and retries once on validation error (fake HTTP); cap raises with a fake gateway and the row waits without counting an attempt; `llm_calls` written on failure too, and a step that raises *after* a successful completion still leaves its `llm_calls` row behind (§8.3); summarize creates a mailing with the right `send_at`, and for backfill no mailing but a `sentiment` analysis from the fake connector + fake gateway.
- **Done when:** a pilot video has a `Summary` and a `Sentiment` in the DB and `eval-prompts` output reads well to the owner.
- **Status: built and tested, acceptance open, 2026-09-11.** Gateway, schema retry, cost ledger, daily cap and the day boundary in the product's timezone are covered; `eval-prompts` runs end to end over the three sample transcripts. It has never spoken to a real model: `ANTHROPIC_API_KEY` is still empty, so nobody has read a real summary and judged the prompts.

### M4 — Output: mails, summary page, sign-up page, minimal landing (≈ 3 sessions)
- [x] Completes the delivery layer M2 began: `ResendClient.send_batch`, 429 handling and the webhook signature check; `render.py`'s summary, preview and contact composers; the remaining templates under `templates/email/` (summary, creator_preview, contact) and the shared partials; `css_inline`. The confirm/welcome template belongs to M5.
- [x] `/s/{view_token}` page (410 for unavailable), `/k/{slug}` GET page in the creator's branding, `landing.html` minimal (promise, example mail snapshot, contact link) and the base layout + `style.css`.
- [x] `cli demo-mails <slug> [--send-to]` renders the three variants for the newest analysed videos to `out/` and optionally sends them; `cli backfill --count`.
- [x] Tests: all variants render with/without sentiment; footer contains the notice, unsubscribe and online link (mail and page); headers include `List-Unsubscribe*`; subject/sender format; page sends `noindex`; the `/s/` page of a creator on the `teaser` variant renders the full sections block and no "weiterlesen" link (§10); sign-up page renders branding.
- **Done when — Phase 0 gate (manifest §10):** the owner can show the pilot candidate real mails in all three variants, the summary pages and his branded sign-up page, from 10–20 of his own videos.
- **Status: built and tested, gate open, 2026-09-11.** `cli demo-mails` produces all three variants as HTML and plain text, and every page answers correctly in the running container, 410 for a deleted video included. The gate needs the pilot's own videos, which needs M1's and M3's acceptance first. Three pieces of M4 are deliberately without a caller until M5 and M6: `send_batch`, the webhook signature check, and `POST /k/{slug}`.

### M5 — Fan area: double opt-in, unsubscribe, bounce webhook (≈ 2 sessions)
- [ ] `/k/{slug}` POST with slowapi and HTMX inline response; confirm route + page; unsubscribe GET/POST incl. one-click; confirm/welcome template.
- [ ] `/webhooks/resend` (signature, bounce/complaint → block).
- [ ] `cleanup` periodic job (pending and unsubscribed retention; the video re-check parts come in M6).
- [ ] Tests: DOI flow end to end with `TestClient`; no enumeration (same response for new/existing); already-confirmed re-signup resends confirm; rate limit returns 429; unsubscribe affects only that subscription; webhook vectors verify, replay is a no-op, bounce blocks.
- **Done when:** the owner signs up on the pilot page, confirms, and is blocked after a test bounce (`bounced@resend.dev`).

### M6 — Scheduling and sending (≈ 3 sessions)
- [ ] `delivery/mailing.py`'s remaining lifecycle — reschedule, stop/postpone, sentiment, preview, send; create/schedule shipped in M3, `schedule.py` in M1 — plus `next_mailing_step()`; steps `prepare_sentiment`, `send_preview` (+ `creator_preview` template with the action bar), `send` (advisory lock, snapshot, batches, resume), stop/postpone routes + confirmation page, reschedule rule, conditional transitions in `mailing.py`, cleanup re-check of every `analyzed` appearance (§9.3).
- [ ] Tests: `compute_send_at`, `next_mailing_step`, `retry_at` cases incl. "worker down across T"; state machine end to end with a stepped clock; exactly-once after a simulated crash mid-send and under two concurrent runs; stop blocks; postpone shifts, caps, rotates the token and refreshes sentiment; sentiment step gives up gracefully; cancelled when the video is no longer public; the send snapshot excludes a `pending` and a just-unsubscribed subscription and a subscription confirmed after the snapshot was taken, leaving exactly one `deliveries` row and one recipient at the fake; a previewed mailing whose creator then changes variant and greeting still renders from its `render_snapshot`; cleanup marks a private sent video unavailable and a deleted backfill video too.
- **Done when:** with `min_delay_hours` and `default_delay_hours` set to 3 on a test config, a new upload arrives as a preview mail with a full stop window, then as the fan mail, without manual steps.

### M7 — Creator settings and operations (≈ 2 sessions)
- [ ] Settings page (form, validation against min/max and variants, reschedule on delay change, OAuth status + connect button, sign-up link, list size), CSV export, logout; `cli status`; `docs/runbooks/onboarding.md` and the deletion statements in `operations.md`.
- [ ] Tests: settings validation; saving a changed delay reschedules and rotates the stop token, saving a greeting does not; a variant switch changes the rendered mail of an open mailing without a new analysis; CSV content.
- **Done when:** the pilot creator changes his delay and greeting himself and downloads his list.

### M8 — Landing page and legal pages (≈ 2 sessions)
- [ ] `landing.html` complete with the seven sections of manifest §5.5, `config/roadmap.toml` + renderer, price tiers (numbers from the owner), FAQ; `/kontakt`; `impressum`/`datenschutz` templates with owner-provided text; favicon; mobile check.
- [ ] Tests: landing renders roadmap items by status; contact form rate-limited and relayed via the fake.
- **Done when:** the owner approves the page on phone and desktop; Lighthouse accessibility ≥ 90.

### M9 — Go-live (≈ 2 sessions)
- [ ] Render Blueprint applied, secrets set, domain + mail DNS verified in Resend, DMARC published, Sentry DSN, `LOGGING__JSON=true`, Bifrost 401 smoke test.
- [ ] Google OAuth verification submitted (homepage + privacy policy live are prerequisites — M8 must be deployed first); until approved the pilot re-consents weekly or the unofficial provider carries production.
- [ ] Pilot onboarding via the runbook: contract signed, `cli onboard`, branding, login + YouTube connect, `backfill`, first real preview reviewed together.
- [ ] `docs/runbooks/operations.md` complete; README final; ARCHITECTURE.md Decisions final.
- **Done when — Phase 1 live:** the first real mailing has gone out to the pilot's list exactly once and the acceptance criteria in §2 are all ticked.

Order of work is M0 → M4 (Phase 0 demo), then M5 → M7 (automation), then M8/M9. M8 can run in parallel with M5–M7 because it shares no code with the pipeline.

**Post-go-live, not MVP:** PubSubHubbub push (`sources/youtube/pubsub.py`, a verification/notification route, lease renewal, tombstone handling) — purely additive, build when a creator needs sub-hour detection; the verified hub facts stay in §18.

## 18. Verified technical facts the plan relies on

Researched against primary sources on 2026-09-09/10 (docs, repositories, live endpoints) and adversarially re-checked. Where a fact could not be confirmed it is marked and turned into a spike or risk.

**YouTube Data API / captions**
- `videos.list`, `channels.list`, `playlistItems.list`, `commentThreads.list` cost 1 unit each; default quota 10,000 units/day, resets at midnight Pacific (09:00 CEST); `search.list` lives in its own 100-calls/day bucket and is not used. Chunk `videos.list` ids at 50 (more → 400 `invalidFilters`). Quota extensions go through a compliance-audit form.
- `captions.list` = 50 units, `captions.download` = 200 units; both require OAuth with `youtube.force-ssl` (or `youtubepartner`) from the video owner; API keys and service accounts always get 403. `tfmt=srt|vtt` are safe on both the REST and discovery docs. Caption ids were reassigned in 2022 — always list before download.
- **Unconfirmed:** whether ASR (auto-generated) tracks can be downloaded by the owner. Official docs make no trackKind distinction; third-party claims of a 403 cite no primary source. → Spike in M2.
- `commentThreads.list`: `order=relevance`, `maxResults=100`, `textFormat=plainText`, `part=snippet` only; with an API key only `textDisplay` is available (`textOriginal` is author-only); `authorChannelId` may be absent; comments disabled → 403 `commentsDisabled` (a normal state, also for `madeForKids` videos); 400 `processingFailure` is retryable.
- `snippet.publishedAt` of a premiere or broadcast is the scheduling time; `liveStreamingDetails.actualStartTime` (same 1 unit when requested as a part) is the go-live time and present only once started.
- Public Atom feed `https://www.youtube.com/feeds/videos.xml?channel_id=UC…`: 15 newest entries, no duration/privacy/live info, includes Shorts, 15-minute cache; feed-level `yt:channelId` lacks the `UC` prefix, entry-level has it; `<updated>` differs from `<published>` — diff on video id. `?user=` works, `?handle=` does not (resolve handles once via `channels.list?forHandle`). The `UC→UU` uploads-playlist shortcut is undocumented but works; `channels.list?part=contentDetails` is the documented fallback.
- YouTube API Developer Policies (III.E.4): non-authorised data (comments, metadata) may be stored ≤ 30 days unless refreshed and kept consistent; derived metrics from API data are restricted; on revocation through the client's own mechanism, authorised data must be deleted within 7 days. → We do not store comments; recently mailed videos are re-checked daily by `cleanup`; open legal question on sentiment summaries (§20).

**youtube-transcript-api**
- 1.2.4 (Jan 2026), Python `<3.15`, MIT, sync `requests`, not thread-safe, no default timeout, mutates the session it is given; API `YouTubeTranscriptApi().fetch(video_id, languages=[…])` (the static `get_transcript` API was removed in 1.2.0); fetches ASR captions; cloud/datacenter IPs are widely blocked (`RequestBlocked`/`IpBlocked`) — the maintainer recommends Webshare **residential** rotating proxies (`WebshareProxyConfig`; its retry adapter replaces adapters you mounted); `PoTokenRequired` (since 1.1.0) affects a growing share of videos with no library workaround; the Android innertube client may miss manual tracks; `translate()` currently broken; single maintainer, last code release Jan 2026. Unofficial; YouTube ToS forbid automated access — grey zone, which is why it is the fallback, not the foundation (manifest §7.4).

**Google OAuth**
- `youtube.force-ssl` is a sensitive (not restricted) scope → verification required (published brand verification first, then homepage + privacy policy on the same domain, demo video in English, per-scope justification explaining why `youtube.readonly` is insufficient — captions need the write scope; Google states 3–5 or 10 business days, plan 2–4 weeks). In **Testing** status refresh tokens expire after 7 days and ≤ 100 test users. Token endpoint: `https://oauth2.googleapis.com/token` (`grant_type=authorization_code` / `refresh_token`); `invalid_grant` on revocation/expiry; a refresh may hand back a new refresh token; refresh tokens are issued only with `prompt=consent`; store tokens encrypted at rest (Google policy); redirect URIs must be HTTPS on a public-suffix domain or `localhost`. PKCE is optional for confidential web clients and not used.

**Resend**
- `POST /emails` and `POST /emails/batch` (≤ 100 per call, attachments unsupported, tags/headers supported; the SDK's "permissive" validation mode is not in the API reference), `Idempotency-Key` (24 h, 1–256 chars; **unverified:** the behaviour on a repeated key with a changed payload is not in the reference — §8.4's payload freeze makes sure the case never arises), rate limit 10 requests/s per team; 429 also for `daily_quota_exceeded`/`monthly_quota_exceeded` (test mails count too); until a domain is verified only the account owner's address can be mailed; `scheduled_at` is capped at 30 days (not used); webhooks at-least-once, unordered, replayable from the dashboard, with `svix-id/timestamp/signature` (HMAC-SHA256 over `id.timestamp.body`, base64, `whsec_` secret, 5-minute window; fixed source IPs published); free plan allows one webhook endpoint; events `email.bounced` (with `bounce.type` Permanent/Temporary), `email.complained`, `email.delivered`, `email.opened`, `email.clicked`; one-click unsubscribe headers; sending from a subdomain is Resend's own recommendation; SPF (return-path), DKIM CNAMEs, DMARC; tracking off by default and needs a tracking subdomain (plus possibly a CAA record); free tier 3,000/month capped at 100/day; Pro $20/month for 50k; test addresses `bounced@resend.dev` etc. (`suppressed@` takes no `+label`).

**Bifrost**
- Image `maximhq/bifrost:v2.1.1` (Apache-2.0, ≈ 86 MB amd64, port 8080 via `APP_PORT`, the container already binds `0.0.0.0`; near-daily releases with breaking renames in 2.x → pin); `config.json` in `/app/data` with `providers.anthropic.keys[].value = "env.ANTHROPIC_API_KEY"`; `POST /v1/chat/completions` with `model: "anthropic/<model>"`; OpenAI-shaped `usage` (`prompt_tokens`/`completion_tokens` omitted when zero, `total_tokens` always present); `response_format` json_schema passed through to the provider's structured outputs; `/health` returns 503 when a store ping fails; `logs_store.enabled=false` suppresses the SQLite request log; **corrected 2026-09-12 by running it — `config_store.enabled=false` is *not* compatible with `governance`: the container exits 1 with "failed to initialize governance handler: config store is required", so a virtual key costs a writable `/app/data`.** A virtual key also needs an explicit `allowed_models` in its `provider_configs`, or every request comes back `403 model_blocked`. Inference routes and the web UI are **unauthenticated by default** → private service + `enforce_auth_on_inference` with a virtual key (`Authorization: Bearer sk-bf-…` or `x-bf-vk`) + `setup_token`; container runs as UID 1000 and checks that `/app/data` is writable unless `BIFROST_SKIP_WRITE_CHECK` is set; migrations are one-way. Official Render guide injects config via `BIFROST_CONFIG_B64`.

**Render**
- Blueprint keys `services`/`databases`; plan ids renamed Aug 2026 (`0.5c-512mb` $7, `0.1c-256mb` Postgres $6, prices re-verified live 2026-09-10); workers/crons have no free tier; free Postgres expires after 30 days; `runtime: docker` with `dockerfilePath`/`dockerCommand`; `preDeployCommand` (paid plans only) runs before deploy for Docker and native runtimes; zero-downtime deploys for web, private services and workers (old and new instance overlap briefly); `runtime: image` for public images (no auto-redeploy on tag change); `type: pserv` for private services; `fromDatabase.connectionString` is the internal `postgresql://` URL; `healthCheckPath` (otherwise only a TCP probe); `autoDeployTrigger: commit`; Postgres default major is 18, set explicitly; `sync: false` vars are ignored on later Blueprint updates; Blueprint sync never deletes resources.

**PubSubHubbub (deferred, kept for later)**
- Hub `https://pubsubhubbub.appspot.com/subscribe`; topic `https://www.youtube.com/feeds/videos.xml?channel_id=…`; `hub.secret` → `X-Hub-Signature: sha1=<hex>` HMAC-SHA1 over the raw body; lease up to 10 days; notifications fire on upload and title/description edits, also for scheduled videos, at-least-once; deletions as `at:deleted-entry` tombstones (undocumented); callback must be public on an allowed port; the hub returned 503 "transient error" for hours on 2026-09-10 — subscribe must retry and only the verification GET confirms; renewals are verified again; no test-fire endpoint; unlisted-upload behaviour unverified; diagnostics page is public.

**Python libraries**
- pydantic-settings 2.15: `TomlConfigSettingsSource` has exactly the priority its tuple position gives it, `env_nested_delimiter="__"`. structlog 26.1: `merge_contextvars` first, bind in async middleware (anyio copies the context into the threadpool), configure before any logger is used. slowapi 0.1.10: endpoint must take `request: Request` (checked at import time); in-memory storage is per process. SQLAlchemy 2.0.52 + psycopg 3.3.5 (`postgresql+psycopg://`, `psycopg[binary]` is fine in a container), pin `sqlalchemy<2.1` (2.1 release candidates are on PyPI), sync `def` endpoints are the documented FastAPI pattern (FastAPI 0.141 / Starlette 1.6 — pin). Alembic 1.19 autogenerate does not detect renames and mishandles native Postgres enums — review every migration, use `VARCHAR` + `CHECK`. itsdangerous 2.2, cryptography 50 (Fernet/MultiFernet; expiry logic belongs in the DB). `premailer` unmaintained since 2021 → `css_inline` 0.21. uv: `uv init` creates no `.venv`/lock until the first `uv sync`; commit `uv.lock`, `uv sync --locked` in CI/Docker. procrastinate 3.9 was evaluated (works as documented) and not adopted, see §4.

## 19. Risks

| Risk | Why it is real | Mitigation in this plan |
|---|---|---|
| Unofficial transcripts blocked from Render's IPs | Documented by the library; cloud IPs are blocked | Webshare residential proxy configured from day one; temporary errors retry for ~24 h inside the 48 h minimum delay; official provider as soon as the OAuth grant exists; creator notice on permanent failure. |
| Official captions may not cover auto-generated tracks | Unconfirmed in docs, widely reported | Spike in M2; if true, the official path covers only uploaded captions and the pilot is asked to upload/auto-publish captions; the unofficial provider remains in the chain. |
| Google OAuth verification takes weeks; Testing tokens die after 7 days | Google policy | Start the verification in M0 (needs landing page + privacy policy → M8 early); weekly re-consent by the creator until approved; unofficial provider carries the gap. |
| `PoTokenRequired` / age-restricted videos have no transcript path in the MVP | Library limitation | Skip + creator notice; count occurrences in logs; revisit with Whisper in Phase 2. |
| E-mails land in spam | Kills the product silently (manifest §11) | Dedicated subdomain, SPF/DKIM/DMARC, no tracking, `List-Unsubscribe`, bounce/complaint handling, plain-text part, real reply-to. |
| Double sends after a crash or during a deploy overlap | Exactly-once is a manifest promise | `deliveries` unique constraint + snapshot at send start + `ORDER BY id` batches with stable idempotency keys + advisory lock; tested with a simulated crash and a concurrent run. |
| Late pipeline shortens the stop window | Worker down across `T`, or a rescheduled `send_at` too close | `send_preview` pushes `send_at` to at least `now + stop_window`; `send` requires `preview_sent_at + stop_window` to have passed; unit-tested. |
| Mail scanners "click" action links | Corporate and Gmail link scanners prefetch GET | Stop, postpone, unsubscribe and magic-link login act on POST behind a confirmation page; one-click unsubscribe is POST by specification. |
| LLM cost runaway | Retries × long transcripts | Per-creator daily cap, cost ledger, single-call ceiling on transcript length, bounded retries. |
| Upload detected late | Poll every 6 h, feed shows 15 entries | 6 h ≪ 48 h minimum delay; `cli poll` for manual runs; push notifications are the documented post-go-live upgrade. |
| Bifrost is an extra moving part for one provider | The gateway is a manifest decision (§8, §13) | Stateless container, pinned version, private network; the app's client is plain OpenAI-compatible HTTP, so removing or replacing the gateway is a URL change. |
| Legal: sentiment summaries as "derived data" from API comments; storage limits | YouTube API policies III.E.4 | No raw comments stored; summaries only; recently mailed videos re-checked daily; question flagged for the lawyer (§20) before launch. |
| Pilot churns | Manifest §11 | `cli status` shows open mailings and failures; a second channel is only configuration. |

## 20. Open questions

To be answered by the owner; the plan proceeds with the stated assumption until then.

1. **Domain and product name** (manifest §15): assumption `Klartext` / `klartext.tld` placeholders in `settings.toml`; Resend subdomain, OAuth homepage and DMARC need the real domain before M9.
2. **Pilot channel id** and contact e-mail for `cli onboard`; whether the pilot will upload captions if the ASR spike is negative.
3. **Price tiers and example mail** for the landing page (manifest §4.3 numbers are hypotheses); FAQ text; Impressum/Datenschutz text (must mention YouTube API services and Google's privacy policy).
4. **Open tracking**: off by default in this plan (privacy, deliverability). Turn on (tracking subdomain, privacy-policy sentence) to measure the manifest §6.3 open-rate criterion, or measure via the Resend dashboard only?
5. **Legal check** (manifest §9): sentiment summaries derived from API comments versus YouTube API policy III.E.4.h; whether stored video titles/durations fall under the 30-day rule (the daily re-check of recently mailed videos is the assumed answer); processor vs joint controller for the fan list (affects the privacy text, not the code).
6. **Webshare proxy budget** (≈ $10–30/month) — needed as soon as unofficial transcripts run in the cloud.
7. **Postpone step**: 24 hours assumed; the manifest only says "verschieben".
8. **A mailbox for the domain.** The plan sends but never receives. `support_email` is the reply-to fallback (§8.4) and the sole recipient of the `/kontakt` relay (§10) — the landing page's only inbound sales channel (manifest §5.5). Needed before M9: a mailbox for the apex domain and its MX record, or Resend inbound on a subdomain. Until then set `SUPPORT_EMAIL` to an existing address; with no MX, every contact mail hard-bounces against the sending reputation §11 protects. Who reads it goes into `docs/runbooks/operations.md`.
9. **Unsubscribe during an in-flight send.** §9.2's recipient set is a snapshot taken at send start, so someone who unsubscribes while a mailing is sending still receives that one mail — seconds of exposure normally, hours if the send is retrying. Assumption: acceptable, and the alternative (re-filtering each batch) breaks the payload freeze §8.4 relies on. Confirm.

## 21. Review section

Filled in during implementation: what was built per milestone, deviations from this plan and why, test evidence, lessons for the next plan.

- M0: —
- M1: —
- …
