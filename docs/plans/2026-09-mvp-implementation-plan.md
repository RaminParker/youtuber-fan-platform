# MVP Implementation Plan — Creator Platform (Phase 0 + Phase 1)

> **Progress:** M0–M4 built, tested and reviewed (2026-09-11); M5 built, reviewed and hardened (2026-09-18, live webhook acceptance moved to M9); M6 built, accepted live and hardened after a code review (2026-09-20). *Re-planned 2026-09-27:* **M6a** (Amazon SES replaces Resend — [`2026-09-ses-migration-plan.md`](2026-09-ses-migration-plan.md)), **M6b** (lean platform: no LLM gateway, one Render service, backups — [`2026-09-lean-platform-plan.md`](2026-09-lean-platform-plan.md)), **M6c** (failure handling, operator console, daily operator mail, safe deploys — [`2026-09-operations-plan.md`](2026-09-operations-plan.md)), **D** (the design as HTML drafts, approved by the owner), then M7, M7a, M7b ([`2026-09-billing-plan.md`](2026-09-billing-plan.md)), M8, M9 and **M10** (product video). None of them started. **Next step: M6a.** Per-milestone detail in §17.
>
> **Status:** draft for review · **Date:** 2026-09-10, revised 2026-09-11 after a full review against the manifest (14 findings; marked "§R" in `implementation-notes.html`), revised 2026-09-27 after the owner's re-planning and two adversarial reviews against the code · **Source of truth:** `docs/manifest/creator-plattform-manifest.md` (the manifest). Every task below cites the manifest section it implements. What is not in the manifest is not built. Where this plan deviates from the manifest, the manifest is updated in M6b (§17).
>
> **Scope:** the MVP as defined in manifest §6 (Phase 1), reached through the Phase 0 demo (manifest §10). Product 2 (briefings), the podcast connector, Whisper, checkout and subscriptions, fan login and dashboards are explicitly out of scope. **Everything deferred beyond the MVP — by a decision in this plan, a review, or a `# ponytail:` shortcut in the code — is collected in `docs/backlog.md`, each item with the trigger that justifies building it.**
>
> **Decisions taken with the owner on 2026-09-27** (every changed passage below is marked "*Changed 2026-09-27*"):
> - **Resend is removed completely** — code, configuration, tests and current docs; no dead code, and a grep gate proves it. Mail goes **directly to Amazon SES (eu-central-1) over SMTP** with the standard library (≈ $0.11 per 1,000 mails, no fixed fee, against ≈ $0.90 per 1,000 and a $20 plan). Bounces, complaints and per-mail delivery status arrive as signed SNS notifications at `/webhooks/ses`. **Listmonk was evaluated and rejected** (SES plan §2). Specification: **`2026-09-ses-migration-plan.md`**, milestone **M6a**.
> - **"Exactly once" becomes "never twice".** SES has no idempotency key; a crash inside one SMTP exchange leaves one recipient uncertain. Owner decision: rather no double mail — that recipient is not sent again; the case is logged and countable (SES plan §5).
> - **Hosting target ≈ €10 a month.** Chosen: **Render, Frankfurt, one web service running web and worker, plus the smallest Postgres — ≈ €11.50 a month**; backups go encrypted to Backblaze B2 (free below 10 GB); monitoring on free plans. The comparison with VPS, other PaaS and the hyperscalers is in §15.2.
> - **The LLM gateway (Bifrost) is removed.** The app calls Anthropic's Messages API directly with structured outputs; the `LLMGateway` abstraction the manifest asks for stays. Specification: **`2026-09-lean-platform-plan.md`**, milestone **M6b**, which also covers the single service, the worker leader lock, the backup job, the heartbeat and the manifest update.
> - **The design comes first — as HTML drafts, no paid design tool.** Every visible surface is drafted in the real templates, in a warm, minimal style (cream, cappuccino, mocha), shown to the owner in the browser at phone and desktop width, and approved before it is built on (milestone **D**, §17). Figma was dropped (a paid seat), and so was Penpot (the owner chose HTML drafts).
> - **The last step is a product video** (milestone **M10**, §17): 60–90 seconds, animated, in the approved style, text and music, no voice.
> - **A removal is complete** (principle, §3): whatever a decision retires — a provider, a service, a setting — leaves no code, configuration, test or current documentation behind.
> - **Every component stays replaceable** (principle, §3.1): each external service sits behind exactly one module, is built in one place (`services.py`) and configured centrally; a test fails when a vendor detail leaks elsewhere. The repository must stay maintainable as the platform grows — structure, documentation and consistency are part of every milestone's definition of done (§17).
> - **The platform handles failure with composure and keeps the owner informed without being asked** (milestone **M6c**, `2026-09-operations-plan.md`): a failure table with the behaviour for each case, alert channels that do not depend on the platform, a durable incident list, an operator console with health, a seven-day schedule of summaries, previews and sends, and the quiet windows, a daily operator mail at 07:00, an emergency stop for all sends. **Deploys are safe at any time by design** (a send stops between two mails and resumes); Render deploys only after CI has passed.
> - **Open rates:** no tracking; the platform counts visits to the summary page that come from the mail's "Online ansehen" link, per video, without personal data (owner decision 2026-09-27, §20 q4; built in M7).
>
> **Decisions taken with the owner on 2026-09-21** (pricing workshop). **The whole topic has its own plan: `docs/plans/2026-09-billing-plan.md`** — decisions, data model, jobs, tests, Stripe facts, risks and questions. This plan only carries the step (M7a and M7b in §17) and the pointers. In short:
> - **Invoicing moves into the MVP.** What stays out is checkout, subscriptions, stored payment methods and self-service. Stripe invoices in arrears are in.
> - **The price covers the cost plus a small compensation.** One public tier table by mails sent per calendar month (summary and confirm mails), priced per month from measured counts, entry tier €5, owner override per creator including €0.
> - **One invoice after six months or at €100 accrued.** The owner carries the default risk of billing in arrears. Stripe only; no webhook, a daily poll instead.
> - **An unpaid invoice pauses the creator automatically**, after a heads-up, with the reason and the payment link on his page, and resumes on payment.
> - **Limits are announced before they are reached:** YouTube quota and confirm-mail volume get a log warning and an alarm; confirm mails get a daily cap per creator and the sign-up form a honeypot.
> - Hosting and mail-provider cost were parked on 2026-09-21 and **decided on 2026-09-27** (above).
>
> **Decisions taken with the owner on 2026-09-18**, after a code review of M5 found security holes (details in §17 M5 and `implementation-notes.html`; every changed passage below is marked "*Changed 2026-09-18*"):
> - **A block is permanent.** Bounce and complaint blocks mirror the mail provider's account-wide suppression list, which does not expire (true for Resend then and for SES now — SES plan §6.4). The app keeps a sending-only credential (least privilege); the confirm-lifts-a-bounce rule of §7/§10 is dropped. Unblocking is an operator step (`docs/runbooks/operations.md`, from M6a).
> - **Addresses are validated strictly**, with an MX lookup (`email-validator`, §4), before a mail costs sending reputation.
> - **The per-address brake is per address across all creators**, as §7/§10 always said — the first implementation had made it per subscription.
> - **Bad webhook signatures get 401**, not 200 (§10, §13).
> - **Confirm and magic-link mails are sent after the response**, so the response time reveals nothing about an address (§13).
>
> **Decisions taken with the owner on 2026-09-09/10** (copied into the manifest in M6b):
> - E-mail provider: Resend (*replaced by Amazon SES on 2026-09-27*). Hosting: **Render** (Blueprint `render.yaml`).
> - **No Whisper in the MVP.** Two transcript implementations only (official OAuth captions, unofficial `youtube-transcript-api`). Videos without captions are skipped and the creator is notified. Whisper arrives with the podcast connector in Phase 2 (manifest §7.4 step 3 is Phase 2).
> - **Upload trigger: feed poll only** (every 6 hours). PubSubHubbub push (manifest §7.3) is deferred until after go-live: with a 48-hour minimum delay it shortens nothing a creator or fan can observe, and the hub proved unreliable during research (§18). It is purely additive later.
> - **No job-queue library.** The pipeline is a status machine in the database; one worker loop runs due steps (manifest §7.8 lists procrastinate as a recommendation, not a decision; reasoning in §9 and `docs/ARCHITECTURE.md`).
> - **Summarisation is one LLM call** up to a configured transcript length; hierarchical map-reduce (manifest §7.5) is deferred until a real video exceeds the ceiling.
> - **E-mail variants are template-only.** One summary prompt always fills every `Summary` field; the templates decide what each variant shows. Manifest §7.6's per-variant prompt parameter is dropped so that a variant switch applies instantly to open mailings and summary pages without re-summarising, and demo mails can show all three variants from one analysis. Two limits, both in §8.4: a mailing whose preview has already gone out keeps the variant it was previewed with (payload freeze), and the `/s/` page always renders the full text regardless of the variant (manifest §7.6 "Teaser mit Volltext online").
> - **Only the worker runs pipeline steps.** The CLI ingests and reports; it never executes a step (a second runner would repeat expensive steps on the same row).
> - **Welcome link:** the confirm mail (= welcome mail) carries no link to the newest summary because summary pages must not reach unverified addresses; the page shown after confirmation carries it instead (manifest §6.1 wording differs).
> - **Unsubscribe is per creator** (token on the subscription), as the multi-creator data model in manifest §7.7 implies; a global "alle abbestellen" comes with the fan dashboard.
> - Language: all code, docstrings, comments, logs and technical docs in **English**; only `README.md` in German. User-facing texts (pages, mails) in German (manifest §3.4).
> - HTMX is included from the start (manifest §7.8). Feature voting on the landing page (§5.6) and logo upload are deferred; the logo is a URL (default: the YouTube channel avatar).
> - Documents live in `docs/`: plans in `docs/plans/`, concept documents in `docs/manifest/`, operator runbooks in `docs/runbooks/` (from M6a).

---

## How to use this plan

**This plan is the master.** Work through §17 from top to bottom, one milestone after the other: **M0 → … → M6 → M6a → M6b → M6c → D → M7 → M7a → M7b → M8 → M9 → M10**. A milestone is finished when its boxes are ticked, its "Done when" holds, the **definition of done for every milestone** (§17, top) is met and its **Status** line says so; then the *Progress* line at the very top moves on. Four steps are specified in their own files (M6a, M6b, M6c, M7a/M7b) — open that file when you get there, work through it, and come back. Everything else is reached from here:

| Document | What it is for | When you need it |
|---|---|---|
| [`../manifest/creator-plattform-manifest.md`](../manifest/creator-plattform-manifest.md) | What to build, and why (German) | when a task cites "manifest §…" |
| [`2026-09-ses-migration-plan.md`](2026-09-ses-migration-plan.md) | Milestone **M6a**: Amazon SES over SMTP, never-twice sending, the SNS webhook, Mailpit, the AWS setup, the complete Resend removal | when §17 reaches M6a, and for any mail question afterwards |
| [`2026-09-lean-platform-plan.md`](2026-09-lean-platform-plan.md) | Milestone **M6b**: Anthropic directly (gateway removed), web + worker in one service, leader lock, backups, heartbeat, manifest update | when §17 reaches M6b |
| [`2026-09-operations-plan.md`](2026-09-operations-plan.md) | Milestone **M6c**: what happens on every kind of failure, alert channels, incidents, the operator console and daily mail, deploys and the emergency stop, the start script, the honest limits of the cheap setup | when §17 reaches M6c, and whenever something breaks |
| [`2026-09-billing-plan.md`](2026-09-billing-plan.md) | Milestones **M7a** and **M7b**: pricing, usage counting, invoices, pause, early warnings, Stripe facts | when §17 reaches M7a |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Module cut, decisions, rules of the fan area | while building, and updated at the end of every milestone |
| `../runbooks/operations.md` (created in M6a) | Operator steps: AWS/SES setup, unblocking, uncertain deliveries, backups and restore, monitoring, deletions | when operating, and whenever a milestone adds an operator step |
| [`../backlog.md`](../backlog.md) | Everything deliberately left for after the MVP, each with its trigger | when something is deferred — never as a to-do list for the MVP |
| [`../../implementation-notes.html`](../../implementation-notes.html) | Where the build deviates from this plan and why; open questions for the owner; the design review log (German) | after every milestone, and when a decision is needed |
| [`../../README.md`](../../README.md) | Install, start, test, operate; keys; limits (German) | day to day |
| [`../../config/settings.toml`](../../config/settings.toml) | Every tunable, with a comment | whenever a number is in question |

**What waits on what** (*added 2026-09-27*). The one outside decision everything later depends on is the **domain** (§20 question 1): it gates the SES identity, the Google OAuth homepage, the go-live and the video.

| Step | Needs | Unblocks |
|---|---|---|
| M6a, M6b, M6c | nothing outside the repository | D, M7 |
| D | the owner's review time | M7 (pages are built in the approved style), M8 |
| **Domain decided** | the owner (§20 q1) | SES setup steps 1–5, 7, 8, 11 (SES plan §9), Google OAuth verification, M8's real-inbox checks, M9, M10 |
| M7 → M7a → M7b | M6a–M6c, D | M8 |
| M8 | M7b, D, the domain (for the real-inbox checks) | M9 |
| M9 | M8, the domain, the AWS account; SES production access requested once the site is live | the first real mailing, M10 |
| M10 | M9 (the product live, under its final name) | — |

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

**What happens end to end.** The worker asks YouTube's public feed every six hours whether the pilot channel has a new video. A new video becomes an *appearance* row. The pipeline moves that row through a handful of states: fetch its metadata (skip shorts), fetch the transcript (official captions if the creator has connected YouTube, otherwise the unofficial caption library), ask the LLM for a structured summary, and schedule a *mailing* for publish date plus the creator's delay (default seven days, never less than 48 hours). Two hours before send time the worker fetches the top comments and asks the LLM for a sentiment picture. One hour before, the creator gets the exact mail with stop and postpone links. At send time the mail goes out to every confirmed subscriber, one recipient at a time, and never twice. Every step is a plain function that reads its row, does one thing, writes the new state — a crash anywhere resumes at the next loop.

**What the developer builds.** One Python repository, one Docker image: a FastAPI web process (sign-up, confirmation, unsubscribe, the "online ansehen" page, the creator area, the landing page, one webhook for mail feedback) and a worker loop (the pipeline, the periodic jobs, the daily backup). Locally they are two compose services; in production they run side by side in one Render service (§15.2). PostgreSQL holds everything, including pipeline state. Two small abstractions keep later phases cheap: a source/transcript interface and an LLM gateway interface. External services do the heavy lifting: YouTube's Data API, Anthropic's API for the LLM, Amazon SES for e-mail, Render for hosting, Backblaze B2 for backups. No queue framework, no frontend build, no admin UI — the operator uses a CLI, the logs and `docs/runbooks/operations.md`.

**What is deliberately not built.** Podcasts, briefings for interviewers, Whisper transcription, checkout and subscriptions (invoicing in arrears *is* built — billing plan), fan login and dashboards, push notifications from YouTube, multi-tenant self-service. All of them are additive later; none of them is needed to earn the first euro.

**How to read the rest.** §2 says when we are done. §3–§4 are the rules and the stack. §5–§8 describe the code you will write. §9 is the heart: the state machines and the worker. §10–§11 are the pages and the mails. §12–§16 are logging, security, tests, deployment and docs. §17 is the order of work, in milestones that each ship something. §18–§20 are the verified facts, the risks and the questions still open.

## 1. Problem and goal

Build the smallest platform that earns money (manifest §0, §6): one pilot creator on YouTube, whose fans sign up with an e-mail address and receive, a few days after each new video, an automatically generated summary plus a sentiment picture of the comments. The creator gets a preview with a stop window before each send, a settings page via magic link, and a CSV export of his list. A landing page sells the service to further creators.

Technically (manifest §7): a **modular monolith** in Python with one shared pipeline — *source → transcript → analysis → output* — cut cleanly enough that Phase 2 (podcast connector, briefings, multi-tenant self-service) adds files instead of rewriting them. Exactly two deliberate abstractions from day one: the **source/transcript interface** and the **LLM gateway interface** (manifest §7.1).

## 2. Acceptance criteria

Technical definition of done for the MVP (each milestone in §17 has its own, narrower criteria):

- [x] `uv run pytest` is green and `uv run ruff check` / `uv run ruff format --check` report nothing.
- [ ] `docker compose up` starts web, worker, Postgres and Mailpit locally (*Changed 2026-09-27*: no gateway; M6a, M6b); `git push` to `master` deploys to Render without manual steps (manifest §7.1 "one command to deploy") — open, the Blueprint has never been applied.
- [ ] A new public upload on the pilot channel is detected by the feed poll, transcribed, summarised, scheduled, sentiment-enriched, previewed to the creator with a full stop window, and sent to all confirmed subscribers **never twice** (*Changed 2026-09-27*, was "exactly once": after a crash inside one SMTP exchange one recipient may be left out, logged and countable — SES plan §5), without any manual step (manifest §1.5, §7.9).
- [ ] Every mail carries the two "fingerprints" (creator header, platform footer with the "automatisch erstellt" notice), an unsubscribe link, `List-Unsubscribe` headers and an "online ansehen" link; the online page carries the same notice (manifest §3.1, §7.6).
- [ ] Bounces and complaints reported by Amazon SES deactivate the affected subscriber automatically; the delivery status of every mail is in the logs (manifest §6.1; SES plan §6).
- [ ] The creator can change delay, minimum length, variant, greeting/farewell, logo URL, accent colour and reply-to on the settings page; a changed delay reschedules unsent mailings (manifest §5.1 C, §7.6).
- [ ] The creator can export confirmed subscribers as CSV (e-mail + confirmation date only) (manifest §7.9).
- [x] All tunables listed in manifest §7.1 live in one `config/settings.toml`; secrets only in environment variables; per-creator values in the database override the file defaults.
- [ ] Structured logs make every pipeline step traceable by `appearance_id` / `mailing_id`, including LLM tokens and cost per call and YouTube quota units per call (§12).
- [ ] *Added 2026-09-27:* every page and mail looks like its owner-approved draft (milestone D) at phone and desktop width, in light and dark mode (mails: in clients that honour `prefers-color-scheme`); accessibility and performance meet M8's bar.
- [ ] *Added 2026-09-27:* no trace of Resend or of the LLM gateway remains in code, configuration, tests or current docs (the gates in SES plan §11 and lean-platform plan §7).
- [ ] *Added 2026-09-27:* a daily off-site backup exists and a restore has been drilled (lean-platform plan §5); uptime, worker and backup are monitored by channels that do not depend on the platform (operations plan §3).
- [ ] *Added 2026-09-27:* the operator console shows correct health, the next seven days of summaries, previews and sends, open incidents and the quiet windows; the daily operator mail arrives; the emergency stop halts all sends; a deploy during a send delays it without sending anybody twice; every failure of the operations plan §2 behaves as described there.
- [x] `README.md` (German) lets a new developer run the project locally in under 15 minutes; `docs/ARCHITECTURE.md` explains the module cut, the state machines and the decisions.

Three of these hold as of 2026-09-27. M5's and M6's rules are built and tested; their live acceptance waits for the domain and the deployment (M9). The settings page and the CSV export wait for M7 — see the Status lines in §17.

Business criteria (manifest §6.3) are tracked by the owner, not by this plan: a paying creator, measurable list growth, open rates above newsletter average (*Changed 2026-09-27:* not measurable without open tracking — §20 question 4), a spontaneous recommendation.

## 3. Guiding principles for the code

Taken from the project's code-style rules and manifest §7.1; listed here because they decide many small choices below.

- **One responsibility per module and function.** Small functions, early returns, descriptive names, `handle_*` for request/webhook handlers.
- **No abstraction without a second implementation** — except the two the manifest names: the source/transcript interface (`SourceConnector`, `TranscriptProvider`) and the LLM gateway interface (`LLMGateway`). Everything else, including the e-mail client and the YouTube API client, is a plain class; test fakes duck-type it, no Protocol needed.
- **Single source of truth.** Tunables in `settings.toml`, per-creator values in the DB, the product name in exactly one place (`settings.product.name`), colours and sizes in `app/design.py`, status vocabularies as `StrEnum`s next to their tables, prompts and e-mail variants as files, log event names as constants.
- **Deletion over addition, boring over clever.** Stdlib first (`xml.etree`, `hmac`, `secrets`, `argparse`, `csv`, `tomllib`, `smtplib`, `email`), then already-installed libraries, then new dependencies. Values that never change are module constants next to their single use, not configuration.
- **A removal is complete** (*owner rule, 2026-09-27*). When a decision retires something — a provider, a service, a setting, a parameter — everything that existed only for it goes in the same milestone: code, constants, settings, environment variables, log events, fakes, tests, fixtures, comments, docstrings, README/ARCHITECTURE/runbook sentences, deployment entries. Nothing is commented out or kept "in case". Code that loses its reason with it (a parameter that only fed a removed key, a comment explaining the old provider) goes too. Each removal has a **grep gate** in its milestone that must print nothing, and every milestone ends with a review of its whole diff for dead code and simplification. The code must be at least as small and clear afterwards as before.
- **Deliberate shortcuts are marked** with a `# ponytail:` comment naming the ceiling and the upgrade path (manifest §7.1 "bewusste Abkürzungen werden im Code als solche markiert").
- **numpy-style docstrings** on public functions; comments explain *why*, never *what*; architecture reasoning goes to `docs/ARCHITECTURE.md`, never into comment blocks.
- **Idempotent by construction.** Every step re-checks the database state before acting; unique constraints, conditional status updates (§8.4), advisory locks and — for fan mails — a per-recipient claim committed before each send (*Changed 2026-09-27*, SES plan §5) guarantee "never twice", not application-level bookkeeping.
- **Logs are part of the feature.** A step without a log line at start and end is unfinished (§12).
- **Tests use fakes, not mocks.** External services are swapped through one documented seam (§8.6); nothing else is patched (§14). Where time or I/O must be controlled inside a class, the class takes it as a constructor parameter (e.g. `SmtpClient(clock=…, sleep=…, connect=…)`).

### 3.1 Replaceable components (*added 2026-09-27* — owner requirement)

The platform must be able to grow and to swap a component for a better one without rewriting its neighbours. The means are **narrow seams, one construction point and central configuration — not an abstraction layer for everything** (an interface with one implementation is a cost, §3). Where a Protocol exists it is because the manifest asks for a second implementation; elsewhere the seam is "one module owns the vendor, `services.py` builds it, `settings.toml`/env configure it".

| Component | Seam — the only place that knows the vendor | Configured in | Swapping it means |
|---|---|---|---|
| LLM (Anthropic) | `LLMGateway` Protocol; `AnthropicGateway` in `analysis/llm.py` | `[llm]` (models, prices, timeout, cap), `ANTHROPIC_API_KEY` | one new class; model changes are two lines + a price entry |
| Prompts | versioned files `analysis/prompts/*_vN.md` | `[llm] summary_prompt_version`, `sentiment_prompt_version` | a new file + one line; compared first with `cli eval-prompts` |
| Output schemas | `analysis/schemas.py` (Pydantic, `Strict`) | — | a model change + template change; the schema-keyword test guards the API |
| Mail relay (SES) | `SmtpClient` in `delivery/email_client.py` (plain SMTP) | `[email] smtp_host/port/rate`, `SMTP_*` | configuration only for any SMTP relay (true because the client speaks plain SMTP); only its feedback webhook is new code |
| Mail feedback (SNS) | `delivery/sns.py` + `web/routes/webhooks.py` | `SES_FEEDBACK_TOPIC_ARN` | one new route for another provider's webhook; `block_addresses` stays |
| Transcripts | `TranscriptProvider` Protocol, chain in `services.py` | `[content] transcript_languages`, proxy env | one new provider class, one line in the chain |
| Sources (YouTube) | `SourceConnector` Protocol; YouTube-specific besides it: `YouTubeConnection` (OAuth), the official-captions provider and the creator's OAuth routes | `[content]`, `[worker] feed_poll_hours`, `YOUTUBE_API_KEY`, `GOOGLE_OAUTH_*` | a new connector package (podcast in Phase 2); the OAuth parts stay YouTube's |
| Database (PostgreSQL 17) | SQLAlchemy models + Alembic | `DATABASE_URL` | any managed PostgreSQL by URL. *Honest limit:* PostgreSQL itself is a deliberate choice — advisory locks, JSONB, `ON CONFLICT`, partial indexes; another database engine would be a real migration |
| Hosting (Render) | one Docker image, `docker-compose.yml`, `render.yaml` | env | any container host; the VPS route is documented (§15.2) |
| Backups (B2) | `backup.py` via restic | `RESTIC_REPOSITORY` etc. | any restic backend by URL |
| Monitoring | ping URLs and DSN in env | `WORKER_HEARTBEAT_URL`, `BACKUP_HEARTBEAT_URL`, `SENTRY_DSN` | configuration only |
| Payments (Stripe, M7b) | `billing/stripe_client.py` | `STRIPE_API_KEY`, `[billing]` | one new client class |
| Design | `app/design.py` tokens + templates + `style.css` | — | tokens and templates only; no colour or size elsewhere (test) |
| Product name, domain | `settings.product` | `[product]` | one line each |

**Guards** that keep it true: the **vendor-boundaries test** (lean-platform plan §8) fails when a vendor detail appears outside its module; `services.py` is the only place clients are built; secrets only in `Secrets`, tunables only in `settings.toml`, each with a comment; the grep gates of every removal. **Migrations survive a deploy overlap:** every migration is backward compatible with the previous release — add, never rename or drop in the same release (expand → deploy → contract; operations plan §7.4).

## 4. Technology stack (final)

All versions verified on 2026-09-09/10 (see §18), the 2026-09-27 changes on that day. Pin exact versions in `pyproject.toml` (`sqlalchemy<2.1`, FastAPI and Starlette pinned too); `uv.lock` is committed.

| Concern | Choice | Notes / deviation from manifest §7.8 |
|---|---|---|
| Language | Python **3.13** (`.python-version`), **uv** | 3.14 is Render's default but `youtube-transcript-api` pins `<3.15` and several libs only just added 3.14; 3.13 is the safe choice. |
| Web | **FastAPI** + **uvicorn** | Sync `def` endpoints with sync SQLAlchemy (documented, threadpool-backed). |
| Templates | **Jinja2** (pages and mails, one environment) + **HTMX** (vendored single file in `static/`) + handwritten CSS | No build step. Colours and sizes come from `app/design.py` (§11). |
| DB | **PostgreSQL 17**, **SQLAlchemy 2** (sync, `postgresql+psycopg://`), **psycopg 3** (`psycopg[binary]`), **Alembic** | One DB for data, pipeline state and periodic-job bookkeeping. |
| Jobs | **No queue library.** `app/worker.py`: a loop that runs due pipeline steps and periodic jobs (§9). The worker is its own process; in production it runs next to the web process in one container, one leader at a time (§8.5, §15.2). | Deviation from §7.8 (procrastinate): the state already lives in `appearances.status` / `mailings.status`; a queue would duplicate it and add four tables, a connector and LISTEN/NOTIFY semantics. |
| Config | **pydantic-settings** with `TomlConfigSettingsSource` + env | Priority: env > `.env` > `settings.toml` > defaults. |
| HTTP | **httpx** | YouTube Data API and captions, Google OAuth token endpoint, Anthropic's Messages API, the SNS signing certificate, the heartbeat pings; Stripe from M7b (billing plan §5). |
| YouTube | **httpx against the Data API REST endpoints** (API key; captions endpoints with the creator's OAuth token); **httpx against Google's OAuth endpoints** (authorize URL, code exchange, refresh); **youtube-transcript-api 1.2.4** (unofficial captions) | Deviation: `google-api-python-client`, `google-auth` and `google-auth-oauthlib` are not needed — four GET endpoints, one download and two token POSTs are simpler as plain httpx calls, and it removes about ten transitive packages. |
| LLM | *Changed 2026-09-27:* **Anthropic's Messages API directly** (`POST /v1/messages`, structured outputs via `output_config.format`), behind the `LLMGateway` Protocol (`AnthropicGateway`) | Manifest §8 named the Bifrost gateway; it is removed (lean-platform plan §2) — one container less, ≈ $7 a month less. The app never imports a provider SDK; another provider is another `LLMGateway` implementation. |
| Addresses | **email-validator 2.3** (+ dnspython) | *Changed 2026-09-18 (M5 review):* RFC syntax, IDN to punycode, MX lookup with a 3 s timeout (a timeout lets the address through). Rolling our own RFC 5322 parser is exactly the reinvention §3 forbids. |
| E-mail | *Changed 2026-09-27:* **Amazon SES** (eu-central-1) over **SMTP with the standard library** (`smtplib`, `email.message`, `email.headerregistry`); feedback via **SNS** → `/webhooks/ses`, signatures checked with `cryptography`; locally **Mailpit** catches every mail | No SDK (`boto3`), no new dependency. Resend removed (cost); Listmonk evaluated and rejected. Detail: `2026-09-ses-migration-plan.md`. |
| CSS inlining | **css_inline** | Deviation: `premailer` has had no release since 2021; `css_inline` is maintained and 10× faster. |
| Rate limits | **slowapi** (in-memory storage) | Sign-up, magic-link request, contact form. Single web process in the MVP. Do not install the `[redis]` extra (obsolete pin). |
| Tokens/crypto | **itsdangerous** (signed session cookie via Starlette `SessionMiddleware`), **cryptography** Fernet/MultiFernet (OAuth refresh tokens at rest; SNS signatures), `secrets` (URL tokens, OAuth state) | |
| Logging | **structlog** (JSON or console by setting, optional rotating file), **sentry-sdk** (optional, DSN from env, EU region) | |
| Backups | *Added 2026-09-27:* **pg_dump 17** + **restic** (pinned release binary) in the image, run daily by the worker, to **Backblaze B2** | Lean-platform plan §5. |
| Quality | **pytest**, **ruff** (lint + format), GitHub Actions | |
| Hosting | *Changed 2026-09-27:* **Render** Blueprint, region Frankfurt: **one** web service (`0.5c-512mb`) running web and worker from the same image via `ops/start.sh`; Postgres (`0.1c-256mb`, PG 17) | **≈ $13.30 ≈ €11.50 a month** (§15.2). Free tiers are unusable (free web services spin down, free Postgres expires after 30 days; `preDeployCommand` needs a paid plan). |
| Product video | *Added 2026-09-27:* **Remotion** (Node, in `video/`, outside the Python build and CI) | Milestone M10. |

Not used, on purpose: async SQLAlchemy, Redis, procrastinate, feedparser (Phase 2, podcast), PyYAML (roadmap file is TOML, stdlib), the Stripe SDK (M7b speaks plain httpx), pgvector (Phase 3), Whisper (Phase 2), any DI or plugin framework; *added 2026-09-27:* Listmonk (SES plan §2), `boto3`, the Bifrost gateway (removed), a self-hosted PaaS layer (Coolify, Dokploy), any paid design tool (the design is drafted in HTML — milestone D).

## 5. Repository layout

The target layout after M10; after M0 `docs/ARCHITECTURE.md` is the authority for the layout of what exists. Entries added or changed on 2026-09-27 carry *(M6a)*, *(M6b)*, *(D)* or *(M10)*.

```
youtuber-fan-platform/
├── README.md                     German. What this is, how to run it, where things are.
├── pyproject.toml                Project, dependencies, ruff + pytest config.
├── uv.lock
├── .python-version               3.13
├── .env.example                  Every secret/env var with a comment, no values. Authority for env vars.
├── .gitignore                    Also video/node_modules/ and video/out/ (M10).
├── Dockerfile                    THE build: one image for web and worker; adds the PostgreSQL 17 client and a pinned restic (M6b).
├── docker-compose.yml            postgres, mailpit (M6a), web, worker — no gateway (M6b).
├── render.yaml                   Render Blueprint: one web service running ops/start.sh, one Postgres (M6b).
├── alembic.ini
├── .github/workflows/ci.yml      uv sync --locked, ruff, pytest against Postgres and Mailpit service containers (M6a).
├── docker/init-test-db.sh        Creates the app_test database for DATABASE_URL_TEST.
├── ops/
│   └── start.sh                  Runs uvicorn and the worker in one container; restarts a crashed worker, ends with the web (M6b, M6c).
├── config/
│   ├── settings.toml             THE configuration file (manifest §7.1). Authority for tunables (commented).
│   └── roadmap.toml              Feature preview cards (manifest §5.6), read with stdlib tomllib (M8).
├── migrations/                   Alembic environment and versions.
├── src/app/                      The application package (neutral name; the product name lives in settings only).
│   ├── config.py                 Settings model, derived values, `get_settings()`.
│   ├── errors.py                 `TemporaryError`, `NeedsOperator`, `CostCapExceeded` — the retry signals of §9.4.
│   ├── log.py                    structlog setup, context helpers, event-name constants (not "logging.py": shadows the stdlib name).
│   ├── jinja.py                  THE Jinja environment (loader over templates/, globals, filters), used by mails and pages.
│   ├── design.py                 Colours, type sizes, radii, spacing (light and dark) — the one place; pages and mails read it (D).
│   ├── branding.py               The creator's accent made readable against the design's own backgrounds (D reads them from design.py).
│   ├── design_preview.py         Renders every page and mail with fictional demo data (defined in the module, validated as `Summary`/`Sentiment`) for design review and the video (D).
│   ├── addresses.py              What an address is and when two are the same (validation, canonical spelling).
│   ├── subscriptions.py          A fan's subscriptions: sign-up rules, confirm, unsubscribe, the confirm mail.
│   ├── creator_settings.py       `effective_settings(creator)`: per-creator values over file defaults.
│   ├── tokens.py                 URL tokens.
│   ├── backup.py                 The daily pg_dump → restic → B2 job (M6b).
│   ├── ops/                      status.py (the one query module behind cli status, console, daily mail, deploy check), incidents.py (M6c).
│   ├── services.py               `Services` container built from settings; `set_services()` is the one test seam.
│   ├── worker.py                 The worker loop: leader lock, due pipeline steps, periodic jobs, heartbeat (§9, M6b).
│   ├── cli.py                    Operator commands (argparse): onboard, poll, process, backfill, demo-mails, eval-prompts; status and operator-password (M6c); design-preview (D); design-tokens (M10); billing commands (M7b).
│   ├── db/
│   │   ├── engine.py             Engine, `SessionLocal`, `session_scope()`.
│   │   ├── locks.py              `advisory_lock(namespace, key)` — mailing sends and the worker leader (M6b).
│   │   └── models.py             All ORM models and their StrEnum vocabularies.
│   ├── sources/                  Source connectors (manifest §7.3) — source-specific.
│   │   ├── base.py               `SourceConnector` Protocol, `ContentItem` and `Comment` dataclasses.
│   │   └── youtube/              connector.py, feed.py (Atom, xml.etree), data_api.py (httpx; QUOTA_UNITS), oauth.py (httpx; Fernet at rest).
│   ├── transcripts/              Transcript layer (manifest §7.4) — the first deliberate abstraction.
│   │   ├── base.py               `TranscriptProvider` Protocol, `Transcript`/`Segment` dataclasses, error types.
│   │   ├── youtube_official.py   captions.list + captions.download with the creator's token; SRT parser.
│   │   ├── youtube_unofficial.py youtube-transcript-api with proxy config and timeout.
│   │   └── service.py            Provider chain per source; persists transcript + origin.
│   ├── analysis/                 Analysis layer (manifest §7.5) — source-independent.
│   │   ├── llm.py                `LLMGateway` Protocol, `AnthropicGateway` (M6b), `Completion`; ledger + daily-cap functions.
│   │   ├── schemas.py            Pydantic models for structured outputs (`Summary`, `Section`, `KeyPoint`, `Sentiment`).
│   │   ├── prompts/              Versioned prompt files: summary_v1.md, sentiment_v1.md (variants are templates, not prompts).
│   │   ├── summarize.py          Transcript → `Summary` (prompt assembly, timestamp markers).
│   │   ├── comments.py           Heuristic comment filter (manifest §3.1 feature 2).
│   │   └── sentiment.py          Filtered comments → `Sentiment`.
│   ├── delivery/                 Output layer (manifest §7.6).
│   │   ├── email_client.py       `SmtpClient`, `SmtpSession`, `DeliveryUncertain`; SMTP reply codes → errors; send-rate spacing. Transport only (M6a).
│   │   ├── sns.py                SNS signature verification + `SnsCertificates` for the SES feedback webhook (M6a).
│   │   ├── render.py             Composes `OutgoingEmail`s (sender name and address, reply-to, headers, SES tags) from templates; CSS inlining.
│   │   └── mailing.py            Mailing lifecycle: create/schedule, reschedule, stop/postpone, sentiment, preview, send (claim-before-send).
│   ├── billing/                  pricing.py, usage.py, invoicing.py, pause.py, stripe_client.py (M7a/M7b — billing plan §5).
│   ├── jobs/
│   │   ├── steps.py              Pipeline step functions per status (§9.3) and periodic jobs; called by worker.py and cli.py.
│   │   └── schedule.py           Pure functions: `compute_send_at()`, `next_mailing_step()`, `retry_at()`; from M6c `every`, `daily_at`, next events, send durations, `quiet_window` — tested without DB.
│   ├── web/
│   │   ├── server.py             `create_app()`: middleware (request id, session, rate limit, body limit), routers, static.
│   │   ├── deps.py               `DbSession`, `current_creator`.
│   │   └── routes/
│   │       ├── public.py         /, /impressum, /datenschutz, /kontakt, /health
│   │       ├── fan.py            /k/{slug}, confirm, unsubscribe, /s/{token}
│   │       ├── creator.py        login (magic link), settings, CSV export, OAuth start/callback, stop/postpone, billing page (M7b)
│   │       ├── operator.py       /betrieb console (M6c)
│   │       └── webhooks.py       /webhooks/ses (M6a)
│   ├── templates/
│   │   ├── email/                base.html, summary.html/.txt, confirm.html/.txt, creator_notice.html/.txt, magic_link.html/.txt, preview_when.html/.txt; contact.txt (M8)
│   │   ├── pages/                base.html, landing.html, signup.html, confirmed.html, summary.html, creator_login.html, action_confirm.html, legal.html, error.html; creator_settings.html (M7); billing.html (M7b)
│   │   └── partials/             summary_body.html (per variant blocks), sentiment_box.html, platform_footer.html, page_footer.html, creator_header.html, signup_form.html, rate_limited.html, example_mail.html; billing_rules.html (M7b)
│   └── static/                   style.css, htmx.min.js; fonts/ (self-hosted woff2 + licence, D); video/ (web cut + poster, M10); favicon (M8)
├── tests/
│   ├── conftest.py               Settings override, DB fixtures, `Services` with fakes via `set_services()`.
│   ├── fakes.py                  FakeLLMGateway, FakeEmailClient, FakeTranscriptProvider, FakeYouTubeConnector, SNS signer (duck-typed).
│   ├── fixtures/                 feed.xml, videos.json, comments.json, transcripts/ (prompt eval samples)
│   ├── unit/                     Pure logic: feed parsing, SNS signature, SMTP error mapping, comment filter, schedule maths, SRT parser, settings, templates, design contrast.
│   └── integration/              Against Postgres (and Mailpit): ingest idempotency, DOI flow, mailing state machine, never-twice send, webhooks, leader lock, backup job.
├── video/                        The product video (M10): Remotion project with its own package.json; not part of the image or CI.
└── docs/
    ├── ARCHITECTURE.md           Module cut, data flow, state machines, worker loop, "Decisions" section, "Where to find what".
    ├── runbooks/                 operations.md (created in M6a: AWS/SES, unblocking, uncertain deliveries, backups, monitoring, deletions); onboarding.md (M7).
    ├── plans/                    This file and its sub-plans (ses-migration, lean-platform, operations, billing).
    └── manifest/                 Concept documents (source of truth).
```

Why `src/app` and not the product name: manifest §7 (intro) demands the name appear in exactly one place so renaming costs one line. The package name is neutral; `settings.product.name` is the one place.

## 6. Configuration

### 6.1 `config/settings.toml` (checked in, no secrets)

Exactly the tunables manifest §7.1 and §13 name, plus the few the code needs. Values below are the manifest defaults. Values that never change (the send loop's page size 100, Data API page size 100, token length 32 bytes, the Anthropic API URL, provider order) are module constants next to their single use, not configuration (manifest §7.1 "keine Konfiguration für Werte, die sich nicht ändern").

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

[llm]                                   # manifest §8; the file is the authority, this is its shape (changed 2026-09-27: no provider prefix — lean-platform plan §2)
model_summary = "claude-sonnet-5"       # Anthropic model name; switching: these two lines and the price entry below
model_sentiment = "claude-sonnet-5"
max_output_tokens = 4000
timeout_seconds = 120
daily_cost_cap_cents = 500              # per creator per day (manifest §7.9)
summary_prompt_version = "v1"
sentiment_prompt_version = "v1"
usage_dashboard = "https://console.anthropic.com/settings/usage"   # what the provider says we spent; the ledger estimates it

[llm.prices_per_million_tokens]         # every model above must have an entry (validated at start-up); each carries source and date
"claude-sonnet-5" = { input = 2.00, output = 10.00, source = "provider price list", checked_on = 2026-09-20 }
"claude-sonnet-4-5" = { input = 3.00, output = 15.00, source = "provider price list", checked_on = 2026-09-20 }   # kept for old ledger rows

[email]                                 # manifest §7.6
variants = ["compact", "detailed", "teaser"]
default_variant = "compact"
confirm_token_days = 7                  # unconfirmed sign-ups are deleted after this (manifest §7.9)
unsubscribed_retention_days = 30        # unsubscribed rows are deleted after this (manifest §9 deletion concept)
magic_link_minutes = 15
session_hours = 24
max_custom_text_chars = 300             # greeting / farewell (manifest §7.6 "wenige hundert Zeichen")
# added 2026-09-27 (SES plan §7) — local defaults; production sets EMAIL__SMTP_HOST / EMAIL__SMTP_PORT (§15.2):
smtp_host = "localhost"                 # the SMTP relay: Mailpit locally, email-smtp.eu-central-1.amazonaws.com in production
smtp_port = 1025                        # 1025 = Mailpit; 587 in production (STARTTLS, derived for every non-local host)
max_send_rate_per_second = 1.0          # per process; web and worker share the SES rate — about 80 % of it after approval
daily_quota = 0                         # the SES 24-hour quota; a send that would exceed it does not start (SES plan §5); 0 = not checked

[web]
rate_limit_signup = "20/minute"         # per IP; deliberately loose, many fans share one mobile-carrier NAT IP
confirm_cooldown_minutes = 10           # per e-mail address: at most one confirm mail per address in this window (§10); renamed 2026-09-27
check_address_dns = true                # sign-up asks DNS whether the domain accepts mail (added 2026-09-18)
rate_limit_magic_link = "3/minute"
rate_limit_contact = "3/minute"

[worker]
loop_seconds = 60                       # how often the worker looks for due steps
feed_poll_hours = 6                     # upload detection latency; manifest §7.3 said daily, 6 h is free and shorter

[operations]                            # added 2026-09-27 (operations plan); fixed thresholds are module constants there
digest_time = "07:00"                   # the daily operator mail, in product.timezone
backup_time = "03:30"                   # the nightly backup, in product.timezone — away from sends
deploy_margin_minutes = 20              # the quiet window ends this long before a preview or a send

[logging]
level = "INFO"
json = false                            # true in production (LOGGING__JSON=true); the setting alone picks the format
file = ""                               # e.g. "logs/app.log" for a local rotating file; empty = stdout only
```

### 6.2 Environment variables (secrets and per-environment values)

Rule: secrets and per-environment values are **flat** fields of a `Secrets` model read from env only; TOML tables are overridable via `TABLE__KEY` (`env_nested_delimiter="__"`). `.env.example` is the authority and carries a comment per variable.

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | web, worker, alembic, backup | Render injects the internal URL via `fromDatabase` as `postgresql://` (the dashboard shows `postgres://`); `config.py` normalises both to `postgresql+psycopg://` (and gives `pg_dump` the form without `+psycopg`, M6b). |
| `DATABASE_URL_TEST` | `uv run pytest` | Locally `…/app_test` (created by `docker/init-test-db.sh`); in CI the Postgres service container. |
| `SECRET_KEY` | web (session cookie) | Render `generateValue: true`. |
| `TOKEN_ENCRYPTION_KEYS` | web, worker (OAuth refresh tokens, Fernet) | Comma-separated, first = current (MultiFernet rotation). |
| `BASE_URL` | links in mails and pages | Optional override; default `https://{product.domain}`; local `http://localhost:8000`. |
| `SUPPORT_EMAIL` | reply-to fallback, `/kontakt` recipient | Optional; overrides the derived `hallo@{domain}` until that mailbox exists (below, §20 q8). |
| `YOUTUBE_API_KEY` | Data API (metadata, comments, channel) | |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | official captions | |
| `TRANSCRIPT_PROXY_USERNAME`, `TRANSCRIPT_PROXY_PASSWORD` | unofficial transcripts from cloud IPs (Webshare rotating residential) | Empty locally. |
| `ANTHROPIC_API_KEY` | worker, CLI (`eval-prompts`) | *Changed 2026-09-27:* the app's own key for Anthropic's Messages API (was the gateway's). A key in its own workspace with a spend limit (lean-platform plan §2). |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | web, worker, CLI | *Added 2026-09-27:* SES SMTP credentials of the sending-only IAM user (region-bound). Empty locally — Mailpit needs none (SES plan §7). |
| `SES_FEEDBACK_TOPIC_ARN` | web | *Added 2026-09-27:* the SNS topic whose notifications `/webhooks/ses` accepts; its region is the region of the signing certificates; empty = every call refused. |
| `EMAIL__SMTP_HOST`, `EMAIL__SMTP_PORT`, `EMAIL__MAX_SEND_RATE_PER_SECOND`, `EMAIL__DAILY_QUOTA` | production (render.yaml), compose | *Added 2026-09-27:* `email-smtp.eu-central-1.amazonaws.com`, `587`, about 80 % of the approved rate, the approved 24-hour quota; compose sets `mailpit` / `1025`. |
| `WORKER_HEARTBEAT_URL` | worker | *Added 2026-09-27:* Healthchecks.io ping URL; empty = off (lean-platform plan §6). |
| `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `BACKUP_S3_KEY_ID`, `BACKUP_S3_SECRET`, `BACKUP_HEARTBEAT_URL` | worker (backup job) | *Added 2026-09-27:* empty repository = backup off (local). Password and key also in the owner's password manager (lean-platform plan §5). |
| `FORWARDED_ALLOW_IPS` | web (`ops/start.sh`) | *Added 2026-09-27:* defaults to `*`; M9 sets Render's proxy addresses (`implementation-notes.html` question 9). |
| `OPERATOR_EMAIL` | worker | *Added 2026-09-27:* where operator mails and the daily mail go (operations plan §4, §6). |
| `OPERATOR_PASSWORD_HASH` | web | *Added 2026-09-27:* scrypt hash for the console's HTTP Basic login (`uv run app operator-password`); empty = console off. |
| `RENDER_GIT_COMMIT` | web | Set by Render; the console shows it as the version. |
| `STRIPE_API_KEY` | web, worker, CLI | From M7b: a restricted key (billing plan §3). |
| `SENTRY_DSN` | web, worker | Empty = disabled. EU region DSN in production. |
| `LOGGING__JSON`, `LOGGING__LEVEL` | logging | Nested override; `LOGGING__JSON=true` in production. |

*Removed 2026-09-27:* `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `SENDER_ADDRESS` (M6a); `LLM_GATEWAY_URL`, `LLM_GATEWAY_KEY`, `BIFROST_SETUP_TOKEN`, `BIFROST_CONFIG_B64`, `APP_PORT` (M6b).

Derived in `config.py` (properties, no config keys): `base_url`, `mail_domain = f"mail.{domain}"`, `sender_address = f"post@{mail_domain}"` (no override since M6a), `support_email = f"hallo@{domain}"` — the last one overridable with an optional `SUPPORT_EMAIL` env var, because this address must be a mailbox somebody actually reads: it is the reply-to fallback for a creator who sets none (§8.4) and the recipient of every `/kontakt` relay (§10). Sending from a domain needs no MX record, receiving does, and the plan configures no receiving path anywhere; until a mailbox exists, `SUPPORT_EMAIL` points at an existing one, otherwise every contact-form mail hard-bounces against the sending reputation §11 protects. → §20.

### 6.3 Settings class

`app/config.py` holds one `Settings(BaseSettings)` with nested models per TOML table (`ProductSettings`, `ScheduleSettings`, …) and a flat `Secrets` model from env. `settings_customise_sources` returns `(init, env, dotenv, TomlConfigSettingsSource)` in that order — the pydantic docs' minimal example returns only the TOML source and would silently disable env overrides. Validation at start-up: `min_delay_hours ≥ 1`, `default ∈ [min, max]`, `default_variant ∈ variants`, `stop_window_minutes < sentiment_lead_hours*60`, every model named in `llm.model_summary` / `llm.model_sentiment` has an entry in `llm.prices_per_million_tokens` (otherwise a model swap would either fail at the first call or silently book cost 0 and bypass the cap), and `email.max_send_rate_per_second > 0` (M6a). `get_settings()` is `functools.lru_cache`d; tests call `get_settings.cache_clear()`.

Per-creator overrides (delay, min length, variant, branding, reply-to) live in the `creators` table and are read through one helper `effective_settings(creator)` so no code path reads the file default when a creator value exists. The settings form (§10) validates creator input against the same `min`/`max`/`variants` values from `settings` — one rule, two call sites, no second implementation.

## 7. Data model

Maps manifest §7.7 one-to-one; English names in code, manifest names in brackets. All timestamps `timestamptz` in UTC; display in `product.timezone`. IDs are integer primary keys; external identifiers are separate unique columns.

Vocabularies (`appearances.status`, `transcripts.origin`, `analyses.kind`, `subscriptions.status`, `mailings.status`, `subscribers.blocked_reason`, the `kind` of creator notices) are each one `enum.StrEnum` defined in `app/db/models.py` next to its table; the column is `VARCHAR` with a `CheckConstraint` built from `list(Enum)` (Alembic autogenerate mishandles native Postgres enums; migrations spell the values out because a migration is a snapshot). Steps, routes and templates compare against enum members, never literals. Transition sets (e.g. `MAILING_STOPPABLE`) are constants beside the enum. `skip_reason` and `last_error` are free text.

Every FK on the chain below `creators` (`sources.creator_id`, `appearances.source_id`, `transcripts/analyses/mailings.appearance_id`, `deliveries.mailing_id`, `deliveries.subscription_id`, `subscriptions.creator_id`, `subscriptions.subscriber_id`) is `ON DELETE CASCADE`; the ledger FKs on `llm_calls` are `ON DELETE SET NULL`. Deleting a creator or a subscriber on request is therefore one SQL statement in the runbook (manifest §7.9 "Export und Löschung"), not a CLI tree-walk.

| Table | Purpose (manifest term) | Key columns and constraints |
|---|---|---|
| `creators` | Customer for product 1 (*Creator*) | `slug` unique (sign-up URL), `name`, `contact_email` (login + notices), `reply_to_email` nullable, `logo_url`, `accent_color` (`#rrggbb`), `greeting_text`, `farewell_text`, `email_variant`, `send_delay_hours` nullable, `min_duration_seconds` nullable, `magic_link_token_hash` + `magic_link_expires_at` nullable, `created_at`. Nullable overrides = "use the file default". |
| `sources` | A YouTube channel (*Quelle*) | `creator_id`, `kind` (`youtube`), `external_id` (channel `UC…`), `title`, `oauth_refresh_token_enc` nullable, `oauth_granted_at`, `oauth_needs_reconsent` bool, `created_at` (feed entries published before it are ignored unless backfilled). Unique `(kind, external_id)`. |
| `appearances` | A video (*Auftritt*) — the central, source-independent object | `source_id`, `external_id` (video id), `title`, `url`, `published_at`, `duration_seconds` nullable, `status` (§9.1), `skip_reason` nullable, `is_backfill` bool, `view_token` unique (32 random bytes, url-safe), `official_captions_declined` bool (§8.2), `attempts`, `next_attempt_at`, `last_error` (retry bookkeeping, §9.4), `created_at`; *added in M7:* `mail_views` int (the "Online ansehen" estimate, §17 M7). **Unique `(source_id, external_id)` — this is the idempotency guarantee** (manifest §7.9). |
| `transcripts` | (*Transkript*) | `appearance_id` unique, `origin` (`youtube_official` / `youtube_unofficial`) — stored because it is legally relevant (manifest §7.7), `language`, `is_generated` bool, `segments` jsonb `[{start, duration, text}]`, `fetched_at`. Plain text is derived on read (`Transcript.text`), not stored twice. |
| `analyses` | (*Analyse*) | `appearance_id`, `kind` (`summary` / `sentiment`), `prompt_version`, `model`, `content` jsonb (validated `Summary` / `Sentiment`), `created_at`. **Unique `(appearance_id, kind)`** — one current analysis per kind, written with `INSERT … ON CONFLICT DO UPDATE` (a sentiment refresh after postpone overwrites). `prompt_version` + `model` record what produced it (manifest §7.7 "versioniert nach Prompt/Modell"); comparing prompt versions happens in `cli eval-prompts`, not in the DB. `# ponytail: one analysis per kind; keep history when A/B-comparing prompts in production becomes a real task.` A missing `sentiment` row means "no sentiment" (comments disabled or sentiment step gave up). |
| `subscribers` | An e-mail address (*Abonnent*), can follow several creators | `email` unique (stored lower-cased), `blocked_at` + `blocked_reason` (`bounce` / `complaint`) nullable, `created_at`. *Changed 2026-09-18 (M5 review):* Every block is permanent and a re-signup sends nothing, whatever the reason: the provider itself suppresses the address (*Changed 2026-09-27:* SES's account suppression list, like Resend's before it) and a mail there would be dropped. A complaint outranks a bounce and is never replaced by one. The cleanup keeps complaint rows forever (they are what stops a new sign-up) but deletes bounce rows once no subscription is left — the provider keeps its own suppression entry, and we keep no data we do not need. *(Originally: a bounce block was lifted when the address confirmed again. That cannot work: the provider drops the confirm mail, and editing its list needs a broader credential than the app's.)* |
| `subscriptions` | Subscriber ↔ creator with double-opt-in state | `subscriber_id`, `creator_id`, `status` (`pending` / `confirmed` / `unsubscribed`), `confirm_token` unique, `confirm_expires_at`, `confirm_sent_at` (throttles confirm mails per address, §10), `confirmed_at`, `unsubscribe_token` unique (permanent, per creator), `unsubscribed_at`, `created_at`. Unique `(subscriber_id, creator_id)`. |
| `mailings` | One planned send per appearance (*Zustellung*, planned part) | `appearance_id` unique, `status` (§9.2), `send_at`, `stop_token` unique (rotated on every new schedule: postpone and delay change), `preview_sent_at`, `render_snapshot` jsonb nullable (the creator's rendering-relevant fields, frozen when the preview goes out — §8.4), `stopped_at`, `sent_at`, `recipient_count`, `attempts`, `next_attempt_at`, `last_error`, `created_at`. |
| `deliveries` | One row per recipient per mailing (*Zustellung*, per subscriber) — a send ledger, not analytics | `mailing_id`, `subscription_id`, `attempted_at` nullable (*Added 2026-09-27:* the claim written and committed before the mail is handed to SES — SES plan §5), `sent_at` nullable. Pending = `attempted_at` null; sent = both set; **uncertain** = claimed, never confirmed — never sent again. **Unique `(mailing_id, subscription_id)` — at most one mail per recipient.** `# ponytail: no delivered/bounced state, no provider message id; bounces block the subscriber by address, delivery rates come from the SES console (manifest §7.6). Add columns with the Phase-2 analytics dashboard.` |
| `llm_calls` | Cost ledger (manifest §7.9 "Kostenkontrolle") | `creator_id` nullable, `appearance_id` nullable, `purpose`, `model`, `prompt_version`, `tokens_in`, `tokens_out`, `tokens_cached`, `tokens_cache_write` (both inside `tokens_in`), `cost_cents` numeric, `price_input`, `price_output` (the prices it was booked at), `duration_ms`, `ok` bool, `created_at`. |
| `job_runs` | Periodic-job bookkeeping and component state | `name` primary key, `last_run_at`; *added 2026-09-27 (M6c):* `last_ok_at`, `last_error_at`, `last_error`; rows also for `worker` (liveness: written after every step, job and send page) and `ses.feedback`. Replaces a queue's cron tables. |
| `operator_switches` | The emergency stop (*added 2026-09-27*, M6c) | one row: `sending_paused` bool, `changed_at`, `changed_via` (`console`/`cli`); read before every claim (operations plan §7.3). |
| `erasures` | Erasure requests (*added 2026-09-27*, M7) | `address_hash` (SHA-256 of the canonical address — never the address), `erased_at`. Lets a restore re-apply every erasure made after the snapshot (lean-platform plan §5). |
| `operator_events` | Incidents for the operator (*added 2026-09-27*, M6c) | `kind`, `level`, `service`/`problem`/`fix`, `refs` jsonb, `first_seen_at`, `last_seen_at`, `count`, `notified_at`, `acknowledged_at`; the same incident within 6 hours raises `count` (a module constant, operations plan §4.2); deleted 180 days after acknowledgement (operations plan §4). |

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

`YouTubeConnector` implements it with `data_api.py`: one function per endpoint, httpx, API key, `fields` parameter to keep payloads small, ISO-8601 duration parsed with a 10-line regex, ids chunked at 50. `videos.list` with `part=snippet,contentDetails,status,liveStreamingDetails` (same 1 unit) also reads `status.madeForKids` (comments are disabled by policy → skip the comment call); `ContentItem.published_at` is `liveStreamingDetails.actualStartTime` when present, otherwise `snippet.publishedAt` — for premieres and live streams `publishedAt` is the time the broadcast was scheduled, not the time it went live, and the delay must count from go-live. All Data API error mapping happens once, in the client's single request helper: httpx transport errors and timeouts, 5xx, 429, 400 `processingFailure` and 403 `rateLimitExceeded` → `TemporaryError`; *Changed 2026-09-20:* 403 `quotaExceeded`/`dailyLimitExceeded` and a rejected API key → `NeedsOperator` (§9.4), because the retry ladder cannot fix either and must not spend a video's attempts on them; 403 `commentsDisabled` → empty comment list; any other 4xx → permanent. Captions: 403 → `TranscriptUnavailable("forbidden")`, 404 → `TranscriptUnavailable("no_captions")` — never retried, each attempt costs 250 units. Latest uploads come from the `UU…` uploads playlist (the `UC→UU` substitution is folklore that works; on `playlistNotFound` fall back to `channels.list?part=contentDetails`), using `contentDetails.videoPublishedAt`. The captions endpoints (`captions.list`, `captions.download`) live in the same client, called with a bearer token instead of the key. `QUOTA_UNITS = {"videos.list": 1, "channels.list": 1, "playlistItems.list": 1, "commentThreads.list": 1, "captions.list": 50, "captions.download": 200}` sits next to the functions and every call logs `quota.youtube` with its units (§12).

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
                 tokens_cached: int = 0; tokens_cache_write: int = 0   # parts of tokens_in

class LLMGateway(Protocol):
    def complete_json(self, *, model: str, system: str, user: str, schema: type[BaseModel], max_tokens: int) -> Completion: ...
```

*Changed 2026-09-19:* a model the provider no longer serves (404) is `NeedsOperator` naming the model and where it is configured; the worker logs `llm.models` at start. *Changed 2026-09-19 (first live call):* every output model derives from `Strict` (`extra="forbid"`), because the provider refuses a strict schema unless each object carries `additionalProperties: false` — until then every summary against the real model failed permanently. *Changed 2026-09-27 (the gateway is removed — full specification in `2026-09-lean-platform-plan.md` §2):* `AnthropicGateway` POSTs to `https://api.anthropic.com/v1/messages` (`x-api-key: ANTHROPIC_API_KEY`, `anthropic-version: 2023-06-01`) with a top-level `system`, one `user` message and `output_config={"format": {"type": "json_schema", "schema": schema.model_json_schema()}}`, parses the first `text` content block into the Pydantic model (one retry with the validation error appended on failure), treats `stop_reason` `max_tokens`/`refusal` as `LLMError`, and maps usage so cached tokens stay inside `tokens_in` (`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`). A unit test rejects any output-model schema keyword the API does not support.

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

`summarize.py` builds the user prompt from the transcript as `[mm:ss] text` lines (the model cites these markers; jump links become `{url}&t={seconds}s`) and calls the `LLMGateway` with the one variant-independent summary prompt (length rules for every field live in `summary_v1.md`, so the compact block stays under 300 words). Ceiling: one call up to `content.max_transcript_chars`; above that the appearance is skipped and the creator notified (`# ponytail: single-call summarisation; add map-reduce chunking when a real video exceeds the ceiling`).

`comments.py` (pure function, unit-tested): drop `< min_words`, drop containing URLs, drop `author_channel_id == source.external_id`, dedupe by normalised text (copy-paste spam), cap at `max_count`. `sentiment.py` feeds the survivors (text + like count only) to the sentiment prompt. No comments (disabled, made for kids, or none pass the filter) → no `Sentiment`; templates render the box only when present (manifest §3.1 "Features degradieren sauber").

### 8.4 Delivery (`app/delivery`)

```python
@dataclass(frozen=True)
class OutgoingEmail:
    from_name: str; from_address: str; to: str; reply_to: str; subject: str; html: str; text: str
    headers: dict[str, str]; tags: dict[str, str]          # changed 2026-09-27 (SES plan §4.2)
```

`render.py` composes every mail: `render_summary_mail(creator, appearance, summary, sentiment, subscription: Subscription | None) -> OutgoingEmail` and siblings for confirm, preview, notice, magic link, contact relay. It fills `from_name` = `"{creator.name} via {product.name}"` and `from_address` = `sender_address` (two fields since M6a: a name with a comma broke a formatted `From`; the client builds the header with `email.headerregistry.Address`), `reply_to` = the creator's reply-to or `support_email` (no `noreply`, manifest §7.6), `headers` = `List-Unsubscribe: <{base_url}/abmelden/{subscription.unsubscribe_token}>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, and `tags` (`kind`, plus `mailing` and `delivery` on fan mails), which the client sends as SES message tags so a bounce event names the mailing that caused it. *Changed 2026-09-27:* the idempotency keys (`mailing/…`, `preview/…`, `notice/…`) are gone with Resend — SES has none; fan mails are protected by claim-before-send instead (§9.2, SES plan §5). `subscription=None` is the creator preview: no `List-Unsubscribe` headers, and the footer's per-subscription sentence is replaced by "Vorschau für {creator} — so sehen deine Abonnenten die Mail" with the stop/postpone action bar on top. HTML goes through `css_inline.inline(html, load_remote_stylesheets=False)`; the text part is rendered from a `.txt` template (no HTML stripping heuristics). The M4 header/sender tests assert on the `OutgoingEmail` captured by the fake.

**Payload freeze.** Every mail of one mailing is rendered from `mailings.render_snapshot` — the creator's `name`, `email_variant`, `greeting_text`, `farewell_text`, `reply_to_email`, `logo_url` and `accent_color`, copied onto the row in the same statement that sets `preview_sent` (§9.2). It buys two things at the price of one jsonb column. First, the fans get exactly the mail the creator saw and chose not to stop — without it, a settings change inside the stop window silently sends something else than what was previewed, which is the whole point of manifest §3.1's "Vorschau mit Stopp-Fenster". Second, the part of a list sent after a retry up to ~23 h later (§9.4) gets byte-for-byte the mail the first part got. (*Changed 2026-09-27:* the original second reason — a stable payload under a provider idempotency key — ended with Resend.) A variant switch still applies instantly to every mailing before its preview and to every summary page; changing a previewed mail means stopping or postponing it, which rotates the token and produces a fresh preview with a fresh snapshot.

*Changed 2026-09-27 (Resend replaced by Amazon SES — full specification in `2026-09-ses-migration-plan.md` §4):* `SmtpClient` (`email_client.py`) is transport only: `send(mail) -> str` sends one mail on its own connection, `session()` yields one connection for a page of fan mails; both build a `multipart/alternative` `EmailMessage` from the `OutgoingEmail` and run `mail` / `rcpt` / `data` themselves, because only that tells where a failure happened. `530`, `535` and `554` (credentials, IAM policy, unverified identity or sandbox), a server that does not offer STARTTLS, and `454` daily quota are `NeedsOperator`; other `4xx` are temporary; other `5xx` permanent (`EmailError`, logged `email.refused`); a timeout or disconnect **inside `data()`** is `DeliveryUncertain` — the mail may have been accepted. Sends are spaced to `email.max_send_rate_per_second`. `# ponytail: any 5xx stops the whole mailing until the operator acts; SES rejects nearly nothing per recipient, add per-address handling only if that happens.` The SNS signature check for the feedback webhook is `delivery/sns.py`.

`mailing.py` holds the lifecycle functions used by the steps and the routes (§9); mailing status is written only here. Every transition is one conditional statement, `UPDATE mailings SET … WHERE id = :id AND status = :expected`, and the caller checks the rowcount: 0 rows means another writer (stop/postpone route, reschedule, or a step) moved the row first; the caller logs `mailing.transition_lost` (expected, actual) and returns without further side effects. This is what lets the web process and the worker write the same row without a lock between them.

### 8.5 Jobs (`app/jobs`, `app/worker.py`)

`worker.py` is the worker process: `while not stopping: run_tick(now); sleep(settings.worker.loop_seconds)`, where a tick takes the **leader lock** (*added 2026-09-27*: `advisory_lock(WORKER, 0)` from `app/db/locks.py`; not obtained → skip the tick — a deploy briefly runs two containers, lean-platform plan §4), runs due steps, due mailings and periodic jobs, and afterwards pings the heartbeat URL at most every 5 minutes; structured logging around each step and Sentry capture on unexpected exceptions. SIGTERM sets the stop flag; the send loop reads it before each claim, so a deploy never leaves an uncertain fan (SES plan §5). In production the worker runs in the same container as the web process (`ops/start.sh`, §15.2). `# ponytail: one sequential worker and the only step runner (the CLI ingests, never runs steps); add SELECT … FOR UPDATE SKIP LOCKED and a second worker when one channel's volume is no longer enough.` `run_due_steps(now)` selects, per status, rows whose `next_attempt_at IS NULL OR <= now` and calls the step function for that status with the same `now` (§9.3); steps never call `datetime.now()` themselves, which is what makes the stepped-clock tests in §14 possible. `run_periodic_jobs` reads `job_runs` and runs a job when it is due: today by interval only (`feed_poll_hours`; daily: cleanup; the billing jobs from M7b); *changed 2026-09-27 (M6c, operations plan §6):* each job gets a `due(row, now)` from `schedule.py` — `every(interval)` or `daily_at(clock time)` — and the clock-time jobs are the backup at `operations.backup_time` (03:30, so a restart never lets it drift into a send) and the daily operator mail at `operations.digest_time` (07:00). *Changed 2026-09-18 (M5 review):* the due run is recorded and committed **before** the job starts, each job in its own transaction: a job failing for any reason then waits its interval instead of re-running every tick with a traceback, and one failing job never costs another its run. A feed answering with something that is not XML is a temporary error of that one channel. Steps stay thin: the work is one call into the owning layer module (`transcripts.service`, `analysis.summarize`/`sentiment`, `delivery.mailing`); appearance status is written only by the steps in `jobs/steps.py`, mailing status only by `delivery/mailing.py`, which steps and routes both call.

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

`services.py` builds the concrete clients lazily, once per process: `Services(youtube: SourceConnector, transcripts: list[TranscriptProvider], llm: LLMGateway, email: SmtpClient, sns_certificates: SnsCertificates, …)` (*Changed 2026-09-27*) behind `get_services()` (module-level cache, built from `get_settings()` on first call). The connector level is injected, never the raw Data API client; `transcripts` is the provider chain in order. The public Atom feed GET in `feed.py` is a plain httpx call and not a Services member; its parsing is unit-tested from `fixtures/feed.xml` and the poll's filter through `ingest_item`. Routes and steps call `get_services()` directly — steps take only ids and `now`, so this accessor is the one seam through which fakes enter. The module exposes exactly one override, `set_services(services | None)`, used only by `tests/conftest.py` (`# ponytail: process-global override; switch to explicit injection if a second process model ever appears`). This is the entire dependency-injection story.

`cli.py` is argparse plus one function call per subcommand; the operations live in the owning layer (`onboard` → `sources/youtube/connector.py` + `db`; `backfill`/`process`/`poll` → `jobs/steps.py`; `demo-mails`/`eval-prompts` → `delivery/render.py` and `analysis`; `status` → `app/ops/status.py`, M6c). `backfill`, `process` and `poll` only **ingest** (`ingest_item` → `detected`); they never call a step function — the worker is the single process that runs steps, and a second runner would repeat the same expensive step on the same row. Progress is watched with `cli status`; locally the worker started by `docker compose up` picks the rows up within `worker.loop_seconds`. The CLI tests exercise the layer functions, not argparse.

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
| `sending` | `sent` | `send` (same run or a resumed run) | *Changed 2026-09-20 and 2026-09-27* — the send loop, specified in SES plan §5: pages of 100 pending deliveries (`attempted_at IS NULL`, subscriber not blocked — re-read per page) `ORDER BY id`, one SMTP session per page. Per recipient: render → wait for the rate spacing → stop check → **claim** (`attempted_at = now`, commit) → send → `sent_at = now` and `attempts` reset, one commit. Any failure except an uncertain one releases the claim and raises (retry ladder); an uncertain one keeps the claim, logs `email.uncertain` and ends the run (> 3 per mailing → `NeedsOperator`). No pending row left → `sent`, `sent_at`, `recipient_count` (sent rows only), committed inside the advisory lock. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `stopped` | creator stop link | Terminal. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `scheduled` | creator postpone link | `send_at += postpone_hours`, capped at `published_at + max_delay_hours` (beyond the cap the confirmation page offers only "stoppen"); `stop_token` rotated so older preview links die (manifest §7.9 "einmal verwendbar"); sentiment is refreshed at the new `T−2h`. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `scheduled` | creator changed `send_delay_hours` in settings | *Changed 2026-09-18 (M6):* built with M7, together with its only caller, the settings page; the rule itself is unchanged. Only when the delay value changed **and** the new `send_at` differs; status falls back to `scheduled` only from `sentiment_ready`/`preview_sent`; `stop_token` rotated exactly as on postpone (one rule: a new schedule is a new token and a new preview). Saving a greeting touches no mailing. Logged as `mailing.rescheduled` with old/new. |
| `preview_sent` | (stays) | `send`, when the SES daily quota left does not cover the recipients (*added 2026-09-27*) | The send does not start; parked for the operator (`NeedsOperator` with both numbers); the console shows it days ahead (SES plan §5). |
| `sending` | — | — | Never stopped or rescheduled by the creator: the send has begun. |
| `sending` | `cancelled` | the operator's "Rest abbrechen", only while the emergency stop is on (*added 2026-09-27*, operations plan §7.3) | Conditional (`… WHERE status = 'sending'`); recipients already sent stay counted, the rest never get it; the creator gets the `send_failed` notice. |
| `scheduled` / `sentiment_ready` / `preview_sent` | `failed` | the 12-hour rule (§9.4) | A mailing that has not started sending and whose `send_at` is more than 12 hours past ends instead of going out days late; checked before any mailing work in every tick (*changed 2026-09-27*: before, only when a parked row failed again). A mailing in `sending` is never ended by the clock while it makes progress — only when it stays parked past the 12 hours (unchanged) or by the operator's "Rest abbrechen". |
| `sentiment_ready` / `preview_sent` / `sending` | `failed` | `send_preview` or `send` after `MAX_ATTEMPTS` temporary errors (§9.4) | Terminal for the automation; operator alerted (Sentry), creator notified. Recovery is manual and documented in the runbook: fix the cause, then `UPDATE mailings SET status = '<previous state>', attempts = 0` — a half-sent mailing resumes from `sending` and skips the deliveries already marked. |

**Concurrency guard for `send`:** the step holds a **session-level** advisory lock for its whole duration — `pg_try_advisory_lock(MAILING, mailing_id)` via `app/db/locks.advisory_lock` (*Changed 2026-09-27*, M6b: the two-key form, so no mailing id collides with the worker's leader lock) on a dedicated connection (`engine.connect()`, outside the session used for the transactions) taken before the snapshot transaction, `pg_advisory_unlock` in `finally`; not acquired → log and return. A transaction-scoped lock would be released by the first commit and leave the batch loop unprotected. If the worker dies, Postgres releases the lock with the connection. This covers the only realistic overlap — Render's zero-downtime deploy runs the old and the new container side by side — up to `maxShutdownDelaySeconds` (300 s) after the new one is healthy (§15.2); the old worker stops between two mails on SIGTERM, and the worker's leader lock covers the rest of the pipeline — and the resumed run then selects only rows with `attempted_at IS NULL`; a claimed row without `sent_at` is uncertain and never selected again.

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
| `notify_creator(session, creator, kind, context)` | called by steps | Sends a `creator_notice` mail (`kind` ∈ `no_transcript`, `too_long`, `oauth_reconsent`, `failed`; *Changed 2026-09-18 (M6):* plus `preview_failed` and `send_failed` for a mailing, because `failed`'s "no mail goes out" is untrue for a half-sent one). A mailing's notice is sent only after its `failed` state is committed, and only by the call that wrote it. | — |
| `poll_feeds(now)` | periodic, every `feed_poll_hours` | Fetches each source's public Atom feed (15 newest entries), `ingest_item` for each. `# ponytail: the 6-hourly poll is the only upload trigger; add PubSubHubbub push when a creator needs sub-hour detection.` | logged, next run |
| `cleanup(now)` | periodic, daily | Deletes `pending` subscriptions whose `confirm_expires_at < now` and `unsubscribed` ones whose `unsubscribed_at` is older than `unsubscribed_retention_days` (*Changed 2026-09-18 (M5 review):* subscribers without remaining subscriptions too, except `complaint` blocks; an address a sign-up is holding is skipped with `FOR UPDATE SKIP LOCKED`, so the sweep never deletes a subscription being added); re-checks with `videos.list` (chunks of 50, 1 unit each) **every appearance in `analyzed`**, regardless of mailing state and age, and marks deleted/private ones `unavailable` — a mailing-bound selector would never reach a backfill row, which by §9.5 gets no mailing at all and whose `/s/` page is exactly what the confirmation page hands every new fan (§10); for one channel this is a handful of 1-unit calls a day (manifest §7.9 "nachträglich gelöschte Beiträge"; also keeps stored API data consistent per YouTube API policy). | logged, next run |
| `backup` | periodic, daily at `operations.backup_time` (03:30; *added 2026-09-27*) | Encrypted `pg_dump` to B2 via restic, pings the backup check (lean-platform plan §5). | logged, incident, `/fail` ping; next run |
| `operator_digest` | periodic, daily at `operations.digest_time` (*added 2026-09-27*) | The daily operator mail (operations plan §6); the worker's tick also mails new `error` incidents at once (§4 there). | logged, next run |

### 9.4 Retries and failure

Steps raise `TemporaryError` (`app/errors.py`; `TranscriptTemporaryError`, the Data API and OAuth temporary errors and the mail client's temporary error subclass it — the worker catches exactly this one type) or a permanent error (mapped to a terminal status immediately). On a temporary error the worker sets `attempts += 1`, `next_attempt_at = retry_at(attempts, now)` and `last_error`, where `retry_at` waits `5 min × 2^(attempts−1)` capped at 6 h: 5, 10, 20, 40, 80, 160, 320 min, 6 h, 6 h — nine waits, ≈ 23 h in total for `MAX_ATTEMPTS = 10`, inside the 48 h minimum delay. After the last attempt the row becomes `failed` (appearance, or mailing for `send_preview`/`send`), the operator is alerted and the creator notified. `prepare_sentiment` uses the same ladder but stops at the preview deadline (§9.2) and never fails. Successful steps reset `attempts` to 0. `CostCapExceeded` is the one temporary condition that is not a retry: like `not_public_yet` (§9.1) the worker sets `next_attempt_at = now + 6 h`, leaves `attempts` unchanged and logs WARNING `llm.cost_cap_hit` — the row waits for the daily reset and never reaches `failed`. This is the whole retry system: two columns and one function. *Changed 2026-09-19 (owner: "Logs und Fehler müssen klar erkennbar sein"):* a rejected credential or an exhausted plan — YouTube key or daily quota, the Anthropic key, workspace or credit, the SES SMTP credentials, IAM policy, sandbox or daily quota (*Changed 2026-09-27*) — is `NeedsOperator` (`app/errors.py`), not a `TemporaryError`: the row waits one hour without counting an attempt, is not written to the creator about and does not climb the retry ladder — **except a mailing**: a mailing may not wait forever, because its preview has named a time (`GIVE_UP_ON_A_MAILING_AFTER = 12 h` in `worker.py`, ARCHITECTURE). *Changed 2026-09-27 (M6c):* this **12-hour rule** is checked at the start of every tick's mailing work for every mailing that has not started sending — after a parking, an outage or an emergency stop alike — and one whose `send_at` is more than 12 hours past ends as `failed` with the honest notice for its state; nothing *starts* days late. A mailing already `sending` keeps the existing rule: it ends by the clock only if it stays parked for the operator past the 12 hours (then `send_failed`, half-sent), never while it makes progress — ending a progressing list would strand the rest for good (the code comment on `GIVE_UP_ON_A_MAILING_AFTER` says so). Appearances have no such limit (nobody was promised anything). The retry ladder itself resets whenever a mail goes out (SES plan §5), so a long list is never ended by scattered hiccups; and every attempt logs `operator.action_needed` at ERROR with service, the provider's own words and the setting to check. Before this, a revoked key turned every video in flight into `failed` and wrote each creator a notice about our misconfiguration. Worker and web process also log `config.secret_missing` at start for each empty secret they need.

### 9.5 Backfill (manifest §6.1)

`cli backfill <slug> [--count N]` (default `content.backfill_count`, 10–20 for the Phase 0 demo): `latest_items(limit=N)` via the uploads playlist (1 unit) → `ingest_item(..., allow_backlog=True)` → the CLI returns; the worker runs pre-onboarding items to `analyzed` (with the sentiment produced at backfill time instead of at `T−2h`) and creates no mailing, while an item published after `source.created_at` that the poll has not seen yet is ingested as a normal upload and mailed. `cli status` shows progress. Summary pages — with sentiment box — exist from day one; the confirmation page links to the newest one (rule in §10).

## 10. Web surface: routes and pages

Three areas in one app (manifest §5.1). All pages: one font family, one accent colour (the creator's on fan pages, ours on the landing page), real labels, keyboard-usable, contrast-checked (manifest §5.5). Every state-changing link from an e-mail lands on a confirmation page and acts on POST — corporate and Gmail link scanners prefetch GET links.

| Route | Area | Method | Behaviour |
|---|---|---|---|
| `/` | A | GET | Landing page from `landing.html`: promise + "Gespräch vereinbaren" button, three steps, a real example mail (static snapshot `partials/example_mail.html`, produced once by `cli demo-mails` from a pilot video, with the pilot's written consent — §20 q10), price tiers rendered from `[pricing]` with the five-line rules block (*Changed 2026-09-21*, billing plan §7), a slot for the product video (*added 2026-09-27*, M10), feature preview from `config/roadmap.toml` (`[[features]]` with title/benefit/status: live / in progress / planned), trust section, FAQ (manifest §5.5). |
| `/kontakt` | A | POST | Rate-limited; relays the message to `support_email`; HTMX inline confirmation. |
| `/impressum`, `/datenschutz` | A | GET | Static templates; text provided by the owner (must mention YouTube API services and Google's privacy policy). |
| `/health` | ops | GET | `{"status": "ok"}` after a `SELECT 1`; Render health check (without it Render only probes the TCP port). |
| `/betrieb`, `/betrieb/zeitplan`, `/betrieb/probleme` | ops | GET + POST actions | *Added 2026-09-27:* the operator console — health, schedule, incidents; HTTP Basic with a failure counter, `noindex`. Its writes, each a same-origin POST behind a confirmation page and each recorded as an incident: "erledigt" on an incident, the emergency stop on/off, "Stoppen" on a mailing not yet sending, "fortsetzen"/"Rest abbrechen" on a `sending` mailing while the stop is on (operations plan §5, §7.3). |
| `/k/{slug}` | B | GET | Sign-up page in the creator's branding: logo, name, greeting, three sentences, one e-mail field, one button (manifest §5.1). Unknown slug → 404 page. |
| `/k/{slug}` | B | POST | Rate-limited. Validates and normalises the address (*Changed 2026-09-18 (M5 review):* strictly, with an MX lookup — `app/addresses.py`; a rejected address gets the form back with the text kept and an error, which reveals nothing about who is subscribed), then by subscription state: none or `unsubscribed` → row becomes `pending` with a fresh `confirm_token` and `confirm_expires_at`; `pending` → same, token refreshed; **`confirmed` → nothing changes** (status, tokens), only the confirm mail is sent again — its link lands on the "Dabei!" page. The public form can therefore never demote a fan. A blocked subscriber gets no mail at all, for either reason (*Changed 2026-09-18 (M5 review):* bounce blocks are permanent, §7). Independently of the IP limit, at most one confirm mail per address per `web.confirm_cooldown_minutes` (renamed 2026-09-27), **across all creators** — the newest `confirm_sent_at` of any of the address's subscriptions, read under a row lock on the subscriber (`INSERT … ON CONFLICT DO UPDATE … RETURNING`), so two simultaneous sign-ups cannot both see "nothing sent yet": the IP limit alone lets one attacker drive thousands of confirm mails a day at a third party's mailbox, and those spam complaints land on the sending subdomain the whole platform shares (manifest §11). A throttled request changes nothing and answers normally. Always answers "Schau in dein Postfach" (no enumeration) — *Changed 2026-09-18 (M5 review):* and just as fast: the session commits before the response and the confirm mail is sent after it (a background task), so a blocked or throttled address, which sends nothing, is not measurably quicker. A 429 from the IP limit is an HTML page, or a fragment the sign-up page tells htmx to swap in. |
| `/k/{slug}/bestaetigen/{token}` | B | GET | Looks the subscription up by `confirm_token`; `pending` and not expired → `confirmed`, `confirmed_at = now` (*Changed 2026-09-18 (M5 review):* no longer lifts a bounce block, §7); already `confirmed` → no-op; `unsubscribed` → the expired page, because a fetched link must not undo a decision to leave. Both show the branded "Dabei!" page with a link to the newest summary page, if any — *newest* = the appearance with the latest `published_at` whose status is `analyzed` and which either `is_backfill` or has a mailing in `sent`; open, `stopped` and `cancelled` mailings are excluded, so the page can never hand out a summary before the list receives it or after the creator stopped it (manifest §3.1 "Original zuerst"). The token is **kept** (confirming is idempotent, so a scanner prefetch followed by the real click shows the same page); expired or unknown → 410 page in the creator's branding with a new sign-up link. Confirm stays GET (a prefetch confirming a sign-up the person requested is acceptable and common). |
| `/abmelden/{token}` | B | GET | One-button confirmation page. |
| `/abmelden/{token}` | B | POST | Unsubscribes that subscription (per creator; manifest §7.7); also the RFC 8058 one-click endpoint (form-encoded `List-Unsubscribe=One-Click`). Always 200. |
| `/s/{view_token}` | B | GET | "Online ansehen" page: creator branding, the **full** summary — the `detailed` block, independent of the creator's mail variant (shared partial) — sentiment box, video link, "Auch abonnieren" link to `/k/{slug}`, the platform footer partial with the "Automatisch erstellt … kein Ersatz für das Original" notice and Impressum/Datenschutz, `X-Robots-Tag: noindex, nofollow` + meta robots, no navigation, no archive (manifest §3.1, §5.1, §7.9). `unavailable` → 410 page. Otherwise the page renders as soon as a `summary` analysis exists, independent of mailing state: the token is the only gate (256 bit, §13) and circulates only through sent mails, the creator preview and the confirmation-page link, so the preview's "Online ansehen" link works before send. `# ponytail: no per-state visibility check; add one if tokens ever leave those three channels.` The page deliberately does **not** mirror `creator.email_variant`: manifest §7.6 names the third variant "Teaser mit Volltext online", so a teaser mail's "weiterlesen" link must arrive at the full text — a page mirroring the variant would show the same teaser plus a link to itself, and the full summary would exist nowhere. The variant governs the mail only. |
| `/s/{view_token}/gelesen` | B | POST | *Added 2026-09-27 (M7):* fired once by the summary page after it has loaded, only when opened with `?von=mail`; increments `appearances.mail_views`; no cookie, no personal data; rate-limited; 204. Unknown or unavailable token → 204 as well (nothing to learn from it). |
| `/creator/login` | C | GET/POST | E-mail form; POST rate-limited; if the address belongs to a creator, sends a magic link (`magic_link_minutes`, hashed token in DB). Always the same response. |
| `/creator/login/{token}` | C | GET | Renders a one-button "Anmelden" page (does not consume the token). |
| `/creator/login/{token}` | C | POST | Validates hash + expiry, clears the token (single use), sets the session cookie, redirects to `?next=` (settings by default; the OAuth start during onboarding). |
| `/creator/einstellungen` | C | GET/POST | Session required. Form: delay (within min/max), min length, variant (radio with a one-line description each; real previews via `cli demo-mails --send-to`), greeting, farewell (plain text, ≤ `max_custom_text_chars`), logo URL, accent colour, reply-to. Saving applies the reschedule rule from §9.2 and shows a HTMX confirmation. Also shows: list size, OAuth status with a "YouTube verbinden" button, the sign-up link to copy. |
| `/creator/abonnenten.csv` | C | GET | Session required. `email,confirmed_at` of confirmed subscriptions (manifest §7.9). |
| `/creator/youtube/verbinden` | C | GET | Session required. Stores a random `state` in the session and redirects to Google (§8.1). |
| `/creator/youtube/callback` | C | GET | Checks `state`, exchanges the code, verifies the granted channel matches the source (`channels.list?mine=true`, 1 unit), stores the encrypted refresh token, clears `oauth_needs_reconsent`. |
| `/creator/abmelden` | C | POST | Ends the session. |
| `/m/{stop_token}/stoppen`, `/m/{stop_token}/verschieben` | C | GET → confirm page, POST → action | Valid only while the mailing is in `MAILING_STOPPABLE`; the token is the credential, single-purpose, rotated on postpone and reschedule, dead once the mailing is sent. The POST is the same conditional update (`… WHERE stop_token = :token AND status IN MAILING_STOPPABLE`); 0 rows → the page says the mail is already being sent (or was already stopped), never "gestoppt". Past the postpone cap the page offers only "stoppen". |
| `/webhooks/ses` | hooks | POST | *Changed 2026-09-27 (was `/webhooks/resend`; specified in SES plan §6.2):* raw body, an SNS message, verified in the thread pool: `TopicArn` must equal `SES_FEEDBACK_TOPIC_ARN` (empty = refuse all); `SignatureVersion` 2 only; signing certificate only from `https://sns.<region>.amazonaws.com/….pem`, the region taken from the topic ARN; RSA/SHA-256 check. A `SubscriptionConfirmation` is logged (`webhook.ses_subscription`, WARNING, with its `SubscribeURL`) and confirmed once by the operator — the app makes no outgoing request. A `Notification`: a `Permanent` bounce (any subtype, incl. `OnAccountSuppressionList`) → block as `bounce`; a `Complaint` → block as `complaint`; one conditional `UPDATE` that touches only rows that change (unblocked → blocked, bounce → complaint), keeps the first block's date and never turns a complaint back into a bounce; `Transient`/`Undetermined` bounces are logged, nothing blocked; `Delivery`, `DeliveryDelay` and `Reject` are logged with kind, mailing and delivery ids, never the address; anything else is logged and ignored. No dedup table: writes are set-to-value, so at-least-once delivery and replays are no-ops. A bad signature, a foreign topic or an empty topic setting gets 401 (SNS retries; failures show in CloudWatch); everything signed gets 200. |

Onboarding itself (contract, OAuth link, branding) runs by conversation and CLI in the MVP (manifest §5.1 C): `cli onboard --slug --name --email --channel-id` creates creator + source, resolves the channel (title, avatar as default logo) and prints the sign-up URL; the creator logs in himself via `/creator/login` with the onboarded `contact_email` and connects YouTube from the settings page; `cli backfill <slug>` processes the back catalogue.

## 11. E-mail: variants, framing, deliverability

Implements manifest §7.6 exactly.

**Fixed frame (platform fingerprint)** in `email/base.html`: sender display name `"{creator} via {product}"`; subject `"{creator}: {video title}"`; header with logo, name, accent colour and the fixed line "Zusammenfassung für Abonnenten von {creator}"; the creator's greeting; the variant body; the creator's farewell; the platform footer partial: "Du bekommst diese Mail, weil du dich am {confirmed_at} über {base_url}/k/{slug} für die Zusammenfassungen von {creator} eingetragen hast. Automatisch erstellt mit {product} — kein Ersatz für das Original." followed by Abmelden · Online ansehen · Impressum · Datenschutz. The same footer partial renders on the summary page.

**Variants** are blocks in `partials/summary_body.html` selected by name (compact: two-sentence core message, 3–5 key points with jump links, one quote, sentiment box, video link, < 300 words; detailed: sections with key points each; teaser: core message + quote + "weiterlesen" to the online page, which always shows the full text — manifest §7.6 "Teaser mit Volltext online", see §10), all rendered from the same `Summary` — switching the variant on the settings page applies instantly, without re-summarising, to every mailing that has **not yet been previewed**; a previewed mailing keeps the variant its `render_snapshot` froze (§8.4), and the `/s/` page is unaffected either way. One `summary.txt` serves all variants (core message, key points, quote, links). A fourth variant = one template block + one line in `settings.email.variants`.

*Changed 2026-09-20:* every colour that carries text is derived from the creator's accent so it clears WCAG AA on a white mail, a light page and a dark one (`app/branding.py`, manifest §5.5); body and footer text are at least 16 px, hierarchy comes from colour and weight, not from smaller type. *Changed 2026-09-27 (milestone D):* `branding.py` reads the backgrounds and inks it checks against from `design.py` (today it hard-codes `#ffffff` and `#171612` — with a cream page it would certify contrast against the wrong background); mails use the system font stack only (a web font in a mail is a request to our server on every open — open tracking by the back door); mails declare `<meta name="color-scheme" content="light dark">` and keep one `@media (prefers-color-scheme: dark)` block through `css_inline` (`keep_style_tags=True`) — dark mode is checked in Apple Mail and Outlook; Gmail inverts colours itself and is checked for legibility only.

**Creator texts**: greeting and farewell are plain text, length-limited, escaped by Jinja autoescape, inserted at fixed positions. No placeholders, no editor (manifest §7.6).

**Other mails**: confirm/welcome (double opt-in: the confirm button and one sentence of what comes next; no summary link before confirmation), creator preview (fan mail with the action bar on top), creator notice (one template with a `kind` switch), magic link, contact relay.

**Deliverability** (*Changed 2026-09-27*, Amazon SES — setup step by step in the SES plan §9): dedicated sending subdomain `mail.<domain>` as SES domain identity (Easy DKIM, three CNAMEs), custom MAIL FROM `bounce.mail.<domain>` (MX + SPF), `_dmarc` with `p=none` first, open/click tracking **off** (the configuration set publishes no Open/Click events) unless the owner decides otherwise after reading the privacy implications (§20). Every fan mail has `List-Unsubscribe` + `List-Unsubscribe-Post`. Bounce/complaint notifications block the address for all creators; SES's account suppression list is on. Until production access is granted (needs the live website, M9) SES sends only to verified addresses, 200 a day — development runs against Mailpit. Gmail reports no complaints to SES: Gmail Postmaster Tools is set up for the domain.

## 12. Logging, observability, cost control

Manifest §7.8 "Beobachtbarkeit" and the owner's explicit requirement for important, transparent log files.

- **structlog** configured in `app/log.py` at process start (web, worker, CLI) before any logger is used: `merge_contextvars` first, ISO UTC timestamps, level, logger name, `dict_tracebacks`; renderer `JSONRenderer` when `settings.logging.json`, else `ConsoleRenderer(colors=sys.stderr.isatty())` — the setting alone picks the format, the TTY only decides colour. Stdlib loggers (`uvicorn`, `sqlalchemy.engine` at WARNING, `httpx`) are routed through `ProcessorFormatter` so every line has the same shape. Optional `RotatingFileHandler` when `settings.logging.file` is set (local development; on Render stdout is the log stream).
- **Context**: the request-id middleware binds `request_id`, `path`, `creator_slug` (when resolvable); the worker binds `step`, `attempt`, `appearance_id` / `mailing_id` / `creator_id` before the first log line of a step. Identify people by ids, never by e-mail address, in logs.
- **Event vocabulary** (constants in `app/log.py`, so grep works — the constants file is the authority, ARCHITECTURE.md describes only the naming scheme): `item.detected`, `item.skipped` (reason), `item.failed`, `transcript.fetched` (origin, language, is_generated, segments, chars, duration_ms), `transcript.unavailable` (reason), `llm.call` (purpose, model, prompt_version, tokens_in, tokens_out, cost_cents, duration_ms, ok), `llm.cost_cap_hit`, `mailing.scheduled` (send_at), `mailing.sentiment_ready` (comments_used), `mailing.sentiment_skipped` (reason), `mailing.preview_sent`, `mailing.batch_sent` (size, first_delivery_id), `mailing.sent` (recipients, duration_ms), `mailing.stopped` / `postponed` / `rescheduled` / `cancelled` / `failed`, `subscription.created` / `confirmed` / `unsubscribed` / `address_rejected` (reason) / `confirm_sent` / `confirm_failed`, `subscriber.blocked` (reason; only when a row actually changes), `creator.magic_link_sent` / `magic_link_failed`, `web.hostile_path`, `web.rate_limited`, `cleanup.done` (counts), `mailing.transition_lost`, `operator.action_needed`, `config.secret_missing`, `llm.models`, `llm.prices_stale`, *changed 2026-09-27 (SES plan §6, lean-platform plan):* `webhook.ses` (type, topic_ok, signature_ok) / `webhook.ses_subscription`, `email.delivered` / `delayed` / `bounced` / `complained` / `rejected` (kind, mailing, delivery, SES message id — never the address), `email.uncertain`, `email.refused`, `backup.done` / `failed` / `disabled`, `worker.not_leader`, `worker.heartbeat_failed`, `lock.unlock_failed`, *added 2026-09-27 (M6c):* `worker.downtime`, `worker.restarted`, `worker.exited` (the start script's line), `operator.login_failed`, `operator.notified` / `notify_failed`, `operator.digest_sent`, `incident.record_failed`, `mailing.sending_paused`, `operator.switch_changed`, `mailing.cancelled_by_operator`, `mailing.quota_insufficient`, `ses.feedback_silent`, *M7:* `subscriber.erased` (hash only), the M7a events (billing plan §6), `feed.polled` (source, entries, new), `worker.tick` (due counts, duration_ms), `step.retry` (attempt, next_attempt_at, error), `quota.youtube` (endpoint, units).
- **Levels**: INFO for step boundaries and counts, WARNING for skips, retries, bad signatures, cost cap, DEBUG for payload sizes and provider responses (never bodies with PII), ERROR with traceback for exhausted retries → Sentry when `SENTRY_DSN` is set (`sentry-sdk` with the FastAPI and logging integrations; `send_default_pii=False`).
- **Cost control** (manifest §7.9, §11): `llm_calls` is the ledger; `assert_under_cap` refuses calls above `daily_cost_cap_cents` per creator; `cli status` (M6c) prints today's cost per creator with one `SUM … GROUP BY`. YouTube quota is not counted in code (`# ponytail: per-process counters lie across web and worker; the Google Cloud console graphs quota`) — every call logs its units, so `grep quota.youtube` gives the number when needed. *Changed 2026-09-21:* the units are now counted in the database, per Pacific day, with a warning and an alarm before the limit (billing plan §6) — the owner wants to know before it breaks, not when.
- **Operational visibility without a dashboard**: `cli status` prints per creator: list size, pending/confirmed, open mailings with `send_at`, status and attempts, appearances in `failed` with `last_error`, today's LLM cost, last feed poll, cleanup and backup run, and (*added 2026-09-27*) the uncertain deliveries per open or recent mailing (SES plan §5). *Changed 2026-09-27:* these figures come from one query module (`app/ops/status.py`, M6c) and are shown by `cli status`, the operator console `/betrieb` and the daily operator mail alike; incidents are kept in the database for 180 days, beyond Render's 7-day log retention; alerts come through channels that do not depend on the platform (operations plan §3). That is the MVP's monitoring (manifest: "genug, um nachts zu schlafen").

## 13. Security and data protection

Manifest §7.9 and §9 (technical part only; contracts and legal texts are the owner's).

- **Tokens**: all URL tokens from `secrets.token_urlsafe(32)` (256 bit); magic links stored hashed (SHA-256), 15 minutes, consumed on POST only; stop/postpone tokens rotate on postpone and reschedule and die with the mailing; confirm tokens expire with the pending sign-up (7 days); unsubscribe tokens are permanent per subscription (must always work).
- **Webhooks** (*Changed 2026-09-27*, SNS instead of Svix): SNS SignatureVersion 2 (RSA/SHA-256) only; the signing certificate is fetched only over HTTPS from the SNS host of the configured region; the topic must be ours; every write is set-to-value, so replays are harmless and no timestamp window is needed; 401 on a bad signature, 200 for everything signed. An empty topic setting rejects everything (the lesson of the 2026-09-18 review: an empty secret must never mean "accept").
- **Request hygiene** (*Changed 2026-09-18 (M5 review):* ): request bodies are capped at 64 KiB (Starlette's `RequestBodyLimitMiddleware`), a path containing a control character is a 404 before it reaches a route (PostgreSQL rejects NUL in a string parameter, which used to surface as a 500), and every route's session commits **before** the response is sent (`Depends(get_session, scope="function")`) — a page that says "done" must not go out ahead of a commit that then fails.
- **No oracle in the response time** (*Changed 2026-09-18 (M5 review):* ): the sign-up and the creator login mail after the response (FastAPI background tasks), so an address that sends nothing answers as fast as one that does. A failed send releases the per-address brake, or withdraws the magic link, so a provider hiccup never locks anyone out.
- **Error tracking** (*Changed 2026-09-18 (M5 review):* ): Sentry runs with `send_default_pii=False`, `include_local_variables=False` (its scrubber checks only top-level names; frame locals held the mail provider's key, the settings and fans' addresses) and `max_request_body_size="never"` (sign-up forms carry addresses).
- **OAuth**: only the refresh token is stored, Fernet-encrypted with `MultiFernet` (rotation supported); access tokens are held in memory for the call; `invalid_grant` marks the source for re-consent and notifies the creator; `state` in the session. Redirect URIs must be HTTPS on a real domain (or `localhost`). The Google Cloud project must be **verified for the sensitive scope** before the pilot's grant can outlive 7 days (Testing status expires refresh tokens after 7 days) — prepared from M0 (Google Cloud project, consent screen) and submitted in M9, as soon as the homepage and the privacy policy are live — Google's review needs both (*changed 2026-09-27*; §17 M9, §19). Revocation is done by the creator in his Google account; `invalid_grant` handling covers it.
- **Sessions**: signed cookie (`SessionMiddleware`, `HttpOnly`, `Secure` in prod, `SameSite=Lax`), 24 h; state-changing creator forms are POST from same-site pages (Lax cookie is the CSRF defence; no third-party embedding).
- **Rate limits**: slowapi on sign-up, magic-link request, contact form; uvicorn `--proxy-headers` on Render so the real client IP is used, with `--forwarded-allow-ips` from `FORWARDED_ALLOW_IPS` (*changed 2026-09-27*): `*` until M9, then Render's proxy addresses — with `*` a client can forge `X-Forwarded-For` and get a fresh per-IP counter for every request (`implementation-notes.html` question 9); the per-address brake does not depend on the IP either way.
- **Data minimisation**: no raw comments stored, no IPs, unconfirmed sign-ups deleted after 7 days, unsubscribed subscriptions after 30 days, addresses without a subscription with them unless a complaint blocks them (*Changed 2026-09-18 (M5 review):* bounce rows included), deliveries keep only `attempted_at` and `sent_at`; *added 2026-09-27:* **backups** keep about one month of daily and weekly snapshots plus 30 days of hidden versions, so a deleted address is gone from them after at most ≈ 2 months — the privacy notice says so; a fan erased on request is recorded as a hash in `erasures`, and every restore re-applies those erasures and the cleanup before anything is sent (lean-platform plan §5); the delivery-status log lines carry ids, never addresses (SES plan §6); CSV export limited to e-mail + confirmation date; deletions by FK cascade with one SQL statement per case in the runbook (creator after the contractual grace period, a fan on request).
- **Visibility**: summary pages send `X-Robots-Tag: noindex, nofollow` and a meta tag, are not in any sitemap, and 410 when the video is gone.
- **Secrets**: never in the repo; `.env` is git-ignored; Render `sync: false` for all keys (*Changed 2026-09-27:* the gateway and its virtual key, setup token and config store are gone — lean-platform plan §7). The Anthropic key lives in a workspace with its own spend limit; the SES SMTP user may only send from the platform's identity; the backup key is restricted to its bucket and cannot delete — a delete only hides, and hidden versions stay 30 days (lean-platform plan §5); the restic password and the B2 key are also in the owner's password manager, so losing the Render account does not lose the backups.
- **Dependencies**: exact pins in `uv.lock`; `uv sync --locked` in Docker and CI.

## 14. Testing strategy

Manifest §10: "jede Aufgabe ... mit einem Test, der zeigt, dass sie funktioniert". House rules: testable code, and `uv run pytest` green before anything counts as done.

- **Unit tests** (no I/O, fast): Atom feed parsing from fixtures; SNS signature verification against a test key pair, SMTP reply-code mapping (*Changed 2026-09-27*); ISO-8601 duration parsing; SRT parsing; comment filter; `compute_send_at`, `next_mailing_step` and `retry_at` across edge cases (delay reduced below elapsed time, worker down across `T` — preview must still get its full stop window, postpone at the cap, premiere with `published_at` weeks in the past → `send_at ≥ now + min_delay_hours`); two attempts of one preview with `send_at` pushed in between announce the same send time; a mailing whose creator changes variant and greeting after `preview_sent` renders byte-identically from its `render_snapshot` (§8.4); settings loading and validation errors (including a model without a price entry); template rendering of all three variants with and without sentiment (snapshot the text part), footer notice present in mail and page; cost computation; `OutgoingEmail` composition (sender name and address, reply-to fallback, headers, tags); *added 2026-09-27:* every text/background pair of `design.py` in light and dark clears 4.5:1; every page and mail of `design_preview` renders; no template or stylesheet names a third-party host; the output-model schemas use no keyword the Anthropic API rejects.
- **Integration tests** (Postgres from `docker compose`, `DATABASE_URL_TEST`, one transaction per test rolled back; `set_services()` with fakes): ingest twice → one appearance; full chain detected → analyzed by calling `run_due_steps(now)` with `FakeTranscriptProvider` + `FakeLLMGateway`; premiere stays `detected` and enriches on the next run; DOI flow through `TestClient` (sign-up → confirm mail captured by `FakeEmailClient` → confirm → CSV export contains the address); already-confirmed re-signup resends the confirm mail; unsubscribe GET/POST; mailing state machine driven by `run_due_steps` with a stepped clock (`now` is a parameter everywhere); **never twice** (*Changed 2026-09-27*): `send` interrupted after a claim and re-run → that recipient is not sent again and is counted uncertain; a definite failure releases the claim and the retry sends it once; two `send` runs started concurrently → one delivery per subscription; bounce webhook blocks the subscriber and later mailings exclude him; a replayed webhook changes nothing; delay change reschedules only when the value changed and rotates the stop token; stop link blocks the send; stop committed between `send`'s load and its `sending` write (the fake `videos.list` commits the stop from a second session) → nothing sent, `mailing.transition_lost` logged, the same for postpone vs `send_preview`; postpone shifts, caps, rotates the token and refreshes sentiment; video made private before send → cancelled; magic link: GET twice does not invalidate, POST once does; backfill creates no mailings but writes a sentiment, and a post-onboarding upload ingested by `backfill` is still mailed; a bounced or complained address gets no confirm mail and stays blocked (*Changed 2026-09-18*: blocks are permanent); cleanup deletes pending and unsubscribed rows, marks a private sent video unavailable and a deleted backfill video too (its `/s/` page then answers 410); *added 2026-09-27:* one test sends through real `smtplib` into Mailpit and reads the message back (SES plan §8); the leader lock lets only one of two workers run a tick; the backup job's success and failure paths; the recipient snapshot at send start includes neither a `pending` subscription, nor one unsubscribed after the mailing was scheduled, nor one confirmed after the snapshot was taken — exactly one `deliveries` row and exactly one recipient at the fake.
- **Fakes** in `tests/fakes.py` duck-type the real classes; no `unittest.mock` patching of internals.
- *Changed 2026-09-18 (M5 review):* **Tests must fail when the rule breaks, not only pass when it holds.** The M5 review ran mutants against the suite (a dropped filter, a lost row lock, a whitelist turned blacklist) and many survived. Rules that guard money, privacy or reputation get a test that was seen failing against a mutant: the sign-up row lock (two sessions, one holding the lock), the cleanup's `SKIP LOCKED` (one session holding a subscriber), the confirmation page's link rule (other creator, unavailable video, every non-`sent` mailing state), the periodic schedule (+23 h / +24 h, a crashing job).
- **Prompt regression** (manifest §8 "Prompts sind Produkt"): `cli eval-prompts` runs the real model on the 3–5 fixed transcripts in `tests/fixtures/transcripts/` and writes the rendered mails to `out/` for eyeballing; run manually before changing a prompt version; not part of CI (costs money).
- **CI**: GitHub Actions workflow with Postgres and (*added 2026-09-27*) Mailpit service containers: `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`. Runs on every push and PR. The Mailpit round trip fails in CI instead of skipping (SES plan §8). `video/` is not built in CI.

## 15. Local development and deployment

### 15.1 Local (manifest §7.1 "Lokal startet alles mit docker compose up")

`docker-compose.yml` (*Changed 2026-09-27*): `postgres:17` (volume; `docker/init-test-db.sh` creates `app_test` for `DATABASE_URL_TEST`), `mailpit` (pinned `axllent/mailpit` tag; SMTP `1025:1025`, inbox UI and API `8025:8025` — every mail the local stack sends lands there and nowhere else, SES plan §8), `web` and `worker` built from the `Dockerfile` with the source mounted for reload (`uvicorn --reload` / `python -m app.worker`), both with `EMAIL__SMTP_HOST=mailpit` and `depends_on` Postgres and Mailpit. No LLM gateway: the worker calls Anthropic directly with `ANTHROPIC_API_KEY` from `.env` (lean-platform plan §2). `make`-free: `uv run` commands are documented in the README (`uv run alembic upgrade head`, `uv run app <command>`, `uv run pytest`). Host-run commands use the `settings.toml` defaults (`localhost:1025` for mail), which reach the published Mailpit port. Upload detection locally: `cli poll <slug>` or the worker's periodic poll; no tunnel needed.

### 15.2 Production: where it runs, and why (*Changed 2026-09-27* — decided with the owner)

**The owner's criteria:** stable, not complex to operate, cheap — with a target of **about €10 a month** (2026-09-27: "€28 is a lot of money; my hope was €10"). Mail is not hosted at all (Amazon SES, per use), the LLM is not hosted at all (Anthropic, per use), the design needs no tool, and the video is one static file.

**Decision: Render, region Frankfurt, Hobby workspace — one web service running web and worker, plus the smallest Postgres. ≈ €11.50 a month.** It keeps deploy-on-push, managed Postgres with point-in-time recovery, TLS, health checks and restarts, and needs no server administration and no SSH from the owner's machine (his work network blocks tunnels). What it took (lean-platform plan): the LLM gateway removed, web and worker in one container with a leader lock, backups run by the worker.

| Item | What | ≈ per month (before VAT) |
|---|---|---|
| `web` | Render web service `0.5c-512mb`, running uvicorn **and** the worker via `ops/start.sh` | $7.00 |
| `platform-db` | Render PostgreSQL 17, `0.1c-256mb` (+ $0.30 per GB of storage; < 1 GB in year one); 3-day point-in-time recovery on Hobby | $6.30 |
| Backups | Backblaze B2, EU region, restic-encrypted; first 10 GB free | $0 |
| Monitoring | UptimeRobot free (the `/health` check), Healthchecks.io free (worker heartbeat, backup), Sentry free developer plan (EU region), SES reputation alarms (CloudWatch, a few cents at most) | $0 |
| **Total** | | **≈ $13.30 ≈ €11.50**, plus mail (≈ $0.11 per 1,000) and LLM (≈ 3–8 ct per video) by use |

**When it grows:** the database moves to the 1 GB plan (≈ $19) only when its memory is measurably the bottleneck; a second service for the worker ($7) only if the single container's memory is (lean-platform plan §3); the Pro workspace ($25) is not needed while the off-site backup exists and the owner is the only operator.

**The alternatives considered** (prices from the providers' pages, 2026-09-27; details and sources in `implementation-notes.html`):

| Option | ≈ per month for this workload | Why not (or: why not now) |
|---|---|---|
| **Own VPS**: netcup VPS 500 (Germany, 2 vCPU, 4 GB) with `docker compose` + Caddy, restic to B2 | **≈ €7** on a 12-month term (€8.64 month to month) | The cheapest. But a server the owner owns: one day of setup (cloud-init, firewall, automatic updates, Caddy, a deploy workflow over SSH from GitHub Actions with a forced-command key, restic), then ≈ 15–30 minutes a month, and every incident is his. Stays the documented exit route (below). |
| Hetzner Cloud VPS | ≈ €6 + backups | New servers cannot be created by new customers (Hetzner status notice of 2026-06-26, still open); prices rose twice in 2026. |
| Render as before (web, worker, gateway as separate services) | ≈ €24 | Double the price for separation this platform does not need. |
| Railway (Hobby/Pro) | ≈ $10–25 | Postgres is a container on a volume, not a managed database with point-in-time recovery; volume backups only on Pro. |
| Fly.io | ≈ $40 + | Managed Postgres alone starts at $38. |
| Neon (free Postgres) + a PaaS | — | The worker queries every minute, so the free compute hours run out in about two weeks; the paid plan costs ≈ $19 for an always-on database. |
| Oracle Cloud Always Free | €0 | Allowance halved in 2026, idle instances are reclaimed, capacity errors are documented — not for the only production host. |
| Contabo, IONOS, Strato, OVH VPS | ≈ €4–10 | Cheap, but the same server work as netcup; Contabo's overselling is documented. |
| AWS/GCP/Azure (containers + managed Postgres) | ≈ $30–60 | IAM, networking, registry and infrastructure-as-code for a two-process app — complexity without a saving. |
| Coolify / Dokploy on a VPS | the VPS price | A web control panel with root on the server; both had critical vulnerabilities in 2026. |

**Exit route, kept open on purpose:** the same image and compose file run on any VPS; moving is Caddy in front, `restic restore` + `pg_restore` of the latest dump, and DNS. Trigger in `docs/backlog.md`: the Render bill passes €25 a month without a matching rise in revenue, Render's terms or prices change, or a customer requires an EU-owned processor.

**Data protection:** Render (Frankfurt), AWS (SES, Frankfurt), Anthropic, Backblaze (EU region, client-side encrypted), Sentry (EU region), Healthchecks.io and UptimeRobot (they see only ping URLs and the public `/health`), and Stripe (M7b) are processors or recipients: accept each DPA, list them in the privacy notice and in the owner's record of processing activities. Render, AWS, Anthropic and Backblaze are US companies (CLOUD Act) even with data in the EU — accepted for the MVP; the exit route is the answer if a customer objects.

**Verify before M9** (not confirmed from the documentation on 2026-09-27): that Render's terms allow commercial use on the Hobby workspace (the docs name no restriction — otherwise the Pro workspace, +$25); the Blueprint field `maxShutdownDelaySeconds` (and its maximum) and the value `autoDeployTrigger: checksPass`. *Confirmed 2026-09-27:* logs are kept 7 days on Hobby (14 on Pro) — the incident list and the database views keep what matters longer (operations plan §4); `RENDER_GIT_COMMIT` is set at runtime.

**`render.yaml` after M6b** (single environment, region `frankfurt`, private network):

```yaml
services:
  - type: web
    name: web
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: 0.5c-512mb                  # a paid plan is required for preDeployCommand
    region: frankfurt
    healthCheckPath: /health
    autoDeployTrigger: checksPass     # deploys every push to master once CI has passed (M6c; verify the value)
    maxShutdownDelaySeconds: 300      # a summary call in flight finishes (verify the field and its maximum)
    preDeployCommand: uv run alembic upgrade head
    dockerCommand: ./ops/start.sh     # uvicorn + worker, lean-platform plan §3
    envVars:
      - { key: DATABASE_URL, fromDatabase: { name: platform-db, property: connectionString } }
      - { key: SECRET_KEY, generateValue: true }
      - { key: LOGGING__JSON, value: "true" }
      - { key: EMAIL__SMTP_HOST, value: email-smtp.eu-central-1.amazonaws.com }
      - { key: EMAIL__SMTP_PORT, value: "587" }
      # sync: false — set once in the dashboard:
      # BASE_URL, SUPPORT_EMAIL, TOKEN_ENCRYPTION_KEYS, YOUTUBE_API_KEY, GOOGLE_OAUTH_CLIENT_ID,
      # GOOGLE_OAUTH_CLIENT_SECRET, TRANSCRIPT_PROXY_USERNAME, TRANSCRIPT_PROXY_PASSWORD,
      # ANTHROPIC_API_KEY, SMTP_USERNAME, SMTP_PASSWORD, SES_FEEDBACK_TOPIC_ARN,
      # EMAIL__MAX_SEND_RATE_PER_SECOND, WORKER_HEARTBEAT_URL, RESTIC_REPOSITORY, RESTIC_PASSWORD,
      # BACKUP_S3_KEY_ID, BACKUP_S3_SECRET, BACKUP_HEARTBEAT_URL, FORWARDED_ALLOW_IPS, SENTRY_DSN,
      # OPERATOR_EMAIL, OPERATOR_PASSWORD_HASH
      # (STRIPE_API_KEY from M7b)

databases:
  - name: platform-db
    plan: 0.1c-256mb
    region: frankfurt
    postgresMajorVersion: "17"        # must be explicit: the default is the newest major and cannot be changed later
    ipAllowList: []                   # reachable only from inside the private network
```

The real file keeps one `- key: … sync: false` entry per secret (the flow-style lines above are for reading); `sync: false` values are prompted on the first Blueprint apply and ignored on later syncs — a secret added later is set in the dashboard.

- **Deploy** = `git push` to `master` → CI → Render deploys once the checks have passed. Safe at any time by design; the console and the daily mail show the quiet windows (operations plan §7.1). **Emergency stop** for all sends: one button in the operator console (or `uv run app pause-sending on`) — a switch in the database that the send loop reads before every mail, so it takes effect before the next recipient, without a deploy or a restart (operations plan §7.3). **Rollback** = Render "rollback to previous deploy" (a migration is not rolled back — hence backward-compatible migrations, §3.1).
- **Backups:** the worker's daily job (lean-platform plan §5); first restore drill in M9, then quarterly.
- **Monitoring** (accounts created in M9): UptimeRobot on `https://<domain>/health` every 5 minutes; Healthchecks.io checks for the worker heartbeat (period 5 min, grace 30 min) and the backup (period 1 day, grace 2 h); Render's e-mail notification on failed deploys; Sentry with an EU-region DSN; SES reputation alarms (SES plan §9 step 8). All alerts go to the owner's mailbox.
- **Domain:** `<domain>` → the web service; `mail.<domain>` DKIM CNAMEs and the `bounce.mail.<domain>` MX + SPF as printed by SES; `_dmarc` TXT (SES plan §9).

The runbook `docs/runbooks/operations.md` lists the one-time setup (Google Cloud project + OAuth consent + verification, YouTube API key, the AWS/SES setup, the Anthropic workspace, B2 + restic, DNS, Render Blueprint, monitoring accounts, Sentry) and the recurring checks (quota, costs, failed rows, uncertain deliveries, restore drill).

## 16. Documentation deliverables

One authority per topic, everything else links there:

- **Configuration**: the comments in `config/settings.toml` and `.env.example`. README and ARCHITECTURE only point to them.
- **Layout and architecture**: `docs/ARCHITECTURE.md` (English): "Where to find what" entry section, the module cut with the two abstractions, the data model, the two transition tables, the worker loop, leader lock and retry rule, the never-twice send mechanics (claim-before-send), the transcript provider chain and its legal notes, the e-mail frame, the log naming scheme, and a **Decisions** section (one short entry each: modular monolith; transcript providers and why no Whisper in the MVP; status-driven worker loop instead of a queue; poll-only trigger; *added 2026-09-27:* Amazon SES over SMTP — Listmonk rejected; Anthropic's API directly — gateway removed; web and worker in one container in production; the design reviewed as HTML drafts). No separate ADR folder — one place.
- **Log events**: the constants in `app/log.py`.
- `README.md` (German): what the platform does in five sentences, folder map, local start in five commands (with Mailpit), the CLI, link to this plan and to `docs/ARCHITECTURE.md`, how to run tests and lint.
- `docs/runbooks/operations.md` (*created in M6a*): one-time setup, deploy and rollback, DNS/e-mail, the AWS/SES setup and production-access text, unblocking a fan, uncertain deliveries and "did the mail arrive?", backups and the restore drill, monitoring accounts and who gets their mails, quotas, cost review, deletions (creator, fan), incident cheatsheet (mailing stuck in `sending`, rows in `failed`, OAuth re-consent, IP blocked).
- `docs/runbooks/onboarding.md` (M7): the exact steps to onboard a creator (contract, `cli onboard`, branding, creator login + YouTube connect, `backfill`, first preview) — manifest §3.1 "Wie der Creator das erlebt".
- *Added 2026-09-27:* the design review log — which draft was shown when, the owner's comments, what changed, the approval date — as a table in `implementation-notes.html` (milestone D). After approval, the templates, `style.css` and `app/design.py` *are* the design; there is no separate design file to drift from.
- *Added 2026-09-27:* `video/README.md` (German): how the product video is previewed, rendered and re-cut; `video/LICENSES.md`: the music track and the Remotion licence (milestone M10).
- Docstrings (numpy style) on every public function and Protocol.

## 17. Implementation steps (milestones)

Each milestone is deployable, has a test that proves it, and is small enough for one or two working sessions (manifest §10 "kleine Schritte"). Tick the boxes as work completes. Effort is in focused sessions (≈ half a day each), a guide, not a promise (manifest: no calendar).

**Marking.** `[x]` is built *and* covered by a passing test. `[ ]` is not started.
A **Status** line under each milestone records when it was finished and what could
not be verified — a "Done when" that needs a real API key or a real channel stays
open until it has been run against one, however green the tests are.

**Definition of done for every milestone** (*added 2026-09-27* — the owner's standard for a maintainable repository). A milestone is not done until:
1. its tests, including the mutation probes it names, pass; `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` are clean;
2. every grep gate of the plans prints nothing, and (from M6b on) the vendor-boundaries test passes (§3.1);
3. its whole diff was reviewed for dead code, duplication and simplification — nothing commented out, nothing kept "in case";
4. `docs/ARCHITECTURE.md`, `README.md`, `docs/runbooks/operations.md`, `.env.example` and `config/settings.toml` comments describe the new state — one authority per topic (§16), no second copy;
5. its **Status** line, the *Progress* line, the review section (§21), `implementation-notes.html` (deviations, owner questions) and `docs/backlog.md` (anything deferred) are updated; where the build deviates from the manifest, the manifest is updated too;
6. (from M6c on) the operator can see what the milestone added: new failure modes have their row in the operations plan's table and an incident where a person must act; new periodic work appears in the console's schedule.

**History in the boxes of built milestones.** M0–M6 describe what was built at the time, with the names of that time (`ResendClient`, `BifrostGateway`, `/webhooks/resend`, idempotency keys). They stay as a record; M6a and M6b replace those parts, and §4–§16 describe the platform as it will be.

### M0 — Foundation (≈ 3 sessions)
- [x] `uv init`, `pyproject.toml` with pinned dependencies and ruff/pytest config, `.python-version`, `.gitignore` additions (`.env`, `logs/`, `out/`).
- [x] `config/settings.toml` + `app/config.py` (`Settings`, derived values, validation, `get_settings`). Test: TOML loads, env overrides, invalid delay fails at start-up, a configured model without a price entry fails at start-up.
- [x] `app/log.py` (structlog, JSON/console by setting, optional file, stdlib routing, event constants). Test: a log call renders the bound context.
- [x] `app/db/engine.py`, `app/db/models.py` (all tables and enums from §7), Alembic env, first migration. Test: `alembic upgrade head` on an empty DB, `downgrade base` works.
- [x] `app/jinja.py`, `app/services.py` (with `set_services`), `app/worker.py` loop skeleton (runs nothing yet), `app/web/server.py` with `/health`.
- [x] `Dockerfile`, `docker-compose.yml` (postgres, bifrost, web, worker), `.env.example`, `render.yaml`, GitHub Actions CI.
- [x] `README.md` (German) updated, `docs/ARCHITECTURE.md` skeleton with the Decisions section.
- [ ] **External setup started now because of lead times:** Google Cloud project, YouTube Data API key, OAuth client (web), consent screen with `youtube.force-ssl`; domain decision; Resend account + sending subdomain (*Changed 2026-09-27:* replaced by an AWS account and an SES domain identity — SES plan §9); Render account; Webshare residential proxy account.
- **Done when:** `docker compose up` serves `/health`, CI is green with the tests above.
- **Status: done, 2026-09-11.** `docker compose up` serves `/health` with a real `SELECT 1`; `alembic upgrade head` and `downgrade base` both verified against PostgreSQL 17. The external-setup box stays open: the LLM-provider and Resend accounts exist, the Google Cloud project, the YouTube API key, the domain, the Render account and the Webshare proxy do not. CI is green: the first run after the push finished in 37 s — `uv sync --locked`, both ruff checks and the full suite against a PostgreSQL service container.

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
- [x] `/k/{slug}` POST with slowapi and HTMX inline response; confirm route + page; unsubscribe GET/POST incl. one-click; confirm/welcome template.
- [x] `/webhooks/resend` (signature, bounce/complaint → block).
- [x] `cleanup` periodic job (pending and unsubscribed retention; the video re-check parts come in M6).
- [x] Tests: DOI flow end to end with `TestClient`; no enumeration (same response for new/existing); already-confirmed re-signup resends confirm; rate limit returns 429; unsubscribe affects only that subscription; webhook vectors verify, replay is a no-op, bounce blocks.
- **Done when:** the owner signs up on the pilot page, confirms, and is blocked after a test bounce (`bounced@resend.dev`). *Changed 2026-09-27:* with SES the test bounce is `bounce@simulator.amazonses.com`, run in M9.
- [x] Review follow-up (2026-09-18): a code review of the finished milestone found 15 verified defects, among them a forgeable webhook when the secret is empty, Sentry shipping secrets and fans' addresses, and commits after the response. All fixed test-first; the plan passages they changed are marked "*Changed 2026-09-18*" and summarised at the top of this plan.
- **Status: built, reviewed and hardened; acceptance open, 2026-09-18.** 482 tests (127 more than before M5) cover every rule in §10 for the three routes, the webhook, the cleanup and the hardening in §13; the rules that guard privacy and reputation were each seen failing against a mutant (§14). Clicked through in Chrome and checked against the rebuilt container: HTMX swap, confirm, unsubscribe, a NUL path (404), a 100 KB body (413), an unsigned webhook (401), and the MX lookup against real DNS (`gmx.dee` and `example.com` rejected, `delivered@resend.dev` accepted). **Sending is verified live:** real confirm mails reached Resend's test address `delivered@resend.dev` (status *delivered*), sent after the response as designed, from `onboarding@resend.dev` via `SENDER_ADDRESS` (no verified domain before M9). **Not verified: the webhook.** No event has arrived from Resend yet — the development machine sits in a network that blocks the `cloudflared` tunnel, and a tunnel from that machine was ruled out, so the live bounce test moved to M9, where the app has a public address. Until then the payload handling rests on Resend's documented examples (`email.bounced`, `email.complained`, `email.suppressed`), not on a real event.

### M6 — Scheduling and sending (≈ 3 sessions)
- [x] `delivery/mailing.py`'s remaining lifecycle — stop/postpone, sentiment, preview, send; create/schedule shipped in M3, `schedule.py` in M1 — plus `next_mailing_step()` and `postponed_send_at()`; steps `prepare_sentiment`, `send_preview` (the `summary` template's preview block with the action bar), `send` (advisory lock, snapshot, batches, resume), stop/postpone routes + confirmation pages, conditional transitions in `mailing.py`, cleanup re-check of every `analyzed` appearance (§9.3). *Changed 2026-09-18:* the reschedule on a changed delay moved to M7 (see there).
- [x] Tests: `compute_send_at`, `next_mailing_step`, `retry_at`, `postponed_send_at` cases incl. "worker down across T", the postpone cap and a premiere published long ago; state machine end to end with a stepped clock; exactly-once after a simulated crash mid-send, after a lost provider answer (same key, byte-identical batch) and under a held lock; stop and postpone committed from a second session mid-step; stop blocks; postpone shifts, caps, rotates the token and refreshes sentiment; sentiment step gives up gracefully (deadline, cost cap); cancelled when the video is no longer public; the send snapshot excludes pending, blocked, unsubscribed and other creators' subscriptions and one confirmed after the snapshot, leaving exactly one `deliveries` row and one recipient at the fake; a previewed mailing whose creator then changes variant and greeting still renders byte-identically from its `render_snapshot`; cleanup marks a private sent video unavailable and a deleted backfill video too; the result pages never say "Gestoppt" unless this request stopped the mail.
- **Done when:** with `min_delay_hours` and `default_delay_hours` set to 3 on a test config, a new upload arrives as a preview mail with a full stop window, then as the fan mail, without manual steps.
- [x] Review follow-up (2026-09-20): a code review of the finished milestone found 19 verified defects — a caught database error silently discarding a paid-for summary, a finished send that could end as `failed`, a long list giving up mid-way, blocked addresses still getting later batches, a mailing parked forever, notices that said the wrong thing, and two test-isolation leaks. All fixed test-first, nine of them pinned by mutation probes; the passages they changed are marked "*Changed 2026-09-20*".
- **Status: built, tested, accepted live, reviewed twice and closed, 2026-09-18/20.** 693 tests. Mutation probes against the rules that guard money, reputation and privacy — advisory lock, conditional transitions, each snapshot condition, payload freeze, token rotation, "never say gestoppt", the stop-window push, no failure notice for a stopped mailing — each killed by the intended test; one survivor, `ORDER BY id DESC`, is an equivalent mutant (any stable order keeps key and payload stable). The routes were exercised against the running container, and at 320 px and desktop width in Chrome (keyboard only: focus lands on the single button, Enter acts, results are announced).

  **Acceptance run, 2026-09-19, against the live services** (test channel, `min_delay_hours = default_delay_hours = 3`, every address a Resend test address): feed poll → real transcript (unofficial provider, 15,321 characters) → real summary (`claude-sonnet-4-5-20250929`, 3.2 ct) → mailing scheduled for T+3 h → sentiment from 17 real comments (1.1 ct) → preview to the creator at T−1 h, delivered, first sentence "Diese Mail geht am Sonntag, 20. September, um 00:18 Uhr an 2 Abonnenten" → batch send at T, `/emails/batch`, both fans delivered, one `deliveries` row each. Afterwards: one-click unsubscribe from the mail's own link works, the `/s/` page answers 200, the confirmation page now links the summary the list received, and swapping the worker process (local → container) sent nothing a second time. Three defects the fakes could not find were fixed on the way: the strict output schema, a model the gateway would not serve, and a rejected key ending videos in `failed`.

  **Still unverified:** how the mail renders in Apple Mail and Outlook, and the
  `List-Unsubscribe` header as it arrives at a real mailbox (set in code and
  unit-tested; the provider's API does not show headers). Both wait on a
  verified sending domain — without one the provider delivers only to the
  account's own address — and therefore on the deployment; the bounce webhook
  (M9) waits on the same thing. *Changed 2026-09-20:* Gmail judged good by the
  owner on the preview mail of 2026-09-19.

### M6a — Amazon SES replaces Resend (≈ 3 sessions) — *added 2026-09-27*
Specified, with its checkboxes, gate and "Done when", in [`2026-09-ses-migration-plan.md`](2026-09-ses-migration-plan.md) §12 — open that file, work through it, come back. Built first because M7a counts confirm mails at the moment the provider accepts them, and everything later would otherwise build on the client that is about to go.
- **In short:** `SmtpClient` (standard library) to SES; `OutgoingEmail` with `from_name`/`from_address`; per-recipient **claim before send** — never twice, a deploy stops cleanly between two mails, a hard crash leaves at most one uncertain recipient; `/webhooks/ses` with SNS signature checks feeding the unchanged block rule and logging the delivery status of every mail; Mailpit catches every local mail; `docs/runbooks/operations.md` created; **every trace of Resend removed and a grep gate that proves it**. The live SES checks need the domain and a public address and happen in M9.
- **Status: planned, not started, 2026-09-27.**

### M6b — Lean platform: no gateway, one service, backups (≈ 3 sessions) — *added 2026-09-27*
Specified in [`2026-09-lean-platform-plan.md`](2026-09-lean-platform-plan.md) §8.
- **In short:** `AnthropicGateway` replaces the Bifrost gateway (structured outputs, usage mapping, error mapping); web and worker in one container (`ops/start.sh`) with a worker leader lock (`app/db/locks.py`); the daily encrypted backup to B2 from the worker; the worker heartbeat; `render.yaml` in its ≈ €11.50 shape (§15.2); the manifest updated with every decision of 2026-09-10, -21 and -27; **every trace of the gateway removed and a grep gate that proves it**; memory measured under 512 MB.
- **Status: planned, not started, 2026-09-27.**

### M6c — Operations: failure handling, operator console, safe deploys (≈ 4 sessions) — *added 2026-09-27*
Specified in [`2026-09-operations-plan.md`](2026-09-operations-plan.md) §9.
- **In short:** a behaviour for every kind of failure (§2 there) with a test or drill each; alert channels that do not depend on the platform; component state and a durable incident list in the database; the operator console `/betrieb` (health, what is running, the version, a seven-day schedule of summaries, previews and sends with recipient counts and durations, incidents, the quiet window) behind a password only the owner holds; the daily operator mail at 07:00; one mail when a person must act; an emergency stop for all sends; Render deploying only after CI; `cli status` — all from one status module.
- **Status: planned, not started, 2026-09-27.**

### D — The design, drafted in HTML and approved by the owner (≈ 4 sessions + the owner's review time) — *added 2026-09-27*
**Goal.** Every surface a visitor, a fan or a creator sees is designed and approved *before* the milestones that follow build on it. Owner's direction (2026-09-27): modern, minimal, clear, interesting, **warm colours — cream, cappuccino, mocha**; the owner shows references at the kick-off and whenever he has them. **Tool: none beyond the code** (owner decision 2026-09-27, no paid design tool): the drafts *are* the real templates, `style.css` and `app/design.py`, rendered with fictional demo data and shown in the browser. What is approved is exactly what ships — there is no design file that could drift from the code.

**How a draft is made and shown.**
- A new module `app/design_preview.py` renders every page and mail with fictional demo data defined in the module itself (the image does not contain `tests/`) — a demo creator "Beispielkanal" with a light, a mid and a dark example accent, a demo video, a `Summary` and a `Sentiment` validated against their Pydantic models — and `uv run app design-preview` writes them as static files to `out/design/` (git-ignored) with an index page listing every screen and state. The same function backs a test that renders every entry (no template can break unnoticed) and, later, the video's screens (M10).
- Each round is a branch (`design/foundations`, `design/key-screens`, `design/all-screens`); nothing merges into `master` before the owner's approval.
- For each round the implementer delivers **screenshots of every screen at 390 px and 1440 px, in light and dark mode**, taken from `out/design/` in a browser; the owner can also open `out/design/index.html` himself (DevTools' responsive mode for phone width).
- **Feedback and approval** are recorded in a review table in `implementation-notes.html` (round, screen, owner's comment, what changed, status); approval is the owner's explicit OK with its date in that table. A change after approval is a new round on the affected screens.

**Scope — every visible surface** (✓ = in round 2, the rest in round 3):

| Area | Screens and states |
|---|---|
| Website (A) | landing page ✓ (the seven sections of manifest §5.5, the tier table with the five-line rules block, a video slot for M10); `/kontakt` (form, sent, rate-limited); Impressum/Datenschutz (`legal.html`); error pages 404, 410, 429, 500 |
| Fan pages (B), creator's branding on the platform's warm base | sign-up ✓ (empty, address error, "Schau in dein Postfach", "try tomorrow" from M7a); confirmed ("Dabei!" with and without the summary link); expired link; unsubscribe (confirm, done); summary page `/s/` ✓ (full text, with and without sentiment, 410) — each with the three example accents |
| Creator area (C) | login (form, "check your inbox"); the one-button login page; stop/postpone confirmation and result pages. *The settings page (M7) and the billing page (M7b) are drafted in their milestones in the approved style and approved the same way.* |
| Mails | fan mail ✓ (compact; then detailed and teaser, each with and without sentiment); creator preview with its action bar; confirm mail; magic-link mail; creator notice — 600 px wide, light and dark |
| Operator console (M6c) | the three `/betrieb` pages and the daily operator mail — plain, dense, readable on a phone |
| Brand | product wordmark in text (the final name waits for the domain decision, §20 q1), favicon, social preview image |

**Rounds.** 1. **Foundations:** palette (light and dark), type scale, spacing scale, radii, and a components page in the preview (button, link, input with error, radio card, card, banner, tier table, sentiment box, summary block, footer, mail frame). 2. **Key screens** (✓ above). 3. **All remaining screens.** The owner approves each round before the next starts.

**Constraints every round must meet** (checked by tests where marked):
- **One font family and one accent colour** (manifest §5.5): the warm neutrals — cream background, foam-white surfaces, cappuccino rules and quiet fills, mocha/espresso text — are not accents; the single platform accent is proposed as a caramel tone; on fan pages the creator's accent replaces it. Dark mode is warm espresso, not grey. The font is licensed for self-hosting (SIL OFL), served from `static/fonts/` as at most two woff2 files (a variable font or regular + bold), never from a third-party host (a German court fined remote Google Fonts under the GDPR in 2022). Mails use the system font stack (§11).
- **Tokens live in `app/design.py`** under role names: the existing roles (`fg`, `muted`, `bg`, `canvas`, `card`, `rule`, `quiet`, `highlight`, `bright`, `dark_ink`, the type keys, `DEFAULT_ACCENT`) keep their names. **No new `accent` role:** the page already sets `--accent` per page (`pages/base.html`), and `DEFAULT_ACCENT` becomes the approved caramel — one value, one place. `TYPE['family']` becomes the self-hosted page font; a new `mail_family` holds the system stack for mails. New roles for spacing (`space-1…n`) and for border and outline widths (the 2 px and 3 px borders and the 3 px focus ring in `style.css` today) are added in round 1 and listed in the review log. No colour, font size, radius, spacing or width literal in a template or `style.css` — the existing colour test is extended accordingly (literal `rem`/`px` forbidden except `0` and `1px` hairlines). ✔ test
- **`app/branding.py` reads its backgrounds and inks from `design.py`** (`bg`, `card`, `bright`, `dark_ink`), no second copy. With a cream page and a lighter card, page and card differ: the creator-accent helpers in `app/jinja.py` (`link_on_light`, `surface_on_light`, …) check against the **stricter** of `LIGHT['bg']` and `LIGHT['card']` (and likewise in dark). Every text/background pair of `LIGHT` and `DARK` clears 4.5:1 (large text 3:1). ✔ test, mutation-probed
- WCAG 2.2 AA: contrast (above), visible focus states, labels, keyboard use; body text ≥ 16 px; hierarchy by colour and weight (§11).
- **No third-party host** in any template or stylesheet (fonts, scripts, images). ✔ test, mutation-probed
- Fictional demo content only: no real creator's name or data, no stock photos of people, no YouTube logo (trademark) — YouTube is named in words.
- Mails keep the fixed frame of §11 (the two fingerprints), declare `color-scheme: light dark` and keep one dark-mode block through `css_inline`.

- [ ] Kick-off: the owner's references and must-haves recorded in the review log; the German landing-page copy drafted (the owner approves wording separately from layout).
- [ ] `app/design_preview.py` + `uv run app design-preview` + the render-everything test.
- [ ] Round 1 approved (foundations, tokens in `design.py`, the new role names recorded).
- [ ] Round 2 approved (key screens).
- [ ] Round 3 approved (all remaining screens, favicon, social image).
- [ ] Tests: contrast of every pair; no literal colours, sizes or spacing outside `design.py`; no third-party host; every preview entry renders.
- [ ] Merged into `master`; `README.md` (how to run the preview) and ARCHITECTURE (the design rules) updated.
- **Done when:** the owner has approved every screen of the scope at 390 px and 1440 px in light and dark (dates in the review log); the approved drafts are on `master`; the tests above are green; Lighthouse (mobile) accessibility ≥ 90 on the landing and sign-up page, run locally.
- **Status: planned, not started, 2026-09-27.**

### M7 — Creator settings and operations (≈ 2 sessions)
- [ ] *Changed 2026-09-18 (M6):* the reschedule on a changed delay (§9.2), moved here from M6 so it is built with its caller. `mailing.postpone` already holds the rule "a new schedule is a new token, status back to `scheduled`, snapshot cleared".
- [ ] Settings page (form, validation against min/max and variants, reschedule on delay change, OAuth status + connect button, sign-up link, list size), CSV export, logout — *Changed 2026-09-27:* drafted in the approved design (D), shown to the owner as screenshots at 390/1440 px, light and dark, and approved before the milestone closes.
- [ ] `docs/runbooks/onboarding.md`; `operations.md` extended with the deletion statements (creator after the contractual grace period). *Changed 2026-09-27:* a fan's erasure request becomes a command, not SQL: `uv run app erase-fan <address>` deletes the subscriber (cascading to subscriptions and deliveries), writes the SHA-256 of the canonical address to `erasures` and logs `subscriber.erased` with the hash only; `uv run app reapply-erasures` deletes every subscriber whose address hash is in `erasures` — the step every restore runs before anything is sent (lean-platform plan §5). A complaint-blocked address is erased too when the fan asks; the SES suppression list keeps protecting the reputation. (*The unblock procedure moved to M6a.*)
- [ ] *Added 2026-09-27 (owner decision on §20 question 4):* the fan mail's "Online ansehen" link carries `?von=mail`; the summary page opened with it fires one small same-origin POST after it has loaded (`hx-post="/s/{view_token}/gelesen" hx-trigger="load"`, HTMX is already on every page), and only that POST increments one integer column per appearance (`appearances.mail_views`, no personal data, no cookie, no IP). The GET alone never counts: mail link scanners (Gmail, Outlook/Defender — §10) fetch links but, in the common case, run no scripts. The figure is still an **estimate and an upper bound** — a reload counts again, and a scanner that runs scripts would count too — and the console and the daily mail label it so. It is the platform's own engagement figure instead of an open rate; the status module (M6c) shows it in `cli status`, the console and the daily mail.
- [ ] Tests: settings validation; saving a changed delay reschedules and rotates the stop token, saving a greeting does not; a variant switch changes the rendered mail of an open mailing without a new analysis; CSV content; `erase-fan` leaves no row with the address and records only its hash, `reapply-erasures` removes a restored subscriber again; a GET of `/s/{token}?von=mail` alone does not increment the counter, the page's POST does, a page opened without `?von=mail` does not fire it; the POST route is rate-limited and answers 204.
- **Done when:** the pilot creator changes his delay and greeting himself and downloads his list.
- **Status: planned, not started.**

### M7a and M7b — Usage, pricing, billing (≈ 2 + 4 sessions) — *added 2026-09-21*
Specified, with their checkboxes and "Done when", in [`2026-09-billing-plan.md`](2026-09-billing-plan.md) §9 — open that file when you get here, work through its §9 from top to bottom, and come back. The boxes are ticked there; the status line below and the *Progress* line at the top of this plan are updated when one closes.
- **M7a — usage ledger, early warnings, operator cost view.** The ledger counts failed LLM calls; YouTube quota and confirm mails are counted in the database with a log warning before the limit; a daily cap and a honeypot protect the sign-up form; `cli costs` shows what each creator costs. No Stripe involved.
- **M7b — pricing, invoices, pause.** Tier table in `settings.toml`, months frozen when they end, one Stripe invoice after six months or at €100, a daily status poll instead of a webhook, automatic pause and resume, the creator's billing page with the rules in five lines — *Changed 2026-09-27:* the billing page and the paused banner drafted in the approved design and approved by the owner like M7's settings page. Needs M7 and M7a; developed against a fake and a Stripe sandbox.
- **Status: planned, not started, 2026-09-21.**

### M8 — Landing page, legal pages, contact; ready for real inboxes (≈ 3 sessions) — *Changed 2026-09-27*
The design is already in place (D); M8 completes the content and proves the pages and mails outside the test suite.
- [ ] `landing.html` complete with the seven sections of manifest §5.5 as approved in D; `config/roadmap.toml` + renderer; price tiers rendered from `[pricing]` (the same table billing reads) with one worked example "19,000 subscribers, weekly video → tier S to M" marked as a forecast, and the five-line rules block `partials/billing_rules.html` (billing plan §7); FAQ; the video slot (filled in M10).
- [ ] The example mail: a real `cli demo-mails` snapshot of a pilot video, with the pilot's written consent (§20 q10); until then the fictional one, marked "Beispiel".
- [ ] `/kontakt` with `templates/email/contact.txt`, relayed to `support_email` after the response; it is the third mail sent after an HTTP answer, so the "send or undo" logic of the confirm and magic-link mails becomes **one** helper now (backlog trigger).
- [ ] Impressum and Datenschutz with the owner's text — it must name the YouTube API Services with Google's privacy policy and every processor of §15.2.
- [ ] Favicon and social preview image as approved in D.
- [ ] **Real inboxes** (needs the domain and SES sandbox steps 1, 3 and 7 with the owner's address verified — SES plan §9): every mail of D's scope arrives in Gmail (web and app), Apple Mail and Outlook; dark mode checked in Apple Mail and Outlook, Gmail's own inversion checked for legibility.
- [ ] Tests: landing renders roadmap items by status and the tiers from the settings; the contact form is rate-limited and relayed via the fake; the one send-or-undo helper serves all three mails.
- **Done when:** the owner approves the finished landing page on phone and desktop; Lighthouse (mobile) performance ≥ 90 and accessibility ≥ 90; the landing page transfers ≤ 300 KB excluding the video (`preload="none"`); the real-inbox checks above pass.
- **Status: planned, not started.**

### M9 — Go-live (≈ 3 sessions) — *Changed 2026-09-27: regrouped by what each step waits for*
**Before, as soon as the domain is decided** (§20 q1; none of this waits for M8):
- [ ] AWS account and SES setup steps 1–5, 7, 8 and 11 (SES plan §9); the owner's address verified for sandbox tests.
- [ ] Anthropic: a production workspace with a spend limit and its own key (lean-platform plan §2).
- [ ] Backblaze B2 (EU region), private bucket with the lifecycle rule "keep hidden files 30 days", an application key restricted to the bucket without `deleteFiles`, `restic init` over the S3 API; password and key in the owner's password manager (lean-platform plan §5).
- [ ] Monitoring accounts: UptimeRobot, Healthchecks.io (heartbeat and backup checks), Sentry EU project.
- [ ] A mailbox for the domain (MX), so `support_email` receives; until then `SUPPORT_EMAIL` points at an existing address (§20 q8).

**Deploy:**
- [ ] The "verify before M9" points of §15.2 (Hobby terms, `maxShutdownDelaySeconds`, `autoDeployTrigger: checksPass`).
- [ ] Render Blueprint applied in its §15.2 shape, every secret set; domain DNS; DMARC published; `/health` answers over HTTPS.
- [ ] `FORWARDED_ALLOW_IPS` set to Render's proxy addresses instead of `*` (`implementation-notes.html` question 9).
- [ ] First backup visible in B2, its Healthchecks.io check green; **restore drill** into a scratch database with matching row counts, dated in `operations.md`.
- [ ] Heartbeat check green; UptimeRobot green; Render's failed-deploy e-mail on; a test error reaches Sentry.
- [ ] Operator console reachable with the password (and refused without); a seeded `NeedsOperator` produces an incident and an operator mail; the daily mail arrives at 07:00; a push with a failing test is not deployed (`checksPass`); the emergency stop set and cleared once; the quarterly drill of the alert channels done for the first time (operations plan §3).

**After the site is live:**
- [ ] SES production access requested (SES plan §9 step 9); quota and send rate recorded, `EMAIL__MAX_SEND_RATE_PER_SECOND` and `EMAIL__DAILY_QUOTA` set (step 10); DMARC `rua` added once the domain's mailbox exists (SES plan §9 step 5). Until approval only verified addresses receive mail — the pilot's first real mailing waits for it.
- [ ] SNS subscription `https://<domain>/webhooks/ses` created and confirmed from its logged `SubscribeURL`; e-mail feedback forwarding off (SES plan §9 step 6).
- [ ] M5's and M6a's live acceptance: sign-ups of `bounce@simulator.amazonses.com` and `complaint@simulator.amazonses.com` end blocked as `bounce` and `complaint`; a real mail to the owner's Gmail shows `spf=pass` (for `bounce.mail.<domain>`), `dkim=pass` and `dmarc=pass`, its DKIM `h=` list contains `list-unsubscribe` and `list-unsubscribe-post`, Gmail's own unsubscribe button unsubscribes, and the delivery appears as `email.delivered` in the log.
- [ ] Google OAuth verification submitted (homepage and privacy policy are live now); until approved the pilot re-consents weekly or the unofficial provider carries production.
- [ ] Pilot onboarding via the runbook: contract signed, `cli onboard`, branding, login + YouTube connect, `backfill`, first real preview reviewed together.

**Before the first invoice** (*added 2026-09-21*; none of it blocks development):
- [ ] Business registered and tax number issued (small-business rule chosen); Stripe account activated (needs the live website); in the Stripe dashboard: tax number as default account tax id, sequential numbering with a prefix, "e-mail finalized invoices" on, reminders for one-off invoices aligned with `pause_after_days_overdue`, payment methods SEPA debit and card; restricted live key set as `STRIPE_API_KEY` on Render. Live check of what a sandbox cannot show: one real €1 invoice to the owner's own address — the mail arrives, the PDF carries number, tax number and the §19 sentence, a reminder arrives, payment flips our row to `paid`.
- [ ] The contract names the tier table, billing in arrears, the €100 rule and the pause.
- [ ] `docs/runbooks/operations.md` complete; README final; ARCHITECTURE.md Decisions final; the Resend and gateway gates still print nothing.
- **Done when — Phase 1 live:** the first real mailing has gone out to the pilot's list, nobody twice and no delivery uncertain, and the acceptance criteria in §2 are all ticked.
- **Status: planned, not started.**

### M10 — Product video (≈ 4 sessions) — *added 2026-09-27; the last step*
**Goal.** A short, high-quality animated video that presents the platform and its features clearly and attractively — for the landing page, for sales conversations with creators and for social media. Made after go-live because it shows the real product in its approved design, under its final name and domain (§20 q1).

**Deliverables.**
- Master: 16:9, 1920×1080, 30 fps, H.264 + AAC in MP4, 60–90 s.
- Vertical cut: 9:16, 1080×1920, for Shorts, Reels and TikTok — the same scenes re-laid out for a narrow frame, not a crop.
- Web version of the master: ≤ 10 MB, plus a poster frame (WebP); both in `src/app/static/video/`. The masters (≈ 100–300 MB) are not committed — they go to the owner's storage (§20 q11).
- No voice (owner decision 2026-09-27): German on-screen text and music; the video works muted, because most feeds start muted.

**Style.** The approved design of D: the same colour tokens, the same self-hosted font, the same components; real screens of the platform rendered by `uv run app design-preview` from its fictional demo data (never a real creator or fan), animated with calm, precise motion: short eases and springs without overshoot for interface elements (≈ 250–600 ms), kinetic typography for the key sentences, masked reveals and gentle parallax between layers, one idea per scene, every line of text on screen long enough to read twice (≥ 1.5 s, at most about six words per line). Nothing flashy; the brand is sober (manifest §3.1). No YouTube logo (trademark).

**Storyboard draft** (German texts are drafts for the owner; timings are targets; `{…}` is filled from the settings):

| # | Seconds | Scene | On-screen text (draft) |
|---|---|---|---|
| 1 | 0–5 | A video goes online; a feed scrolls past it | „Dein Video ist online. Und dann entscheidet der Algorithmus.“ |
| 2 | 5–12 | Product name and promise | „{Produkt}: Jedes neue Video kommt als kurze Mail zu deinen Fans.“ |
| 3 | 12–22 | The creator's branded sign-up page; an address is typed; the confirm mail arrives | „Fans tragen sich ein. Double-Opt-in, fertig.“ |
| 4 | 22–35 | Video timeline → transcript lines flow → headline, core message, key points with timestamps, the quote | „Aus dem Video wird eine Zusammenfassung — mit Sprungmarken.“ |
| 5 | 35–45 | Comments stream in and condense into the sentiment box | „Dazu: Was deine Community sagt.“ |
| 6 | 45–55 | The creator's preview; a countdown to the send; the Stoppen / Verschieben buttons | „Du siehst jede Mail vorher — und kannst sie stoppen.“ |
| 7 | 55–65 | A phone: the mail arrives, opens, a jump link lands at 12:34 in the video | „Deine Fans lesen in einer Minute, was du gesagt hast.“ |
| 8 | 65–75 | Settings, CSV export, the tier table | „Deine Liste gehört dir. Faire Preise ab {Einstiegspreis} im Monat.“ |
| 9 | 75–83 | The "automatisch erstellt" notice, one-click unsubscribe | „Transparent. Abmelden mit einem Klick.“ |
| 10 | 83–90 | Wordmark, domain, call to action | „{Domain} — Gespräch vereinbaren“ |

**How it is made.** Remotion (React-based video rendered from code in headless Chrome, FFmpeg bundled). Its licence is free for individuals and companies with up to three employees — the owner's business qualifies; beyond that a company licence (≈ $25 per seat and month) is needed (backlog trigger) — recorded in `video/LICENSES.md`.
- `video/` holds its own `package.json` and lockfile (the current Node LTS — verify at the start; Node 24 is the active LTS in autumn 2026). `.gitignore` gains `video/node_modules/`, `video/out/` and `video/src/data.json`. The Dockerfile copies nothing from `video/`, and CI does not build it.
- A new CLI command `uv run app design-tokens` prints, as JSON on stdout, the colour and type tokens of `design.py` (light and dark), the product name, the domain and the entry tier price from `[pricing]` — one small function, unit-tested. `video/package.json`'s `prebuild` and `prestudio` scripts run `uv run --project .. app design-tokens > src/data.json`, so the video cannot drift from the site or show an outdated price.
- The fonts are loaded from `../src/app/static/fonts/`; the screens are PNG/HTML captures of `out/design/` (from `design-preview`) copied into `video/public/`.
- `src/storyboard.ts` holds every scene's text and duration — the one place the script lives; one component per scene under `src/scenes/`; two compositions (`Promo` 1920×1080, `PromoVertical` 1080×1920). Preview in Remotion Studio; render with `npx remotion render` (H.264; CRF ≈ 18 for the master, higher for the web version) and `npx remotion still` for the poster.

**Music.** A licence-free track from Pixabay Music (commercial use without attribution is allowed; some tracks are registered with YouTube Content ID — check the track for claims before any YouTube upload). Track, URL, licence and download date go into `video/LICENSES.md`. Mixed low, with a fade-out; cuts follow its beat.

**Process.** Storyboard and German texts approved by the owner → animatic (rough timing with placeholder frames) approved → full animation → review rounds on phone and desktop → final render of both formats.

**On the landing page.** Self-hosted `<video controls playsinline preload="none" poster="…">` in the slot D designed — no YouTube embed, which would set third-party cookies before consent. Below the player, the storyboard's text as a short transcript (WCAG 1.2.1: a text alternative for a video without speech). Plays in Safari on iOS (it needs HTTP range requests — checked on the deployed site).

- [ ] Storyboard and texts approved.
- [ ] `app design-tokens` + test; `video/` set up (Remotion, data from `design-tokens`, fonts, screens from `design-preview`); `.gitignore`.
- [ ] Animatic approved.
- [ ] Both formats rendered; `video/LICENSES.md`; `video/README.md`.
- [ ] Web version, poster and transcript on the landing page; M8's performance bar still holds; plays in Safari iOS.
- **Done when:** the owner approves the final cut of both formats on phone and desktop, and the landing page plays the web version.
- **Status: planned, not started.**

Order of work is M0 → M4 (Phase 0 demo), then M5 → M6 (automation), then *(re-planned 2026-09-27)* **M6a → M6b → M6c** (mail provider, lean platform, operations), **D** (the design, approved by the owner), **M7 → M7a → M7b**, **M8**, **M9**, **M10** — strictly one after the other. The external steps listed under M9's first heading run in parallel as soon as the domain is decided.

**Post-go-live, not MVP** (tracked in `docs/backlog.md`): PubSubHubbub push (`sources/youtube/pubsub.py`, a verification/notification route, lease renewal, tombstone handling) — purely additive, build when a creator needs sub-hour detection; the verified hub facts stay in §18.

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

**Amazon SES** (*Changed 2026-09-27:* replaces the Resend facts of 2026-09-10, which described a provider that is no longer used)
- Checked 2026-09-27 against docs.aws.amazon.com and aws.amazon.com/ses/pricing; the full list, with what is unconfirmed, is §13 of `2026-09-ses-migration-plan.md`. The facts this plan leans on: à-la-carte $0.10 per 1,000 + $0.12 per GB, no fixed fee (new accounts start on the $0.16 Essentials plan — switch); sandbox until production access (verified recipients only, 200/day, 1/s); SMTP `email-smtp.eu-central-1.amazonaws.com:587`, region-bound credentials, `ses:SendRawEmail`; **no idempotency key, and SES may on rare occasions accept a mail although the request returned an error**; bounces/complaints via SNS, which signs with SHA1 unless the topic is set to `SignatureVersion 2`; account suppression list on by default; Gmail sends SES no complaint data; our own `List-Unsubscribe` headers pass through untouched.

**Anthropic Messages API** (*Changed 2026-09-27:* replaces the Bifrost facts of 2026-09-12/19 — the gateway is removed; its hard-won lessons are in git history and `implementation-notes.html`)
- Checked 2026-09-27 in Anthropic's API documentation; details in `2026-09-lean-platform-plan.md` §9. Structured outputs are generally available: `output_config.format = {"type": "json_schema", "schema": …}` on `POST /v1/messages`, no beta header (the old `output_format` is deprecated). Supported models include `claude-sonnet-5`. Unsupported schema features: recursion, external `$ref`, `minimum`/`maximum`/`multipleOf`, `minLength`/`maxLength`, `minItems` other than 0/1; `additionalProperties: false` required. The OpenAI-compatible endpoint ignores `response_format` and is not an option. An API key must belong to a workspace.

**Render**
- Blueprint keys `services`/`databases`; plan ids renamed Aug 2026 (`0.5c-512mb` $7, `0.1c-256mb` Postgres $6, prices re-verified live 2026-09-10); workers/crons have no free tier; free Postgres expires after 30 days; `runtime: docker` with `dockerfilePath`/`dockerCommand`; `preDeployCommand` (paid plans only) runs before deploy for Docker and native runtimes; zero-downtime deploys (old and new instance overlap briefly; the old one gets SIGTERM, then SIGKILL after the shutdown delay); `fromDatabase.connectionString` is the internal `postgresql://` URL; `healthCheckPath` (otherwise only a TCP probe); `autoDeployTrigger: commit`; Postgres default major is 18, set explicitly; `sync: false` vars are ignored on later Blueprint updates; Blueprint sync never deletes resources. *Added 2026-09-27:* workspace plans since 2026-04-23: Hobby $0 + compute (one member, 25 services), Pro $25; Frankfurt is a region; on Hobby point-in-time recovery covers 3 days and logical backups are kept 7 days, both inside Render (hence the off-site copy, §15.2); free web services spin down after 15 minutes idle and free Postgres expires after 30 days — both unusable here; running two processes in one service through a start script is not forbidden; the docs name no commercial-use restriction for Hobby (terms still to be read, §15.2).

**Alternatives to Render** (*added 2026-09-27*, prices from the providers' pages; comparison in §15.2)
- Hetzner Cloud: price rises on 2026-04-01 and 2026-06-15 (CX23 now €5.49 + €0.50 IPv4); status notice of 2026-06-26, still open: creation of new servers restricted for new and some existing customers. No managed PostgreSQL.
- netcup VPS 500 G12.5 (from 2026-09-22): 2 vCore, 4 GB, 64 GB SSD, €6.94 on 12 months, €8.64 month to month, IPv4 included. OVH VPS-1 ≈ €3.81 net on 12 months with daily backup; Contabo cheap but documented overselling; IONOS/Strato ≈ €8–10 after the introductory months.
- Oracle Always Free: allowance halved in 2026 (2 OCPU / 12 GB for A1), idle instances reclaimed. Neon free: 100 CU-hours a month, scale-to-zero cannot be disabled. Railway Hobby $5 incl. $5 usage, Pro $20. Fly.io managed Postgres from $38. Coolify (eleven critical CVEs, January 2026) and Dokploy (CVE-2026-24840). Watchtower archived 2025-12-17.
- Backblaze B2: $6.95 per TB-month, first 10 GB free; region chosen per account. Healthchecks.io: 20 checks free. UptimeRobot: 50 monitors free, commercial use allowed per its help centre (2026).

**Design and video tools** (*added 2026-09-27*)
- Design tools were evaluated and not adopted (owner decision 2026-09-27: HTML drafts): Figma needs a paid Full seat to work beyond drafts (Starter: 3 design files, integrations heavily rate-limited); Penpot (open source, free cloud plan) would have worked but adds a second source of truth next to the templates.
- Remotion: free licence for individuals and companies with up to three employees, otherwise a company licence (≈ $25 per seat and month); renders locally with bundled FFmpeg and a headless Chrome it downloads itself; H.264, 9:16 compositions, 4K by scaling.
- Pixabay Music: commercial use without attribution; not for resale on its own; some tracks carry YouTube Content ID claims.

**PubSubHubbub (deferred, kept for later)**
- Hub `https://pubsubhubbub.appspot.com/subscribe`; topic `https://www.youtube.com/feeds/videos.xml?channel_id=…`; `hub.secret` → `X-Hub-Signature: sha1=<hex>` HMAC-SHA1 over the raw body; lease up to 10 days; notifications fire on upload and title/description edits, also for scheduled videos, at-least-once; deletions as `at:deleted-entry` tombstones (undocumented); callback must be public on an allowed port; the hub returned 503 "transient error" for hours on 2026-09-10 — subscribe must retry and only the verification GET confirms; renewals are verified again; no test-fire endpoint; unlisted-upload behaviour unverified; diagnostics page is public.

**Python libraries**
- pydantic-settings 2.15: `TomlConfigSettingsSource` has exactly the priority its tuple position gives it, `env_nested_delimiter="__"`. structlog 26.1: `merge_contextvars` first, bind in async middleware (anyio copies the context into the threadpool), configure before any logger is used. slowapi 0.1.10: endpoint must take `request: Request` (checked at import time); in-memory storage is per process. SQLAlchemy 2.0.52 + psycopg 3.3.5 (`postgresql+psycopg://`, `psycopg[binary]` is fine in a container), pin `sqlalchemy<2.1` (2.1 release candidates are on PyPI), sync `def` endpoints are the documented FastAPI pattern (FastAPI 0.141 / Starlette 1.6 — pin). Alembic 1.19 autogenerate does not detect renames and mishandles native Postgres enums — review every migration, use `VARCHAR` + `CHECK`. itsdangerous 2.2, cryptography 50 (Fernet/MultiFernet; expiry logic belongs in the DB). `premailer` unmaintained since 2021 → `css_inline` 0.21. uv: `uv init` creates no `.venv`/lock until the first `uv sync`; commit `uv.lock`, `uv sync --locked` in CI/Docker. procrastinate 3.9 was evaluated (works as documented) and not adopted, see §4.

## 19. Risks

| Risk | Why it is real | Mitigation in this plan |
|---|---|---|
| Unofficial transcripts blocked from Render's IPs | Documented by the library; cloud IPs are blocked | Webshare residential proxy configured from day one; temporary errors retry for ~24 h inside the 48 h minimum delay; official provider as soon as the OAuth grant exists; creator notice on permanent failure. |
| Official captions may not cover auto-generated tracks | Unconfirmed in docs, widely reported | Spike in M2; if true, the official path covers only uploaded captions and the pilot is asked to upload/auto-publish captions; the unofficial provider remains in the chain. |
| Google OAuth verification takes weeks; Testing tokens die after 7 days | Google policy | Verification needs the live homepage and privacy policy, so it is submitted in M9 right after the deploy (*Changed 2026-09-27*: M8 is no longer early); weekly re-consent by the creator until approved; the unofficial provider carries the gap. |
| `PoTokenRequired` / age-restricted videos have no transcript path in the MVP | Library limitation | Skip + creator notice; count occurrences in logs; revisit with Whisper in Phase 2. |
| E-mails land in spam | Kills the product silently (manifest §11) | Dedicated subdomain, SPF/DKIM/DMARC, no tracking, `List-Unsubscribe`, bounce/complaint handling, plain-text part, real reply-to. |
| Double sends after a crash or during a deploy overlap | "Never twice" is a manifest promise (§2) | *Changed 2026-09-27:* claim-before-send per recipient (`deliveries.attempted_at`, committed before SMTP) + snapshot at send start + unique `(mailing_id, subscription_id)` + the mailing's advisory lock + the worker's leader lock + a clean stop before the next claim on SIGTERM; at worst one uncertain recipient per interrupted run (SES plan §5); tested with a simulated crash, SIGTERM and a concurrent run. |
| Late pipeline shortens the stop window | Worker down across `T`, or a rescheduled `send_at` too close | `send_preview` pushes `send_at` to at least `now + stop_window`; `send` requires `preview_sent_at + stop_window` to have passed; unit-tested. |
| Mail scanners "click" action links | Corporate and Gmail link scanners prefetch GET | Stop, postpone, unsubscribe and magic-link login act on POST behind a confirmation page; one-click unsubscribe is POST by specification. |
| LLM cost runaway | Retries × long transcripts | Per-creator daily cap, cost ledger, single-call ceiling on transcript length, bounded retries. |
| Upload detected late | Poll every 6 h, feed shows 15 entries | 6 h ≪ 48 h minimum delay; `cli poll` for manual runs; push notifications are the documented post-go-live upgrade. |
| One LLM provider, called directly | *Changed 2026-09-27:* the gateway is removed | The `LLMGateway` Protocol stays: another provider is one more class; the daily cap and a workspace spend limit bound the cost; `NeedsOperator` names the key, workspace or model when the provider refuses. |
| Legal: sentiment summaries as "derived data" from API comments; storage limits | YouTube API policies III.E.4 | No raw comments stored; summaries only; recently mailed videos re-checked daily; question flagged for the lawyer (§20) before launch. |
| *Added 2026-09-21:* Billing, sign-up floods, unannounced limits, fixed costs | Money and reputation | Five risks with their mitigations in the billing plan §11. |
| *Added 2026-09-27:* SES production access refused or late; a fan missing one mailing after a crash; Gmail complaints invisible; account paused for reputation; a leaked SMTP credential | Mail is the product | Six risks with their mitigations in the SES plan §14; the fallback relay is a configuration change. |
| *Added 2026-09-27:* Design approval takes longer than planned | D needs the owner's review time, and M7 builds on it | Three short rounds with screenshots, the owner reviewing on his own schedule; the kick-off (references, landing-page copy) can happen while M6a–M6c are being built, so D starts with its material ready. |
| *Added 2026-09-27:* One hosting provider, US-owned; one container for web and worker | An outage or a price change at Render; a customer objecting to US processors; memory running out in the shared container | Encrypted off-site backup; the compose file keeps the move to a VPS a day's work (§15.2, backlog trigger); memory measured before M6b closes, reduction before upgrade (lean-platform plan §3, §10). |
| *Added 2026-09-27:* One instance, no redundancy | A crash, a restart or a deploy switch-over makes the site unreachable for seconds to a minute; real redundancy (two instances, a high-availability database) costs from ≈ €60 a month | Composure instead of redundancy: every step resumes from the database, the worker restarts itself, alerts come from outside (operations plan §2, §3, §8); backlog trigger: sign-ups lost to downtime become measurable. |
| Pilot churns | Manifest §11 | `cli status` shows open mailings and failures; a second channel is only configuration. |

## 20. Open questions

To be answered by the owner; the plan proceeds with the stated assumption until then.

1. **Domain and product name** (manifest §15): assumption `Klartext` / `klartext.tld` placeholders in `settings.toml`; the SES domain identity (*Changed 2026-09-27*, was the Resend subdomain), OAuth homepage and DMARC need the real domain before M9 — and the product video (M10) shows the final name and domain.
2. **Pilot channel id** and contact e-mail for `cli onboard`; whether the pilot will upload captions if the ASR spike is negative.
3. **FAQ text and Impressum/Datenschutz text** for the landing page (the legal pages must name the YouTube API Services, Google's privacy policy and every processor of §15.2). *Changed 2026-09-27:* the price tiers are decided (billing plan); whether they follow the lower mail cost is SES plan §15 question 3.
4. **Open tracking and the manifest §6.3 criterion** "open rates above newsletter average". *Changed 2026-09-27:* with SES there is no open rate without open tracking (a pixel via an Open event, a tracking subdomain, a privacy-notice sentence — and a small deliverability cost); no provider dashboard shows it otherwise. **Decided 2026-09-27 by the owner:** tracking stays off, and the criterion is replaced by one measured without personal data — visits to the summary page that come from the mail's "Online ansehen" link, counted per video without personal data (built in M7) — recorded in the manifest update (M6b).
5. **Legal check** (manifest §9): sentiment summaries derived from API comments versus YouTube API policy III.E.4.h; whether stored video titles/durations fall under the 30-day rule (the daily re-check of recently mailed videos is the assumed answer); processor vs joint controller for the fan list (affects the privacy text, not the code).
6. **Webshare proxy budget** (≈ $10–30/month) — needed as soon as unofficial transcripts run in the cloud.
7. **Postpone step**: 24 hours assumed; the manifest only says "verschieben".
8. **A mailbox for the domain.** The plan sends but never receives. `support_email` is the reply-to fallback (§8.4) and the sole recipient of the `/kontakt` relay (§10) — the landing page's only inbound sales channel (manifest §5.5). Needed before M9: a mailbox for the apex domain and its MX record, or inbound mail on a subdomain (*Changed 2026-09-27:* was "Resend inbound"; the simple answer is a mailbox at the domain's registrar). Until then set `SUPPORT_EMAIL` to an existing address; with no MX, every contact mail hard-bounces against the sending reputation §11 protects. Who reads it goes into `docs/runbooks/operations.md`.
9. **Unsubscribe during an in-flight send.** §9.2's recipient set is a snapshot taken at send start, so someone who unsubscribes while a mailing is sending still receives that one mail — seconds of exposure normally, hours if the send is retrying. Assumption: acceptable, and the alternative (re-filtering each batch) breaks the payload freeze §8.4 relies on. **Decided 2026-09-18 by the owner: the snapshot holds**; a test pins it.

*Added 2026-09-21:* the questions on pricing and billing — most decided, hosting cost and the business registration open — are in the billing plan §12.

*Added 2026-09-27:* the questions on mail — the AWS account, the DNS provider, and whether the tier prices follow the lower mail cost — are in the SES plan §15. **Question 1 (the domain) is now the one outside decision everything later waits for** (see "What waits on what" at the top). Two more for the owner:

10. **The example mail on the landing page.** Manifest §5.5 asks for a *real* example mail; the one in the repository is invented. Assumption: a `cli demo-mails` snapshot of a pilot video, used with the pilot's written consent (M8); until then the invented one, marked "Beispiel".
11. **Where the video masters live.** The web version sits in the repository (≤ 10 MB); the masters (≈ 100–300 MB) do not belong in git. Assumption: the owner's own cloud drive.


## 21. Review section

Filled in during implementation: what was built per milestone, deviations from this plan and why, test evidence, lessons for the next plan. Until now this has lived in each milestone's **Status** line (§17) and in `implementation-notes.html`; from M6a on, each milestone adds one line here when it closes — what was built, what deviated, the test count, the lesson.

- M0–M6: see the Status lines in §17 and `implementation-notes.html`.
- M6a: —
