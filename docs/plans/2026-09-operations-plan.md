# Operations Plan — failure handling, the operator's view, safe deploys (milestone M6c)

> **Status:** planned, not started · **Date:** 2026-09-27, revised the same day after an adversarial review against the code (the start script was verified in the project's own image) · **Part of the MVP.** One step of the MVP plan (`2026-09-mvp-implementation-plan.md`, §17: milestone **M6c**, after M6b, before D). The conventions of the MVP plan apply unchanged — §3 principles (incl. "a removal is complete"), §14 testing with mutation probes, §16 documentation, §17's definition of done.
>
> **Why it exists.** The owner, 2026-09-27: the platform runs on a cheap host, so it must handle a crash with composure; everything must be logged; every relevant fact must reach the owner at once, simply and securely; he must see when the next summaries are made and the next mails go out — the moments not to deploy — and must never have to remember such things himself. *Cheap, yes — but never at the price of an unreliable service.*
>
> **Progress:** M6c `[ ]` — tick the boxes in §9.

## Table of contents

1. [What the owner gets](#1-what-the-owner-gets)
2. [How the platform behaves when things fail](#2-how-the-platform-behaves-when-things-fail)
3. [Alert channels that do not depend on the platform](#3-alert-channels-that-do-not-depend-on-the-platform)
4. [Durable records: component state and incidents](#4-durable-records-component-state-and-incidents)
5. [The operator console `/betrieb`](#5-the-operator-console-betrieb)
6. [The daily operator mail](#6-the-daily-operator-mail)
7. [Deploys, the start script, the emergency stop](#7-deploys-the-start-script-the-emergency-stop)
8. [Honest limits of the cheap setup](#8-honest-limits-of-the-cheap-setup)
9. [Milestone M6c](#9-milestone-m6c)

---

## 1. What the owner gets

| Need | Answer |
|---|---|
| "What is happening right now, and is everything healthy?" | The **operator console** `/betrieb` (§5): a traffic light per component, what is running, the deployed version, open incidents — read straight from the database, so it is correct even when logs have rotated. |
| "When is the next summary made, the next preview sent, the next mailing sent — to how many fans, for how long?" | `/betrieb/zeitplan` (§5): the next seven days, per mailing and per pipeline row, with estimated send durations; the day ahead in the **daily operator mail** at 07:00 (§6). |
| "When may I deploy?" | **Any time — by design** (§7.1): a send stops cleanly between two mails and resumes in the new container, nobody gets a mail twice; a summary call in flight finishes within the shutdown delay. Render deploys only after CI has passed. The console and the daily mail still show the **quiet windows** (no send running or imminent), for whoever prefers to deploy in them. |
| "Something went badly wrong — can I stop the mails at once?" | **Emergency stop** (§7.3): one button in the console pauses every send before its next mail — no deploy, no restart; for each paused mailing the owner then chooses "fortsetzen" or "Rest abbrechen". |
| "Something broke — do I hear about it?" | Yes, through **independent channels** (§3): web down (UptimeRobot), worker silent (Healthchecks.io), backup failed (Healthchecks.io), every unexpected error (Sentry), mail reputation (AWS), failed CI or deploy (GitHub, Render) — and for problems only a person can fix, one mail from the platform itself. |
| "What happened last week?" | The **incident list** (§4) lives in the database for 180 days, independent of Render's 7-day log retention; logs carry the detail. |
| "Is all of this reachable safely?" | The console sits behind a password only the owner holds (HTTP Basic over HTTPS, brute-force protected, logged, §5). Nothing else is exposed. |

## 2. How the platform behaves when things fail

Every row below is covered by a test or a drill in §9; the log event names are constants in `app/log.py`.

| What happens | What the platform does | What the owner sees | What the owner does |
|---|---|---|---|
| **Container crash, out of memory, host restart** | Render restarts the container; every step resumes from the database state (MVP plan §9); a mail in flight at a hard kill is at most one uncertain delivery (SES plan §5); an LLM call in flight is repeated on the retry (paid twice, both in the ledger) | UptimeRobot mail if the site is down longer than one check (5 min); the **downtime incident** "worker not running from … to …" (§4.1); Sentry if an error preceded it | Usually nothing; if it repeats, the incident and Sentry say why |
| **Worker process crash** (web still fine) | `ops/start.sh` restarts the worker — after 10 s, doubling up to 5 min while it keeps crashing — and the web keeps serving (§7.2) | Incident `worker.restarted` with the exit status; Healthchecks mail if no tick completes for 30 min | Read the error in Sentry |
| **Worker hangs** | — | Healthchecks.io mail after the 30-minute grace; the downtime incident when it recovers | Restart the service in the Render dashboard |
| **Web process crash** | The container ends; Render restarts web and worker | UptimeRobot mail if longer than one check | Usually nothing |
| **Database unreachable** | Requests fail with an error page; worker ticks fail and are retried every minute; transactions leave no half-written state | UptimeRobot, Sentry; the downtime incident with its duration once ticks succeed again | Check Render's status page |
| **Database nearly full** | — | Console light yellow at 80 % of the plan's storage, red at 90 % (§5) | Delete old data or move to the next plan |
| **Database lost or corrupted** | — | — | Restore: Render's point-in-time recovery (last 3 days) or the B2 backup (`operations.md`, drilled in M9) |
| **A deploy while mails are going out** | The send stops between two mails and resumes in the new container; nobody gets a mail twice | The console shows the send continuing | Nothing |
| **A bug sends wrong content** | The emergency stop takes effect before the next mail (§7.3) | Red banner; the paused mailing with its progress | Press the emergency stop; then "Rest abbrechen" for the wrong mailing, fix, deploy, release the stop |
| **Amazon SES slow or refusing temporarily** | Retries with the ladder (MVP plan §9.4) | Attempts in the console; an incident if a mailing gives up | Nothing unless it persists |
| **SES refuses for account reasons** (credentials, sandbox, quota, account paused) | Rows are parked, attempts not counted (`NeedsOperator`) | One operator mail **if mail still works**; Sentry, the console and AWS's own alarm in any case | Follow the fix text in the incident |
| **Anthropic down, overloaded, credit empty, key revoked** | Temporary → retries; account problems → parked; the daily cost cap stops runaway spending | Incident + one operator mail + Sentry | Top up credit or fix the key; parked rows continue by themselves |
| **YouTube quota exhausted, transcript source blocked** | Parked or retried; nothing lost | Incident; the quota line (M7a) | Wait for the reset or request more (`operations.md`) |
| **Render outage** | Nothing runs; afterwards everything resumes; a mailing whose time has passed goes out as soon as it can — never without its preview and the full stop window (MVP plan §9.2); one that cannot go out for too long ends with an honest notice to the creator | UptimeRobot mail; the downtime incident | Nothing |
| **Backup fails** | Retried the next night | Healthchecks.io `/fail` mail at once; incident | Read the incident; `restic unlock` if a lock is reported |
| **A mailing gives up** — after ten temporary failures without progress (≈ 23 h, the ladder resets whenever a mail goes out), or when it has been parked for the operator until 12 h past its send time (MVP plan §9.4) | Terminal `failed`, creator notified honestly | Incident + operator mail | Fix the cause; the runbook resets the row |
| **The SES daily quota would not suffice** for a mailing | The send does not start; the mailing is parked for the operator (SES plan §5) | Days ahead: the schedule marks the mailing "Quote reicht nicht" and the daily mail warns; at send time an incident + operator mail | Request a quota increase in time (`operations.md`) |
| **SES feedback stops arriving** (topic setting wrong, subscription lost) | Our own misconfiguration is answered with 503, so SNS keeps retrying; a foreign topic is refused with 403 and recorded | Incident "keine SES-Rückmeldungen" when mails went out more than 2 h ago and no event arrived since | Check `SES_FEEDBACK_TOPIC_ARN` and the SNS subscription (`operations.md`) |
| **A secret is missing at start** | The process starts and logs which feature cannot work | Incident (recorded by the worker) | Set the variable in the dashboard |
| **An environment variable is changed in the Render dashboard** | Render redeploys the service at once (bypassing CI); a running send stops and resumes as above | — | Nothing; `operations.md` notes it |

## 3. Alert channels that do not depend on the platform

An alarm that travels through the thing that is broken never arrives. Therefore:

| Channel | Watches | Independent of our code? | Cost |
|---|---|---|---|
| UptimeRobot | `https://<domain>/health` every 5 min | yes | free |
| Healthchecks.io | worker heartbeat (period 5 min, grace 30 min); backup (1 day, grace 2 h; `/fail` on error) | yes — silence is the alarm | free |
| Sentry (EU) | every ERROR with traceback, web and worker | its SDK runs in our process, but the mail comes from Sentry | free |
| AWS CloudWatch alarm | SES bounce and complaint rates (SES plan §9 step 8) | yes | cents |
| Render | failed deploy (e-mail) | yes | free |
| GitHub | failed CI (e-mail) | yes | free |
| **Platform operator mail** (§4.3) | problems only a person can fix | no — it uses our SES; the channels above cover the case where mail itself is broken | — |

All of them mail the owner. **Drill:** once a quarter, together with the restore drill, pause the Healthchecks.io check and record a test incident — each channel must produce its mail (`operations.md`).

## 4. Durable records: component state and incidents

### 4.1 Component state

`job_runs` (today: `name`, `last_run_at`) gains `last_ok_at`, `last_error_at`, `last_error` (text, truncated like the other error columns) — it already records each periodic job before it starts; now it also records how it ended. Two more rows:

- `worker` — `last_ok_at` written **at the start of every tick the worker leads, after every step and every periodic job, and after every page of a send** (and the heartbeat ping, throttled to one per 5 minutes, goes out at the same points) — so a backfill of twenty videos, a long send or the backup never looks like a dead worker. No single unit of work lasts longer than a few minutes: an LLM call ≤ 120 s (twice with the schema retry), a page of a send ≤ 100 s at the sandbox's 1/s, the backup ≤ 15 min (its timeout);
- `ses.feedback` — written by the webhook at most once a minute (`… WHERE last_run_at < now() - interval '1 minute'`).

Everything else a traffic light needs is derived from data that exists anyway: the last successful mail (`max` of `deliveries.sent_at`, `mailings.preview_sent_at`, `subscriptions.confirm_sent_at`), the last LLM call and its outcome (`llm_calls`), the last poll, cleanup and backup (`job_runs`), the database size (`pg_database_size(current_database())`).

**Downtime detection** runs at the end of every tick the worker leads: if the previous `worker.last_ok_at` was more than **20 minutes** before this tick's start — longer than any single unit of work above — it records `worker.downtime` with both times. That covers a crash, a hang, a database outage and a Render outage alike — the owner learns *that* the worker did not run and *for how long*, whatever the cause. A worker started by `ops/start.sh` after an exit (environment `WORKER_RESTARTED_AFTER=<exit status>`) records `worker.restarted` (warning) with the status.

### 4.2 Incidents

A new table `operator_events`:

| Column | Meaning |
|---|---|
| `id`, `kind` | the log event name (list below) |
| `level` | `warning` / `error` |
| `service`, `problem`, `fix` | for `NeedsOperator`: the service, the provider's own words, what to check — the three fields the log line already has |
| `refs` | jsonb: `appearance_id`, `mailing_id`, `creator_id`, `delivery_id`, `subscription_id` where known |
| `first_seen_at`, `last_seen_at`, `count` | de-duplication (below) |
| `notified_at` | when the operator mail included it |
| `acknowledged_at` | set by the owner in the console ("erledigt") |

**Kinds:** `operator.action_needed`, `item.failed`, `mailing.failed`, `email.uncertain`, `backup.failed`, `worker.downtime`, `worker.restarted`, `worker.tick_failed`, `worker.step_crashed`, `worker.periodic_failed`, `llm.cost_cap_hit`, `llm.prices_stale`, `config.secret_missing`; from M7a/M7b their warnings and billing incidents (billing plan).

**De-duplication** — one problem is one line, whose `count` rises; merged only into an incident that is not yet acknowledged, within 6 hours of its `last_seen_at`:
- `operator.action_needed`: same `(kind, service, problem)` — one revoked key across fifty parked rows is one incident, and an Anthropic problem never swallows an SES one;
- row-bound kinds (`item.failed`, `mailing.failed`): same `(kind, refs)`;
- `email.uncertain`: same `(kind, refs.mailing_id)`;
- everything else: same `kind`.

**Refs** are the call's own keyword arguments restricted to the id names above, merged over the ids already bound in the structured-log context (`structlog.contextvars.get_contextvars()` — the worker binds `appearance_id`/`mailing_id` before each step).

**No personal data:** `record` replaces e-mail addresses in `problem` with `<address>` (one regex, unit-tested — an SMTP refusal can quote a recipient) and truncates the text. The cleanup deletes incidents whose `last_seen_at` is older than 180 days, acknowledged or not.

**The recorder** — `IncidentRecorder` (a plain class in `app/ops/incidents.py`, method `record(kind, level, *, service=None, problem=None, fix=None, **refs)`) becomes a field of `Services`, so tests use a fake that keeps a list (`tests/fakes.py`); the real one writes **in its own short-lived session, committed at once, and never raises into its caller** (the pattern of the LLM ledger: the record must survive the rollback of the step that failed). `app.log.report_operator_action` imports it inside the function, as it already does for `NeedsOperator`, so no import cycle arises.

**Where it is called — once per event, after the commit that makes the event real:**

| Kind | Call site (today's code) |
|---|---|
| `operator.action_needed` | inside `log.report_operator_action` (called by the worker's `park_for_the_operator`, `steps.py`, `subscriptions.py`, `web/routes/creator.py`, `analysis/llm.py`) |
| `item.failed` | `worker.record_outcome`, after its transaction (not at the two log lines inside it) |
| `mailing.failed` | `worker.record_mailing_outcome`, after its transaction (not in `mailing.fail`, which runs before the commit) |
| `llm.cost_cap_hit` | `llm.assert_under_cap` only (not the worker's second log line) |
| `email.uncertain` | the send loop (SES plan §5 step 2.7) |
| `backup.failed` | `backup.run_backup` |
| `worker.downtime`, `worker.restarted`, `worker.tick_failed`, `worker.step_crashed`, `worker.periodic_failed` | the worker's loop, next to the existing log lines |
| `llm.prices_stale`, `config.secret_missing` | the worker's start only (the web process records nothing at start — one record per problem, and tests that create apps stay silent) |

### 4.3 The operator mail

At the end of every tick the worker leads: if there are `error` incidents with `notified_at` empty, **one** mail lists them all (subject "[Klartext] Handlung nötig: n Probleme", each with service, problem, fix and a link to the console) and sets `notified_at`. A failed send is logged at WARNING and the next attempt waits 30 minutes (`job_runs('operator.notify')`) — a broken mail path must not produce an error every minute. An incident is mailed **once**; the daily mail (§6) repeats everything still open. Warnings are not mailed at once; they appear in the daily mail. `OPERATOR_EMAIL` joins the worker's needed secrets.

## 5. The operator console `/betrieb`

Read-only pages in the web app (German labels, technical details in English as the logs have them), `noindex`, not linked from any public page. Routes in `web/routes/operator.py`.

**Access** — HTTP Basic over HTTPS, user `betrieb`, password hash in the secret `OPERATOR_PASSWORD_HASH`:
- format `scrypt$16384$8$1$<salt b64>$<hash b64>` (stdlib `hashlib.scrypt`, n = 2¹⁴, r = 8, p = 1, 32 bytes — within its default memory limit); `uv run app operator-password` asks for a password (`getpass`) and prints the hash to paste into Render;
- the dependency first checks a **per-IP failure counter** (the `limits` package slowapi already brings; 5 failures per minute, counted only on failures — a normal visit, which re-sends the credentials with every request, is never throttled), then compares the user name with `hmac.compare_digest`, then verifies the password **under a process-wide lock** (one scrypt at a time — 16 MiB each; parallel guesses must not exhaust the 512 MB container); a successful `Authorization` value is remembered as its SHA-256 for the process lifetime, so browsing costs no further scrypt;
- failure → 401 with `WWW-Authenticate: Basic realm="betrieb"`, logged `operator.login_failed`; an empty hash → 404 (the console is off);
- deliberately **not** a magic link: the console must work exactly when mail does not;
- the only write, the "erledigt" POST, checks `Sec-Fetch-Site: same-origin` (or `Origin` equal to `BASE_URL`) and answers 403 otherwise — cached Basic credentials are sent on cross-site requests, so the same-site cookie rule of MVP plan §13 does not protect this form.

**Pages** — all fed by one query module, `app/ops/status.py`, which also feeds `cli status` and the daily mail. One source, three views. The emergency stop and the mailing actions are also CLI commands (`uv run app pause-sending on|off`, `app stop-mailing <id>`, `app cancel-rest <id>`) for the Render shell — the same functions the console calls.

1. **Übersicht** (`/betrieb`):
   - traffic lights: **Worker** (`worker.last_ok_at` < 5 min green, < 20 min yellow, else red), **Datenbank** (answers; size vs. the plan's storage: yellow at 80 %, red at 90 % — the storage size is a module constant next to the query, changed when the plan changes), **Mailversand** (last successful send; an open `NeedsOperator` of the mail service → red), **SES-Rückmeldungen** (last event; red when mails went out more than 2 h ago and no event arrived since — the same rule records the incident), **LLM** (last call ok? today's cost vs. cap), **YouTube** (last poll; quota from M7a), **Backup** (last success < 26 h), **Überwachung** (heartbeat and backup URLs set?);
   - the **emergency stop** as a red banner when active (§7.3);
   - the **version** (`RENDER_GIT_COMMIT`, first 12 characters; "dev" locally) and the container's start time;
   - **what is running now** — a mailing in `sending` with progress ("1.234 von 5.000, noch ≈ 5 min"), due pipeline rows;
   - **the quiet window** (§7.1): "Ruhig bis 14:40" or "Versand läuft (noch ≈ 5 min)";
   - the next five scheduled events; open incidents (count and the newest three); today's numbers: mails sent, new bounces and complaints, uncertain deliveries, LLM cost;
   - the page renders even when the database does not answer: that section then says "Datenbank: keine Antwort" instead of an error page.
2. **Zeitplan** (`/betrieb/zeitplan`): the next seven days, grouped by day, in `product.timezone` — per open mailing: sentiment at `send_at − 2 h`, preview at `send_at − 1 h`, send at `send_at` with today's recipient count and the estimated duration (`recipients ÷ max_send_rate_per_second`), creator, video title, status, attempts, and **"Quote reicht nicht"** when the recipients exceed the SES daily quota left at that time (SES plan §5) — days ahead, so there is time to request more; pipeline rows with their next step and time ("Zusammenfassung von ‚…' — fällig um 13:05, Versuch 2"); periodic jobs with their next run (feed poll, cleanup, backup, daily mail; billing jobs from M7b); below a line, the last 24 hours: what ran and how it ended.
3. **Probleme** (`/betrieb/probleme`): open incidents first (kind, level, service, problem, fix, refs, first/last seen, count) with the "erledigt" button; rows in `failed` and parked rows with their fix text; uncertain deliveries per mailing.

**The console's writes** — each a same-origin POST (checked as above), each logged with its old and new state and recorded as an incident of level `warning` so the history shows who pressed what, and when:
- **"erledigt"** on an incident;
- **Notstopp an / aus** (§7.3);
- **"Stoppen"** on an open mailing that has not started sending — the same conditional transition as the creator's stop link (`MAILING_STOPPABLE → stopped`);
- **"fortsetzen"** or **"Rest abbrechen"** on a mailing in `sending` while the emergency stop is on — "Rest abbrechen" is the one new transition, `sending → cancelled`, conditional like every other (`… WHERE status = 'sending'`): the recipients not yet sent never get this mailing, the ones sent stay counted, the creator gets the honest `send_failed` notice.

The times and durations come from pure functions in `app/jobs/schedule.py` (next sentiment/preview/send from `send_at`; next run of a periodic job; send duration; the quiet window), unit-tested with a stepped clock — the same functions the worker uses to decide what is due, so the console cannot promise a time the worker does not keep.

## 6. The daily operator mail

A periodic job `operator_digest` at **07:00** in `product.timezone` sends one German plain-text mail to `OPERATOR_EMAIL`:

- **Heute geplant:** every preview and send of the next 24 hours with time, creator, video, recipients and estimated duration; summaries expected;
- **Ruhige Zeitfenster heute** (§7.1);
- **Offene Probleme:** every open incident, newest first, with its fix;
- **Gestern:** mails sent, new bounces and complaints, uncertain deliveries, LLM cost, YouTube quota used (M7a), backup result, worker downtime;
- a link to the console.

**Jobs at a clock time.** `run_periodic_jobs` knows only intervals today (`(name, every, run)` checked by `job_is_due`). Each entry gains a `due(row, now) -> bool` built by `schedule.py` — `every(timedelta)` for the interval jobs, `daily_at(time)` for the clock-time jobs. `daily_at` computes today's moment as `datetime.combine(now.astimezone(tz).date(), at, tzinfo=tz)` and compares in UTC (no arithmetic on zone-aware local times); it is due when that moment has passed, the last run was before it, **and it is not later than a cut-off** — `daily_at(time, latest=…)`. Two jobs use it: `operator_digest` at `operations.digest_time` (07:00, latest 10:00 — a morning mail at 22:00 helps nobody) and **`backup` at `operations.backup_time` (03:30, latest 06:00)** — the worker runs one thing at a time, so a backup delays whatever is due behind it by its runtime; it belongs in the quiet hours, not at whatever time a restart happened. A missed run waits for the next day; the backup check at Healthchecks.io then reports the gap. Tested across both DST changes and at the cut-off.

If the platform is down from 07:00 to 10:00 the mail does not come that day — the independent channels of §3 have already spoken.

## 7. Deploys, the start script, the emergency stop

### 7.1 Deploys are safe at any time

- **Render deploys only after CI has passed:** `autoDeployTrigger: checksPass` on the web service (`render.yaml` has `commit` today; the field exists — verify the value `checksPass` at M9). A failing test never reaches production.
- **During the switch-over** Render starts the new container, waits for `/health`, then sends the old one SIGTERM and waits up to `maxShutdownDelaySeconds` (300) before SIGKILL. The old worker finishes the mail it is on and stops before the next claim (SES plan §5 step 2.3); a summary call finishes (≤ 120 s); the new worker takes over at the next tick, holding the leader lock (lean-platform plan §4). Result: the rest of a list goes out a minute or two later; nobody gets a mail twice.
- **Migrations survive the overlap** (§7.4).
- **The quiet window** — shown on the console and in the daily mail for whoever prefers to deploy when nothing is going on: not quiet while a mailing is `sending` and due (`next_attempt_at` empty or within the next 20 minutes — a mailing parked for the operator does not block), while a preview or a send is due within the next **20 minutes** (`operations.deploy_margin_minutes`), or within 30 minutes after the backup started; otherwise quiet until the next such moment. One pure function, `quiet_window(now, state)`, in `schedule.py`.
- **Changing an environment variable in the Render dashboard redeploys at once**, without CI — harmless for the same reasons; `operations.md` says so.

A deploy workflow that waits for the quiet window before it deploys was designed and dropped (2026-09-27): it needed three secrets and a job polling for hours, could deploy a commit that had not passed CI, and bought only the minute of delay above. Backlog, with its trigger.

### 7.2 The start script (one container, two processes — supervised)

`ops/start.sh`, shipped in M6b (lean-platform plan §3) exactly as below; M6c adds only the `worker.restarted` incident that `WORKER_RESTARTED_AFTER` enables. Verified in the project's image (bash 5.2): SIGTERM reaches the web and every restarted worker; a killed web process ends the container.

```bash
#!/usr/bin/env bash
# Web and worker in one container (MVP plan §15.2). A crashed worker is restarted with
# back-off; if the web process ends, the container ends and Render restarts both.
set -uo pipefail

stopping=0
trap 'stopping=1; kill -TERM $(jobs -pr) 2>/dev/null' TERM INT

uvicorn app.web.server:create_app --factory --host 0.0.0.0 --port "$PORT" \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" &
web_pid=$!
python -m app.worker &
worker_started=$SECONDS
delay=10

status=0
while [ "$stopping" = 0 ]; do
  wait -n -p ended; status=$?                       # bash ≥ 5.1: -p names the child that ended
  [ "$stopping" = 1 ] && break
  [ "${ended:-}" = "$web_pid" ] && break            # the web ended: end the container
  (( SECONDS - worker_started > 600 )) && delay=10  # it ran for 10 minutes: start the back-off afresh
  echo '{"event": "worker.exited", "status": '"$status"', "restart_in_s": '"$delay"'}'
  sleep "$delay" & wait $!                          # interruptible by SIGTERM
  delay=$(( delay < 150 ? delay * 2 : 300 ))
  if [ "$stopping" = 0 ]; then
    WORKER_RESTARTED_AFTER="$status" python -m app.worker &
    worker_started=$SECONDS
  fi
done
kill -TERM $(jobs -pr) 2>/dev/null
wait
exit "$status"
```

The `if … fi` (not `… && python … &`) matters: the short form backgrounds a subshell, and the worker behind it would never receive SIGTERM. Back-off 10 → 20 → 40 → 80 → 160 → 300 s keeps a worker that crashes at start from flooding the logs and Sentry's free quota. **Check at M6b:** PID 1 in the container is this script (`cat /proc/1/cmdline` during the memory run) — a shell in between that does not `exec` would swallow SIGTERM.

### 7.3 The emergency stop

A switch in the database, not an environment variable: an environment change makes Render redeploy — minutes during which a wrong mail keeps going out, and possibly a deploy of a commit that failed CI.

- **Storage:** a one-row table `operator_switches` (`sending_paused` bool, `changed_at`, `changed_via` — `console` or `cli`), created by the M6c migration with `sending_paused = false`.
- **Effect:** `due_mailings` skips every mailing while it is set; the send loop reads it **before every claim** (one indexed single-row read per mail — negligible next to the SMTP exchange) and stops like on SIGTERM: no transition, no attempt counted. The preview step reads it before sending too. Summaries, sign-ups, confirm mails and everything else carry on.
- **Control:** the console button (a confirmation page, then a same-origin POST) and `uv run app pause-sending on|off`. The console shows a red banner; the daily mail says so first; switching it on or off is an incident of level `warning` (who, when).
- **After the stop:** for each mailing in `sending` the console offers **"fortsetzen"** (it resumes when the stop is released) or **"Rest abbrechen"** (`sending → cancelled`, §5). Mailings that had not started are unaffected and go out when the stop is released — unless the wait has taken them past the 12-hour rule: **the worker applies that rule to every mailing that has not started sending before it does any mailing work** (MVP plan §9.4 — after a stop, an outage or a long parking alike), so nothing starts days late; those end with the honest notice. A paused mailing in `sending` waits for the owner's choice.
- Tests: the stop halts a running send before the next claim; a paused mailing resumes on release; "Rest abbrechen" leaves the sent recipients counted and the rest unsent; a mailing that had not started and is past its 12 hours ends on release instead of going out; a paused `sending` mailing is never ended by the clock.

### 7.4 Migrations that survive the overlap

During a deploy the new container's `preDeployCommand` migrates the database **while the old container still runs** against it. **Rule** (MVP plan §3.1): every migration is backward compatible with the code of the previous release — add columns nullable or with a default, add tables, never rename or drop in the same release; a rename or drop is a second migration in a later deploy (expand → deploy → contract). The review of every migration checks it.

## 8. Honest limits of the cheap setup

- **No high availability.** One instance: during a crash, a restart or a deploy switch-over the site can be unreachable for seconds to a minute (a fan's sign-up then shows an error; he tries again). Redundancy — two instances and a high-availability database — costs from ≈ €60 a month. Not worth it before revenue; backlog, with the trigger "sign-ups lost to downtime become measurable".
- **Logs live 7 days** on Render's Hobby workspace. The incident list and the database views keep what matters for 180 days; the full log text beyond a week would need a log stream (backlog).
- **Point-in-time recovery covers 3 days**; older states come from the nightly B2 backup (loss up to 24 hours).
- **The operator mail depends on our own mail path** — which is why §3's channels exist.

## 9. Milestone M6c

### M6c — Operations: failure handling, operator console, daily mail (≈ 4 sessions) — *added 2026-09-27*
Test-first; the quiet-window rule, the incident de-duplication, the downtime detection, the console's access check and the CSRF check get mutation probes.
- [ ] Migration: `job_runs.last_ok_at`, `last_error_at`, `last_error`; table `operator_events`. Periodic jobs record their outcome; the `worker` and `ses.feedback` rows (§4.1). The migration follows §7.4.
- [ ] `IncidentRecorder` as a `Services` field + fake; de-duplication, refs, address scrubbing, retention in the cleanup; the call sites of §4.2; downtime and restart detection; the operator mail with its 30-minute back-off (§4.3).
- [ ] `app/ops/status.py` — the one query module; `app/jobs/schedule.py` gains `every`, `daily_at`, the next-event and duration functions and `quiet_window` (pure, stepped-clock tests); `run_periodic_jobs` uses `due(row, now)`; `backup` moves to 03:30.
- [ ] `cli status` (moved here from M7) printing the same figures as the console.
- [ ] Console `/betrieb`, `/betrieb/zeitplan`, `/betrieb/probleme` with the "erledigt" POST (§5); `uv run app operator-password`.
- [ ] The daily operator mail (§6); the emergency stop with `operator_switches`, the console's mailing actions ("Stoppen", "fortsetzen", "Rest abbrechen", the new `sending → cancelled` transition) and their CLI commands (§5, §7.3); the feedback-silence rule (§2).
- [ ] `render.yaml`: `autoDeployTrigger: checksPass`.
- [ ] Settings and secrets: `OPERATOR_EMAIL`, `OPERATOR_PASSWORD_HASH` (`Secrets`, `.env.example`, `render.yaml` `sync: false`); `[operations]` `digest_time = "07:00"`, `backup_time = "03:30"`, `deploy_margin_minutes = 20` — each with its comment. The thresholds that never change (merge 6 h, retention 180 days, traffic-light minutes, storage size) are module constants.
- [ ] Log events in `app/log.py`: `worker.downtime`, `worker.restarted`, `operator.login_failed`, `operator.notified`, `operator.notify_failed`, `operator.digest_sent`, `incident.record_failed`, `mailing.sending_paused` (`worker.exited` is the start script's own line).
- [ ] `operations.md`: the console and its password, the alert channels and who receives them, the quarterly channel drill, the emergency stop, "changing an env var redeploys", the failure table of §2 as the incident cheatsheet; the migration rule in ARCHITECTURE.
- [ ] Tests: every row of §2 that can be simulated (worker killed → `worker.restarted`, web untouched; stop mid-send → resume, nobody twice; database gone for a tick → downtime incident with its duration; parked rows show with their fix); the console refuses without or with a wrong password, answers 401 with `WWW-Authenticate`, never throttles a signed-in owner, rejects a cross-site "erledigt"; incident merging per kind and never into an acknowledged incident; address scrubbing; the operator mail once per incident and its back-off; the digest's content for a seeded day; `daily_at` across DST; the emergency stop halts a send before its next claim and the 12-hour rule is applied on release.
- **Done when:** on the local stack, the console shows correct traffic lights, a seven-day schedule matching the seeded mailings to the minute, and the quiet window; killing the worker process shows the restart incident without interrupting the web; a seeded `NeedsOperator` produces exactly one incident and one operator mail in Mailpit; the daily mail arrives in Mailpit with today's plan; the emergency stop pressed in the console halts a running send before the next recipient and shows the banner, and "Rest abbrechen" ends it with the right counts. The live checks of the channels happen in M9.
- **Status: planned, not started, 2026-09-27.**
