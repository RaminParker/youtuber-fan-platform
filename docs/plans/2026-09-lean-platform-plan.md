# Lean Platform Plan — one service, no gateway, backups included (milestone M6b)

> **Status:** planned, not started · **Date:** 2026-09-27 · **Part of the MVP.** One step of the MVP plan (`2026-09-mvp-implementation-plan.md`, §17: milestone **M6b**, directly after M6a). Where the platform runs and why is decided in the MVP plan §15.2; this plan is *how the code and the deployment get there*. The conventions of the MVP plan apply unchanged — in particular §3 "a removal is complete".
>
> **Why it exists.** The owner's hosting target is about €10 a month (2026-09-27). The previous shape — separate web, worker and LLM-gateway services on Render — cost ≈ €24 before backups. Two owner decisions of 2026-09-27 bring it to ≈ €11.50: **the LLM gateway (Bifrost) is removed** and the app talks to Anthropic's API directly; **web and worker run in one Render service**.
>
> **Progress:** M6b `[ ]` — tick the boxes in §8.

## Table of contents

1. [What changes](#1-what-changes)
2. [The LLM gateway goes: Anthropic's Messages API, directly](#2-the-llm-gateway-goes-anthropics-messages-api-directly)
3. [Web and worker in one service](#3-web-and-worker-in-one-service)
4. [One worker at a time: the leader lock](#4-one-worker-at-a-time-the-leader-lock)
5. [Backups, from inside the worker](#5-backups-from-inside-the-worker)
6. [Worker heartbeat](#6-worker-heartbeat)
7. [The removal: every trace of Bifrost and the second service](#7-the-removal-every-trace-of-bifrost-and-the-second-service)
8. [Milestone M6b](#8-milestone-m6b)
9. [Verified facts](#9-verified-facts)
10. [Risks](#10-risks)

---

## 1. What changes

| Before (M0–M6) | After M6b |
|---|---|
| `BifrostGateway` → Bifrost container → Anthropic | `AnthropicGateway` → Anthropic Messages API (httpx); the `LLMGateway` Protocol — the manifest's abstraction — stays |
| Render: `web`, `worker`, `bifrost` (+ disk), Postgres | Render: **one** web service running both processes, Postgres |
| No off-site backup | Daily encrypted `pg_dump` from the worker to Backblaze B2 (free below 10 GB) |
| No signal when the worker hangs | Heartbeat ping after completed ticks (Healthchecks.io, free) |
| Local compose: postgres, bifrost, web, worker | postgres, mailpit (M6a), web, worker — no gateway |
| Monthly: ≈ $27.55 | ≈ $13.30 (≈ €11.50) |

Local development keeps web and worker as two compose services (reload, separate logs); only production combines them.

## 2. The LLM gateway goes: Anthropic's Messages API, directly

**Why it is possible now:** Anthropic's Messages API offers structured outputs as a generally available feature — `output_config.format` with a JSON schema, no beta header (checked 2026-09-27, §9). Its OpenAI-compatible endpoint is **not** an option: it ignores `response_format` and `strict` ("not considered a long-term or production-ready solution"), so repointing the current client there would silently lose schema enforcement.

**`AnthropicGateway`** (in `src/app/analysis/llm.py`, replacing `BifrostGateway`; same `complete_json` signature):

- `POST https://api.anthropic.com/v1/messages` with headers `x-api-key: <ANTHROPIC_API_KEY>`, `anthropic-version: 2023-06-01`, `content-type: application/json`. The base URL is a module constant (`API_URL`), not a setting.
- Body: `model`, `max_tokens`, `system` (top-level string), `messages: [{"role": "user", "content": user}]`, `output_config: {"format": {"type": "json_schema", "schema": schema.model_json_schema()}}`.
- Answer: the JSON is the text of the first `content` block of type `text`; `schema.model_validate_json(text)`. The existing schema retry stays exactly as it is (one retry, the model's own answer appended as an `assistant` message plus the validation error as a `user` message).
- `stop_reason == "max_tokens"` or `"refusal"` → `LLMError` naming the reason (the documentation promises valid JSON only for a normal end; a truncated answer is not trusted).
- **Usage** (keeps the ledger's rule that cached tokens are inside `tokens_in`): `tokens_in = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`, `tokens_cached = cache_read_input_tokens`, `tokens_cache_write = cache_creation_input_tokens`, `tokens_out = output_tokens`; missing fields count as 0. `model` = the `model` field of the answer (the dated snapshot), so `price_for_booking` keeps working.
- **Errors:** transport error, `429`, `529` (overloaded) and `5xx` → `LLMTemporaryError`; `401`, **`402` (`billing_error`)** and `403` → `NeedsOperator("Anthropic", <the API's message>, "check ANTHROPIC_API_KEY, the key's workspace and the account's credit")`; a `400` whose message names credit or billing (`_ACCOUNT_TROUBLE` keeps "credit balance", "billing", "workspace", "api key") → the same `NeedsOperator` — an empty account must never end every video in `failed` and write to every creator (the 2026-09-19 rule, pinned today by `test_no_credit_left_is_the_operators_too`); `404` or an error naming the model → `NeedsOperator(…, "switch to a model the API still serves in config/settings.toml [llm] and its price entry")`; `413` and any other `4xx` → `LLMError` (permanent, e.g. a schema the API does not accept).
- **Model names lose the gateway's provider prefix:** `model_summary = "claude-sonnet-5"`, `model_sentiment = "claude-sonnet-5"`; the price table keys likewise (`"claude-sonnet-5"`, `"claude-sonnet-4-5"` — kept for old ledger rows, with its comment). `price_of`'s handling of provider prefixes becomes dead and is removed; its snapshot matching (`claude-sonnet-4-5-20250929` → `claude-sonnet-4-5`) stays.
- **Schema compatibility:** the API rejects `minimum`/`maximum`, `minLength`/`maxLength`, `multipleOf`, recursion and `minItems` other than 0 or 1, and requires `additionalProperties: false` on every object (already enforced by `Strict`). A unit test walks every output model's JSON schema and fails on any unsupported keyword, so a future field cannot break the first live call.
- **Spend protection:** the gateway's virtual-key budget disappears with the gateway; the app's own daily cap (`assert_under_cap`, which sums the ledger) remains the guard. In the Anthropic Console, give the production key its own workspace with a monthly spend limit (the console offers workspace limits — verify the exact form at setup, record it in `operations.md`).
- **Where `ANTHROPIC_API_KEY` lives:** it becomes an app secret (`Secrets.anthropic_api_key`), needed by the worker and the CLI's `eval-prompts`; `NEEDED_SECRETS` names it instead of `LLM_GATEWAY_URL`/`LLM_GATEWAY_KEY`.
- `cli eval-prompts --model claude-…` (no prefix); its `completion.model.split('/')[-1]` goes (dead without prefixes).
- **Timeout:** the shared `httpx.Client` of `build_services` has a 30 s default; the gateway passes `timeout=settings.llm.timeout_seconds` (120 s) per request.

## 3. Web and worker in one service

**Start script** `ops/start.sh` (bash, in the image; the Render service's `dockerCommand: ./ops/start.sh`). It is specified **once, in the operations plan §7.2**, and shipped in this milestone exactly as written there: it starts uvicorn and the worker, forwards SIGTERM to both, **restarts a crashed worker with back-off (10 s up to 5 min) without touching the web process**, and ends the container only when the web process dies (Render then restarts it).

- On SIGTERM uvicorn finishes open requests and the worker finishes its current mail and stops before the next claim (SES plan §5 step 2.3).
- `FORWARDED_ALLOW_IPS` defaults to `*` as today; M9 sets Render's proxy addresses (`implementation-notes.html` question 9).
- Render gives the old instance a shutdown delay before SIGKILL; `maxShutdownDelaySeconds: 300` (operations plan §7.1; verify the field and its maximum in the Blueprint reference) so a summary call in flight (≤ 120 s) finishes.
- **Dockerfile changes:** `COPY ops ./ops`; `ops/start.sh` committed executable (`git update-index --chmod=+x ops/start.sh`); `ENV UV_NO_DEV=1`, because `uv run` (used by `preDeployCommand` and compose) would otherwise install the dev group — pytest, ruff — over the network at every deploy; the PostgreSQL 17 client and restic (§5) with their prerequisites `ca-certificates curl gnupg bzip2`. The default `CMD` (web only) stays for `docker run`; compose keeps its two services.
- A backup still running at SIGTERM is killed with the container; restic then leaves a stale lock — `operations.md`: "`restic unlock` if a backup reports a lock".

**Memory:** the 512 MB instance holds uvicorn (one worker process), the worker, and during the daily backup `pg_dump` and `restic`. Measured before M6b is done: `docker run --memory=512m -e PORT=8000 …` (the script needs `PORT`) with the production command, a summary call, a send of 200 mails to Mailpit and a backup run in parallel; peak resident memory recorded in `operations.md`. **Above 450 MB:** first reduce (uvicorn `--workers 1` is the default; lower the httpx pool; check for a leak), not upgrade — the next Render size costs $25.

**Deploy overlap:** Render starts the new instance, waits until `/health` answers, then stops the old one — for up to a minute both run, each with a worker. §4 makes that safe.

## 4. One worker at a time: the leader lock

The worker has always assumed it is the only step runner (`# ponytail: one sequential worker…` in `worker.py`). The mailing send is protected per mailing by an advisory lock; appearance steps (LLM calls) are not. During a deploy overlap two workers could summarise the same video twice (money) or race a transition.

**Rule:** each tick first takes a session-level advisory lock on a dedicated connection; if another process holds it, the tick is skipped (logged `worker.not_leader` at DEBUG). Released in `finally`; if the unlock fails, the connection is invalidated — a session-level advisory lock survives the end of its transaction and the return of the connection to the pool, so an unreleased lock would block every later tick. The mailing lock is taken *inside* a tick on its own connection; the two never wait on each other (both are `try` locks).

**One helper, not two:** `mailing.exclusive(mailing_id)` moves to `app/db/locks.py` as `advisory_lock(namespace: int, key: int)` using the two-integer form `pg_try_advisory_lock(namespace, key)`; namespaces are constants there (`MAILING = 1`, `WORKER = 2`). The mailing lock becomes `advisory_lock(MAILING, mailing_id)`, the leader lock `advisory_lock(WORKER, 0)`. The two-key form keeps a mailing id from ever colliding with the leader key. `mailing.exclusive` is deleted, its callers use the helper; the log event `MAILING_UNLOCK_FAILED` becomes `LOCK_UNLOCK_FAILED` (`lock.unlock_failed`, with namespace and key).

**Tests:** a second session holds the leader lock → `run_tick` does nothing (no step, no periodic job); released → the next tick runs; a failing unlock invalidates the connection (new `tests/integration/test_locks.py`). The existing lock tests in `tests/integration/test_mailing.py` (≈ lines 420–439) simulate "another worker" with the one-key `pg_advisory_lock(:id)`; they switch to `pg_advisory_lock(1, :id)` (`locks.MAILING`), or they would stop exercising the lock. Mutation probe: skip the leader check → the test fails.

## 5. Backups, from inside the worker

**Why in the worker:** it already has the database connection, a periodic-job scheduler (`job_runs`, one run per interval, recorded before it starts) and the logging; a separate cron service would cost a minimum of $1/month and a second image.

**Target:** Backblaze B2, bucket `klartext-backups` (name follows the product), account region **EU Central (Amsterdam)** (chosen when the B2 account is created — it cannot be changed later), first 10 GB free; our dumps are far below. restic encrypts client-side before upload, so the provider sees only ciphertext. restic talks to B2 through **B2's S3-compatible API** (`s3:https://s3.<region>.backblazeb2.com/klartext-backups/platform`, the endpoint shown in the bucket's details) — restic's own documentation recommends it over its native B2 backend because of that backend's error handling (checked 2026-09-27).

**The key cannot destroy the backups.** The application key is restricted to the bucket and has **no `deleteFiles` capability** (list, read, write only — verify the capability names at setup): through the S3 API a delete then only *hides* a file, and the bucket's **lifecycle rule keeps hidden files for 30 days** (`daysFromHidingToDeleting: 30`). A compromised container, a leaked key or a buggy command can hide snapshots, not erase them; for 30 days every snapshot can be restored from its hidden version in the B2 console. restic's own pruning works the same way (it hides), so storage stays small.

**Settings:** `Secrets` gains `restic_repository`, `restic_password`, `backup_s3_key_id`, `backup_s3_secret`, `backup_heartbeat_url`, `worker_heartbeat_url` (all `""`) — secrets are fields of `Secrets`, and a value in `.env` never reaches `os.environ`, so it could not be "passed through".

**The job** `backup` (daily, registered in `run_periodic_jobs` after `cleanup`; module `app/backup.py`, one public function `run_backup(settings, run=subprocess.run, get=httpx.get)` — `run` and `get` are the test seams):

1. If `RESTIC_REPOSITORY` is empty (local development), log `backup.disabled` once and return.
2. `restic backup --stdin-from-command --stdin-filename platform.dump --tag daily -- pg_dump --format=custom --no-owner --dbname=<url>` via `run(…, check=True, timeout=900, env=…)` (15 minutes — a dump below 1 GB takes seconds to minutes; the worker does nothing else meanwhile, operations plan §6). `--stdin-from-command` makes restic fail the snapshot when `pg_dump` exits non-zero — a broken dump never becomes a "successful" backup. `<url>` is the database URL without SQLAlchemy's `+psycopg` driver suffix **and without the password** (a password in the command line is visible in the process list); the password goes into `PGPASSWORD` (one small function in `config.py` splits the URL, tested).
3. `restic forget --keep-daily 7 --keep-weekly 4 --prune` — about one month of history. Deliberately short: every snapshot holds addresses of fans who have since unsubscribed or asked for erasure (MVP plan §13 names the retention); with the 30 days of hidden versions a deleted address is gone from the backups after at most ≈ 2 months.
4. Success → log `backup.done` (duration, restic's summary line) and GET `BACKUP_HEARTBEAT_URL`; failure (non-zero exit, timeout) → log `backup.failed` at ERROR with restic's stderr (it contains no secrets) and GET `BACKUP_HEARTBEAT_URL/fail`. A failing ping is logged, never raised.
5. Environment for the subprocess, built explicitly from `Secrets`: `PATH`, `RESTIC_REPOSITORY` (the `s3:` URL above), `RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (restic's names for the S3 credentials, filled from `backup_s3_key_id`/`backup_s3_secret`), `PGPASSWORD` — never logged; restic's stderr is logged only on failure and truncated.

**Image:** the Dockerfile adds the PostgreSQL 17 client from the PostgreSQL project's Debian repository (Debian bookworm ships 15, and `pg_dump` must not be older than the server) and a pinned restic release binary (≥ 0.17 for `--stdin-from-command`; Debian's package is older) verified against its published SHA-256. Both version pins sit in the Dockerfile with a comment.

**Once, by hand** (`operations.md`): create the B2 account (EU region), the private bucket with the lifecycle rule "keep hidden files 30 days", the application key restricted to the bucket without `deleteFiles`; `restic init` against the repository with a long random password; store **the restic password and the key in the owner's password manager too** — losing the Render account must not lose the backups; set the four variables on Render; once a quarter, from the owner's machine, `restic check` against the repository; create the Healthchecks.io check (period 1 day, grace 2 hours).

**Restore drill** (M9, then quarterly; `operations.md`): `restic restore latest --target /tmp/r` on the owner's machine (or a Render shell), `pg_restore` into a scratch database, compare row counts of `creators`, `subscriptions`, `mailings`, `deliveries` with production; note the date in `operations.md`.

**A real restore** (the database is lost): restore the newest snapshot, then — **before the worker sends anything** (set the emergency stop first, operations plan §7.3) — run the cleanup once (it deletes what the retention rules say, MVP plan §13) and `uv run app reapply-erasures` (M7: every fan erased on request since the snapshot is erased again, from the `erasures` log), check the console, release the stop. A restore must never bring back an address somebody asked us to delete.

**Data loss bound:** up to 24 hours (daily dump), plus Render's own 3-day point-in-time recovery for the common case; the off-site copy is for losing the Render database or account.

**Tests:** with fake `run` and `get`, the job calls restic with exactly those arguments and that environment (no password in any argument), pings the success URL on success and the `/fail` URL on a non-zero exit or a timeout, and does nothing when the repository is empty; the job is in the periodic schedule once a day. Worker tests seed `job_runs` with a far-future `last_run_at` for every periodic job they do not test — otherwise `run_tick` also runs the real feed poll against YouTube.

## 6. Worker heartbeat

A hung or crashed worker produces no error, only silence — and Render does not health-check what runs next to the web process. **Rule:** a small `Heartbeat(url, clock=time.monotonic, get=httpx.get)` object, created in `worker.main()` (no module-level state), is called after every tick **that held the leader lock** — a non-leader tick must not ping, or a stuck leader would go unnoticed. If the last ping is ≥ 5 minutes old it calls `get(url, timeout=5)`; failure logs `worker.heartbeat_failed` at WARNING and never raises; empty URL = off. Healthchecks.io check: period 5 minutes, **grace 30 minutes** — a tick that sends a list lasts as long as the send (SES plan §5: ≈ 12 minutes per 10,000 at 14/s); raise the grace when the largest list grows. Test with a fake clock and a fake `get`: first tick pings, a tick 1 minute later does not, one 5 minutes later does; a non-leader tick never pings; a failing ping does not break the tick.

## 7. The removal: every trace of Bifrost and the second service

Same rule as the SES plan §11: complete, in this milestone.

| Where | Remove | Replace with |
|---|---|---|
| `src/app/analysis/llm.py` | `BifrostGateway`, `COMPLETIONS_PATH`, `_ACCOUNT_TROUBLE` words that only the gateway produced ("no keys found"), `MODEL_SETTINGS`'s `bifrost.json` clause, `_raise_if_operator`'s gateway branches (404 at the path, `model_blocked`, virtual key), the module docstring's "OpenAI-compatible HTTP … or the gateway itself", the gateway wording in the docstrings of `LLMTemporaryError`, `LLMError`, `price_of`, `price_for_booking`, `_upstream_message` and the comment in `record_call`, the `CACHE_READ_FACTOR` comment's gateway measurement (it becomes a sentence on the API's own cache fields), the provider-prefix handling in `price_of` | `AnthropicGateway`, `API_URL`, the error mapping of §2 |
| `src/app/services.py` | `BifrostGateway` import and construction | `AnthropicGateway(settings.secrets.anthropic_api_key, settings.llm.timeout_seconds, http)` |
| `src/app/config.py` | `llm_gateway_url`, `llm_gateway_key` | `anthropic_api_key` |
| `src/app/cli.py` | `handle_gateway_config`, `GATEWAY_CONFIG`, the `gateway-config` subcommand, the hint "ANTHROPIC_API_KEY and LLM_GATEWAY_URL/_KEY", `completion.model.split('/')[-1]` in `handle_eval_prompts` | hint "ANTHROPIC_API_KEY" |
| `src/app/worker.py` | `LLM_GATEWAY_URL`, `LLM_GATEWAY_KEY` in `NEEDED_SECRETS`; the `# ponytail: one sequential worker` wording "the only process" stays true (one leader) | `ANTHROPIC_API_KEY`; leader lock, stop checks, `Heartbeat` |
| `src/app/log.py` | `MAILING_UNLOCK_FAILED` | `LOCK_UNLOCK_FAILED`, `WORKER_NOT_LEADER`, `WORKER_HEARTBEAT_FAILED`, `BACKUP_DONE`, `BACKUP_FAILED`, `BACKUP_DISABLED` |
| `pyproject.toml` | the comment naming "the LLM gateway" | the API |
| `src/app/delivery/mailing.py` | `exclusive` | `app/db/locks.advisory_lock` |
| `config/bifrost.json` | the file | — |
| `config/settings.toml` | the `[llm]` comment about `gateway-config` and recreating the container; provider prefixes in model names and price keys | the comment "switching model: these two lines and the price entry below" |
| `docker-compose.yml` | the `bifrost` service, `bifrost-data` volume, `LLM_GATEWAY_URL` on web and worker | — |
| `render.yaml` | the `worker` service, the `bifrost` private service and its disk, `LLM_GATEWAY_*`, `BIFROST_*`, `APP_PORT` | one web service with `dockerCommand: ./ops/start.sh`, `maxShutdownDelaySeconds: 300`, and the env list of MVP plan §15.2 |
| `.env.example` | `LLM_GATEWAY_URL`, `LLM_GATEWAY_KEY`, `BIFROST_SETUP_TOKEN` and their comments | `ANTHROPIC_API_KEY` (now the app's), `WORKER_HEARTBEAT_URL`, `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `BACKUP_S3_KEY_ID`, `BACKUP_S3_SECRET`, `BACKUP_HEARTBEAT_URL`, `FORWARDED_ALLOW_IPS` — each with a comment, all empty locally |
| tests | the test keeping `settings.toml` and `bifrost.json` in step (`test_operator_errors.py::TestOneModelNameInTwoFiles`); `test_operator_errors.py::TestTheGateway` → `TestAnthropic` (401, 402, 403, 400-credit, 404-model, other 400); gateway tests in `tests/unit/test_llm_gateway.py` rewritten for `AnthropicGateway` (body shape, headers, usage mapping incl. cache fields, `stop_reason`, the schema retry); `"anthropic/…"` model names in `tests/unit/test_config.py` and `tests/integration/test_public_pages.py`; prefix cases in the price tests; the one-key lock probes in `test_mailing.py` (§4) | the schema-keyword test (§2), leader-lock test (§4), backup tests (§5), heartbeat test (§6) |
| docs | README (Bifrost in the service list, key table, `gateway-config`), ARCHITECTURE (the gateway in the module cut and Decisions, the "Gateway 'no keys found'" troubleshooting), backlog (the "no separate gateway" and "worker as a thread" levers → done), `implementation-notes.html` entries that describe Bifrost as current (annotated "*Überholt am 27.09.2026*") | ARCHITECTURE Decisions entries: "Anthropic's Messages API directly (gateway removed 2026-09-27)", "web and worker in one container in production, leader lock" |
| manifest | §8 and §13 name Bifrost as the gateway; §7.8 names "Railway oder Render" and procrastinate | updated with all decisions of 2026-09-10, -21 and -27 (the box in §8) |

**The gate — M6b is not done until this prints nothing:**

```sh
git grep -nI -e bifrost -e Bifrost -e BIFROST -e LLM_GATEWAY -e gateway-config -e chat/completions \
  -e response_format -e BifrostGateway \
  -- src tests config migrations pyproject.toml .env.example render.yaml docker-compose.yml Dockerfile .github \
     README.md docs/ARCHITECTURE.md docs/runbooks docs/backlog.md docs/manifest
```

The word "gateway" itself stays where it names the manifest's abstraction (`LLMGateway`).

## 8. Milestone M6b

### M6b — Lean platform: no gateway, one service, backups (≈ 3 sessions) — *added 2026-09-27*
Test-first for every rule; the leader lock and the backup's failure path get mutation probes.
- [ ] `AnthropicGateway` (§2) with its tests, the schema-keyword test, model names without prefix, price keys, `ANTHROPIC_API_KEY` as app secret; one live call per output model (`uv run app eval-prompts --model claude-sonnet-5`) reads well.
- [ ] `app/db/locks.py`; the mailing lock moved; the leader lock in `run_tick` (§4).
- [ ] `ops/start.sh` exactly as in the operations plan §7.2 (verified there in the project's image), and PID 1 checked to be the script; Dockerfile with PostgreSQL 17 client and pinned restic; memory measured under 512 MB (§3) and recorded.
- [ ] **Vendor boundaries test** (`tests/unit/test_boundaries.py`): vendor **host names and command texts**, matched as regular expressions over `src/app/**/*.py` (templates and tests excluded — they hold watch URLs and legal links by design), may appear only in their own modules: `amazonaws\.com` → `delivery/email_client.py`, `delivery/sns.py`, `config.py`; `api\.anthropic\.com` → `analysis/llm.py`; `googleapis\.com` → `sources/`, `transcripts/`; `youtube\.com/(watch|feeds|channel)` → `sources/`; `backblazeb2\.com` and `restic ` → `backup.py`; (from M7b) `stripe\.com` → `billing/stripe_client.py`. Module imports (`from app.delivery.sns import …`) are the seam working, not a leak. A new vendor gets its row with its module; the test must pass on the day it is written. This keeps every provider swappable behind one module (MVP plan §3.1) and fails the build the day a vendor detail leaks into a step, a route or a template.
- [ ] `app/backup.py` + periodic job + tests (§5).
- [ ] Worker heartbeat + test (§6).
- [ ] `render.yaml` in its new shape (MVP plan §15.2); `.env.example`; README; `operations.md` sections for backup, restore drill, heartbeat, Anthropic workspace limit.
- [ ] Every row of §7; the gate prints nothing.
- [ ] **Manifest updated** (German, each change marked „*geändert am …*“; the mail-provider passages §7.6/§7.8 were already done in M6a; change notes never name the removed provider or gateway): §1.5 and §7.9 („genau einmal“ → nie doppelt, SES-Plan §5); §3.1, §7.2 (diagram), §7.3 and §13 (feed poll instead of push, 2026-09-10); §4.2 (mail cost with SES); §5.5 (design reviewed as HTML drafts; video slot); §6.2, §7.4, §11 and §13 (no Whisper in the MVP); §6.3 (the open-rate criterion — MVP plan §20 question 4); §7.8 (no procrastinate; httpx sync instead of "Async-Client"; Render in one service instead of "Railway oder Render"); §8 and §13 (Anthropic directly; the `LLMGateway` abstraction stays); §10 (milestones M6a, M6b, M6c, D and M10); §13's date. The M6b gate includes `docs/manifest`.
- [ ] A review of the whole diff for dead code and simplification.
- **Done when:** `docker compose up` runs without a gateway and a real summary comes back from Anthropic; the production image started with `ops/start.sh` under `--memory=512m` serves `/health`, runs worker ticks, stops both processes on SIGTERM within the shutdown delay and exits when the web process is killed; two such containers against one database never run a step twice (leader lock); a backup run against a local restic repository produces a snapshot that `pg_restore` restores with matching row counts; the full suite, ruff and both gates are clean.

## 9. Verified facts

Checked 2026-09-27 against Anthropic's API documentation, render.com, backblaze.com (via third parties where the page failed), healthchecks.io and the repository.

- **Anthropic structured outputs:** `output_config.format = {"type": "json_schema", "schema": …}` on `POST /v1/messages`, generally available, no beta header; the old `output_format` is deprecated and needs the header `structured-outputs-2025-11-13`. Supported models include `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001` and the Opus 4.6–5.5 family. Unsupported schema features: recursion, complex types in enums, external `$ref`, `minimum`/`maximum`/`multipleOf`, `minLength`/`maxLength`, `minItems` other than 0/1; `additionalProperties: false` required on objects. The JSON is in the `text` content block. The documentation warns that on `max_tokens` the output may be incomplete and on `refusal` it may not match the schema — hence the `LLMError`. The schemas Pydantic generates use `anyOf`, `$defs`/`$ref`, `default`, `title` and `description`, all supported.
- **Anthropic OpenAI compatibility layer:** `response_format` is ignored; described as not production-ready. Not used.
- **Render:** Hobby workspace $0 + compute; web service `0.5c-512mb` $7; Postgres smallest $6 + $0.30/GB; the old instance is stopped after the new one passes its health check (zero-downtime), SIGTERM then SIGKILL after the shutdown delay; free web services spin down after 15 minutes and free Postgres expires after 30 days — both unusable. Running two processes in one service via a start script is not forbidden (the docs show `bash -c` commands). **To verify:** `maxShutdownDelaySeconds` in the Blueprint; log retention on Hobby.
- **Backblaze B2:** $6.95 per TB-month, first 10 GB free (via third-party price pages; the official page did not load); region per account. restic's documentation: "Due to issues with error handling in the current B2 library that restic uses, the recommended way to utilize Backblaze B2 is by using its S3-compatible API"; through that API restic's deletes only hide files, which B2 lifecycle rules then remove; `--stdin-from-command` exists since restic 0.17. **To verify at setup:** the key capability names and that a key without `deleteFiles` can still hide.
- **Healthchecks.io:** free Hobbyist plan with 20 checks; ping `https://hc-ping.com/<uuid>`, failure `…/fail`.

## 10. Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| 512 MB is not enough for web + worker + backup | Two Python processes plus `pg_dump`/`restic` once a day | Measured before M6b closes (§3); reduce first; the $25 size only on evidence. |
| A crashed worker, or a crashed web process | Two processes share one container | `ops/start.sh` restarts a crashed worker with back-off while the web keeps serving; only a web crash ends the container, and Render restarts both (operations plan §7.2). Steps resume from the database. |
| Two workers during a deploy | Render overlaps instances | Leader lock (§4); mailings also keep their own lock. |
| No gateway-level spend limit | The virtual-key budget is gone | The app's daily cap per creator (ledger sum) + a workspace spend limit at Anthropic. |
| Backups exist but do not restore | Untested backups | `--stdin-from-command` fails broken dumps; heartbeat on success only; restore drill in M9 and quarterly. |
| B2 is a US company | Backup provider | Client-side encryption (restic); EU region; listed as a processor. |
| A compromised container deletes the backups | The backup key lives in the container | The key cannot delete, only hide; hidden versions stay 30 days; quarterly `restic check` from the owner's machine (§5). |
