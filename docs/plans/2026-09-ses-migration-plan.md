# Mail Plan — Amazon SES replaces Resend (milestone M6a)

> **Status:** planned, not started · **Date:** 2026-09-27, revised the same day after two adversarial reviews against the code · **Part of the MVP.** This plan is one step of the MVP plan (`2026-09-mvp-implementation-plan.md`, §17: milestone **M6a**, the next milestone to build). It lives in its own file because it is a self-contained topic; the MVP plan only points here. The conventions of the MVP plan apply unchanged: §3 principles (including **"a removal is complete"**), §14 testing (mutation probes for rules that guard money, privacy or reputation), §16 documentation, "*Changed YYYY-MM-DD*" for every deviation, `docs/backlog.md` for everything deferred.
>
> **Why it exists.** Resend costs too much to send newsletters and still earn money with the platform (owner, 2026-09-27): ≈ $0.90 per 1,000 mails at its overage price and a $20 plan from the first list above 100 fans, against ≈ $0.11 per 1,000 and no fixed fee at Amazon SES. **Owner decision: Resend disappears completely — from code, configuration, tests and current documentation. No dead code, no leftover names; the code must be at least as clean and small afterwards as before.**
>
> **Progress:** M6a `[ ]` — tick the boxes in §12 as work completes.

## Table of contents

1. [What was decided, and why](#1-what-was-decided-and-why)
2. [Listmonk — evaluated and rejected](#2-listmonk--evaluated-and-rejected)
3. [Feature parity with Resend — what stays, what changes, the compromises](#3-feature-parity-with-resend--what-stays-what-changes-the-compromises)
4. [Sending over SMTP](#4-sending-over-smtp)
5. [Never twice, without an idempotency key](#5-never-twice-without-an-idempotency-key)
6. [Feedback from SES: bounces, complaints, delivery status](#6-feedback-from-ses-bounces-complaints-delivery-status)
7. [Configuration](#7-configuration)
8. [Local development: Mailpit](#8-local-development-mailpit)
9. [AWS setup (operator, once)](#9-aws-setup-operator-once)
10. [Costs](#10-costs)
11. [The removal: every file, every line of Resend](#11-the-removal-every-file-every-line-of-resend)
12. [Milestone M6a](#12-milestone-m6a)
13. [Verified facts](#13-verified-facts)
14. [Risks](#14-risks)
15. [Questions — decided and open](#15-questions--decided-and-open)

---

## 1. What was decided, and why

Decisions taken with the owner on 2026-09-27:

1. **Amazon SES in `eu-central-1` (Frankfurt) is the only mail provider**, for fan newsletters and every single mail (confirm, magic link, creator preview, creator notice, later the contact relay).
2. **The app talks to SES directly over SMTP** with the standard library (`smtplib`, `email.message`, `email.headerregistry`). No SDK, no new Python dependency, no intermediary service.
3. **Listmonk is not used** (§2). The saving comes entirely from SES; Listmonk would add a service, cost and risk while weakening guarantees the platform already has.
4. **"Exactly once" becomes "never twice".** SES has no idempotency key; if the process dies inside one SMTP exchange, nobody can know whether that one recipient got the mail. **Owner decision: rather no double mail** — that recipient is not sent again; the case is logged and countable. Everything else about the send guarantee is unchanged.
5. **Bounces and complaints arrive as signed SNS notifications** at `POST /webhooks/ses` and feed the existing, unchanged blocking rule (`block_addresses`).
6. **Delivery status is visible per mail in our logs** (owner decision): SES also reports *delivered* and *delayed* per mail; the webhook logs them with mailing and delivery ids — the replacement for Resend's per-mail dashboard, without a new table.
7. **Local development sends into Mailpit**, a local SMTP catcher. The defaults point at it; only production configuration points at SES. A laptop can no longer mail a real person by accident.

**Why SMTP and not the SES HTTP API (v2 `SendEmail`):** the HTTP API needs AWS Signature V4 request signing — `boto3` (≈ 20 MB of dependencies for one call) or ≈ 40 lines of hand-written signing. SMTP is in the standard library, needs one username and one password, gives the same success signal (`250 Ok <message-id>`), talks to Mailpit locally unchanged, and makes a later switch of relay (§14) a configuration change. SMTP is how most of the industry's bulk senders talk to SES; it is not the "old" path, it is the portable one.

## 2. Listmonk — evaluated and rejected

Checked against the Listmonk source (v6.2.0 of 2026-06-26; master `5e23f60` of 2026-09-24) and its documentation:

| Need of the platform | Listmonk v6.2.0 | Source |
|---|---|---|
| Know whether a mail went out | `POST /api/tx` queues the mail **in memory** and answers `{"data": true}` at once; an SMTP failure afterwards is only logged and the mail dropped. The maintainer: "there's no mechanism that records the states of transactional e-mails". | `cmd/tx.go`, `internal/manager/manager.go`, issue #2377 |
| Never send twice, never lose silently | No idempotency key (request #2596 closed as stale). Campaigns advance `last_subscriber_id` *before* sending a batch, so a crash loses the rest of that batch; open reports of campaigns finishing with fewer mails sent than planned (#2860, #2708). | `queries/campaigns.sql`, `internal/manager/pipe.go` |
| Confirm mail in each creator's branding | One global opt-in template for all lists. | `static/email-templates/subscriber-optin.html`, issue #3044 |
| Blocked addresses never mailed again | `/api/tx` does not check the blocklist. | `cmd/tx.go` |
| Safe subjects (video titles are untrusted text) | A per-request `subject`/`altbody` containing `{{ … }}` is executed as a Go template. | `models/messages.go` |
| Learn about bounces | No outgoing webhooks in any version; bounces of recipients who are not Listmonk subscribers are lost (`bounces.subscriber_id NOT NULL`). | source grep, `schema.sql`, issue #206 |
| Small attack surface | Public admin UI; six security advisories in two years, two critical (CVE-2025-58430, CVE-2025-49136); open issue #3195: `--install --idempotent` can wipe a populated database on a connection blip. | GitHub security advisories |
| Cost | One more always-on service (≈ $7/month) plus its database. | — |

What Listmonk does well — campaign fan-out with per-list one-click unsubscribe, a UI for lists, SES bounce ingestion — the platform already has, hardened and tested (M5, M6). **Decision: not used.**

## 3. Feature parity with Resend — what stays, what changes, the compromises

| What the platform did with Resend | With SES | Note |
|---|---|---|
| Confirm mail after the HTTP answer, brake released on failure | unchanged | `SmtpClient.send` |
| Magic-link mail after the answer, link withdrawn on failure | unchanged | |
| Creator preview with stop/postpone links | unchanged | a crash between SES's `250` and the status commit can send it twice (§5, accepted — it costs the creator a glance) |
| Creator notices | unchanged | at-least-once, like the preview (§5) |
| Newsletter to all confirmed fans, resumable after a crash | unchanged, **never twice**; at worst one fan per interrupted run misses it (§5) | the compromise the owner chose |
| `List-Unsubscribe` + one-click `List-Unsubscribe-Post` | unchanged — SES passes our headers through | DKIM coverage checked live in M9 |
| Bounce → permanent block, complaint → permanent block, provider suppression mirrored | unchanged rule; SNS instead of Svix | §6 |
| Per-mail status in the provider's dashboard | **per-mail status in our logs** (delivered, delayed, bounced, complained) | §6; the SES console shows totals only |
| Test addresses (`bounced@resend.dev` …) | SES mailbox simulator (`bounce@`, `complaint@`, `success@`, `suppressionlist@simulator.amazonses.com`) | locally: Mailpit |
| Operator errors for a wrong key / exhausted plan (`NeedsOperator`) | unchanged, mapped from SMTP reply codes | §4.4 |
| Sending without approval | **SES sandbox** until AWS grants production access (needs the live website) | M9; development never needs it |
| Gmail spam complaints reported | **not reported** — Gmail sends SES no complaint data | Gmail Postmaster Tools (§9 step 11) |

## 4. Sending over SMTP

### 4.1 The client (`app/delivery/email_client.py`, rewritten)

```python
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "mailpit"})   # STARTTLS off only for these

class SmtpClient:                      # plain class, no Protocol (MVP plan §3)
    def __init__(self, host: str, port: int, username: str, password: str,
                 max_send_rate_per_second: float,
                 connect=smtplib.SMTP, clock=time.monotonic, sleep=time.sleep): ...
    def send(self, mail: OutgoingEmail) -> str: ...        # one mail, own connection
    def session(self) -> ContextManager[SmtpSession]: ...  # one connection for a page of fan mails

class SmtpSession:
    def wait_for_slot(self) -> None: ...                   # the rate spacing; the send loop calls it before the claim (§5)
    def send(self, mail: OutgoingEmail) -> str: ...        # does not wait again; raises DeliveryUncertain (§4.4)
```

- `connect`, `clock` and `sleep` are the test seams (a scripted fake connection that returns and raises what real `smtplib` does; a fake clock) — nothing is patched (MVP plan §14).
- **STARTTLS is derived, not configured:** on for every host outside `LOCAL_HOSTS`, and then mandatory (a server that does not offer it → `NeedsOperator`), always as `starttls(context=ssl.create_default_context())` — without an explicit context, Python 3.13's `smtplib` does **not** verify the server's certificate and a man in the middle could read the credentials. A test asserts the context's `verify_mode == ssl.CERT_REQUIRED` and `check_hostname`.
- **Rate spacing lives on the client instance** and applies to `send` and `session` alike: before each mail, wait until `1 / max_send_rate_per_second` has passed since the previous one (`clock`, `sleep`). `SmtpClient.send` waits internally; in a session the fan-mail loop calls `SmtpSession.wait_for_slot()` itself *before* it claims the recipient (§5 step 2.2), and `SmtpSession.send` does not wait again — otherwise a stop or crash during the wait would leave a claimed recipient that no SMTP exchange ever touched. SES's send rate is a hard account limit (sandbox: 1/s); staying under it is cheaper than handling `454 Throttling`. `cli demo-mails --send-to` (nine single sends) is covered by the same spacing. The web process sends confirm and magic-link mails from several threads at once (FastAPI background tasks share a thread pool), so the spacing state is guarded by a `threading.Lock`. **The account's rate is shared by all processes** (web and worker run side by side): `max_send_rate_per_second` is set to about 80 % of the account's rate (§9 step 10), leaving room for the web process's few single mails; a `454` rate throttle that still happens is a temporary error (§4.4) — the worker retries, a fan simply submits again.
- **Timeouts:** 30 s for connect and commands; **120 s for the final reply after the message body** (`sock.settimeout(120)` just before `data()`) — RFC 5321 allows the server 10 minutes there, and every early timeout becomes an uncertain delivery.
- **Connection handling:** never `with smtplib.SMTP()` (its `__exit__` raises on a QUIT other than 221 and masks the real error): `quit()` after success, `close()` in `finally`, errors there swallowed. No explicit `ehlo()` — `starttls`, `login` and `mail` call `ehlo_or_helo_if_needed`. No `rset()` — a failed mail ends the run (§5), the session is discarded.

### 4.2 The message

`OutgoingEmail` changes (in `app/delivery/render.py`): `from_` (a formatted string) becomes **`from_name` + `from_address`**; `idempotency_key` is deleted; `sender()` returns both parts. Reason: a creator called `Müller, Hans` produced `From: Müller, Hans via Klartext <…>`, which parses as two addresses (checked on Python 3.13) — SES answers `5xx` and the whole mailing fails; and `mail()` needs the bare address anyway.

Built with `email.message.EmailMessage(policy=email.policy.SMTP)`, **before** any claim is written (§5):

- `From` via `email.headerregistry.Address(display_name=mail.from_name, addr_spec=mail.from_address)` — correct quoting of `,`, `"`, `<` and non-ASCII (test with all four);
- `To`, `Reply-To`, `Subject`, `Date` (`email.utils.formatdate()`), `List-Unsubscribe` and `List-Unsubscribe-Post` (fan mails only, as today), `X-SES-MESSAGE-TAGS` (§4.3); no `Message-ID` (SES sets its own);
- `set_content(text, cte="quoted-printable")`, then `add_alternative(html, subtype="html", cte="quoted-printable")` → `multipart/alternative`, 7-bit clean (an `8bit` body without `BODY=8BITMIME` risks a DKIM failure after conversion by a relay);
- a header value containing CR or LF raises **`ValueError` on assignment** (checked on Python 3.13) — mapped to `EmailError`; header injection through a creator name or a video title is impossible by construction, and a test pins it.

### 4.3 Tags

`OutgoingEmail.tags` stays and is written as `X-SES-MESSAGE-TAGS: kind=summary, mailing=12, delivery=345` (fan mails carry `mailing` and `delivery`; other mails only `kind`). SES returns them with every event (§6), which is how a log line about a bounce or a delivery names its mailing. Every value is a code constant or an integer id, so no validation code is written (one comment says why).

### 4.4 What each SMTP outcome means

Facts from the Python 3.13 source: `mail()` and `rcpt()` **return** `(code, message)` and do not raise on a refusal; `data()` raises `SMTPDataError` only when DATA itself is refused (before `354`) and **returns** the final reply after the body; any `OSError`/timeout during a read or write surfaces as `SMTPServerDisconnected`.

| Where / what | Mail sent? | Becomes | Why |
|---|---|---|---|
| `data()` returns `250` | yes | the message id from `250 Ok <id>` | |
| connect fails (`OSError`, `socket.gaierror`, `SMTPConnectError`, `ssl.SSLError`), or `SMTPServerDisconnected` before `data()` | no | `EmailTemporaryError` | the body never left |
| `starttls()` not offered (`SMTPNotSupportedError`) | no | `NeedsOperator` | a relay without TLS is misconfigured |
| `535` (`SMTPAuthenticationError`), `530`, any `554` | no | `NeedsOperator("Amazon SES", <SES's own words>, "check SMTP_USERNAME/SMTP_PASSWORD (per region, eu-central-1), the IAM policy of the SMTP user, whether the sender identity is verified, and whether the account is still in the sandbox")` | recognised by **status**, not wording — the codebase's rule (`tests/unit/test_operator_errors.py`) |
| `454` whose text says `Daily message quota exceeded` | no | `QuotaExhausted` (a `NeedsOperator`) | **the one wording match**, documented as the exception: the same `454` otherwise means "slow down" |
| any other `4xx` (incl. `421`, `451`, `454` rate) returned by `mail`/`rcpt`/`data`, or `SMTPDataError` with a `4xx` | no | `EmailTemporaryError` | the retry ladder takes over |
| any other `5xx` returned, or `SMTPDataError` with a `5xx` | no | `EmailError` (permanent), logged `email.refused` at ERROR with the reply | |
| `SMTPServerDisconnected` or `OSError` **raised by the `data()` call** | **unknown** | `DeliveryUncertain` — deliberately *not* a `TemporaryError` | the body may have been accepted; conservatively also when the drop happened before `354` |

**Single mails handle uncertainty themselves:** `SmtpClient.send()` catches `DeliveryUncertain`, logs `email.uncertain` at ERROR (with the `kind` tag, never the address), and returns `""` — treated as sent. The brake is not released, the magic link not withdrawn, the preview counts as sent, the confirm mail counts toward M7a's confirm-mail counter (conservative for the cap). Callers (`subscriptions.py`, `web/routes/creator.py`, `mailing.send_preview`, `jobs/steps.notify_creator`, `cli.py`) therefore **need no change** for it. Only `SmtpSession.send` raises `DeliveryUncertain`, because only the fan-mail loop has a ledger to record it in.

`# ponytail: any 5xx stops the whole mailing until the operator acts; SES rejects nearly nothing per recipient (suppressed addresses are accepted and reported as bounces), add per-address handling only if it happens once.`

## 5. Never twice, without an idempotency key

Resend recognised a repeated batch by its key for 24 hours. SES has no such key (§13): the same crash would send the repeated part again. The design therefore records the attempt **before** the mail is handed over.

**New column** `deliveries.attempted_at timestamptz NULL`. A delivery is:

| `attempted_at` | `sent_at` | State |
|---|---|---|
| null | null | **pending** — will be sent |
| set | set | **sent** |
| set | null | **uncertain** — a send was started and its outcome is unknown; never sent again |

**Migration** (hand-written — `alembic check` does not compare the partial index's `WHERE`, so the model test would not notice a forgotten index): add the column; `UPDATE deliveries SET attempted_at = sent_at`; rebuild `ix_deliveries_pending` as `(mailing_id, id) WHERE attempted_at IS NULL`. The downgrade drops the column and restores the old index; its docstring warns that uncertain rows become pending again and could be sent twice.

**Before the send starts — the daily quota.** SES's quota counts recipients over a rolling 24 hours. `start_sending` (the `preview_sent → sending` transition) first compares the snapshot's recipient count with the quota left: `email.daily_quota` (the approved quota, set in M9 — §9 step 10; `0` = not checked, the default locally and in the sandbox) minus every mail the platform sent in the last 24 hours (fan mails from `deliveries.sent_at`; previews, confirm and magic-link mails from their own timestamps; notices are too few to matter). If it does not fit, the send does not start: `NeedsOperator("Amazon SES", "the mailing needs N mails, M are left in the 24-hour quota", "request a higher quota (operations.md) or wait for the window to free up")` — parked, never started half-way. The operator console's schedule shows the same arithmetic days ahead ("Quote reicht nicht", operations plan §5) and the daily mail warns, so a quota increase can be requested before the day.

**The loop** — `send_batches(session, mailing, appearance, creator, now, settings, should_stop)`, inside the unchanged advisory lock and snapshot (`BATCH_SIZE = 100` becomes a local constant of `mailing.py`: the page size of pending rows read at once):

1. Read the next page: up to 100 deliveries with `attempted_at IS NULL`, subscriber not blocked (re-read per page, as today), `ORDER BY id`. Open one SMTP session for the page.
2. For each delivery, in this order:
   1. **Render and build** the message bytes (from `render_snapshot` — payload freeze unchanged). A template or header error raises here, *before* anything is recorded.
   2. **Wait** for the rate spacing (§4.1).
   3. **Stop check:** if `should_stop()` (the worker received SIGTERM — a deploy), return without a transition and without counting an attempt; the mailing stays `sending` and resumes at the next start. This keeps every deploy from producing an uncertain fan.
   4. **Claim:** `UPDATE deliveries SET attempted_at = :now WHERE id = :id AND attempted_at IS NULL`, **commit**. Rowcount 0 → skip it.
   5. **Send.**
   6. **Success:** `sent_at = :now` and the mailing's `attempts` reset (progress, MVP plan §9.4) in **one commit**.
   7. **`DeliveryUncertain`:** keep the claim; log `email.uncertain` at ERROR (`mailing_id` is already bound, plus `delivery_id`); end the run with a `TemporaryError`. If the mailing now has more than **3** uncertain deliveries, raise `NeedsOperator("Amazon SES", "the relay lost answers to N mails of mailing M", "check SES and the network; see operations.md → uncertain deliveries")` instead — a relay that keeps losing answers must not quietly thin out a list.
   8. **Any other exception raised by the send itself** (every "no" row of §4.4): `session.rollback()` first — after a caught database error, PostgreSQL leaves the session unable to write and the next commit silently does nothing — then release the claim (`attempted_at = NULL`) in a fresh transaction, commit, re-raise → the retry ladder or `NeedsOperator` handles it as today.
   9. **Once `send` has returned, nothing releases the claim.** An exception in step 6 or later (the commit fails, the connection drops) rolls back and re-raises with the row left claimed — uncertain, never twice.
3. After each page: log `mailing.batch_sent` (size, first delivery id); the session is closed (`quit`, then `close`). No pending row left → `sending → sent`, `recipient_count` = rows with `sent_at` (uncertain ones are not counted, and therefore not billed — the error is in the creator's favour), committed inside the lock as today.

`should_stop` is passed down, not imported. The real signatures today: `steps.send(session, mailing_id, now)`, dispatched by the worker through `MAILING_STEPS[step](session, mailing_id, now)`. They become `steps.send(session, mailing_id, now, should_stop=lambda: False)` → `mailing.send_batches(…, should_stop)`; `worker.run_due_mailings` calls `steps.send(session, mailing_id, now, should_stop=lambda: _stopping)` for the `send` step (the dict entry becomes a `functools.partial`, or `send` is called outside the dict — the smaller diff wins); tests pass `lambda: False` or a switch. **The worker also stops iterating** once `_stopping` is set: `run_due_steps`, `run_due_mailings` and `run_periodic_jobs` check it before each row or job, so a SIGTERM never starts another 120-second summary call inside the shutdown delay.

**What a crash does now:** before step 4 — nothing happened; between 4 and 6 — that one delivery is uncertain and skipped on resume; after 6 — recorded. A failed commit in step 6 leaves the row claimed — uncertain, never twice. **The guarantee: no fan ever receives a mailing twice; after a crash inside one SMTP exchange, one fan may not receive it at all, and the operator can see it.** (SES itself says it may on rare occasions accept a mail although the request returned an error, §13. Such a mail arrives once and is recorded as not sent — it cannot duplicate.)

**Visibility of uncertain deliveries:** the ERROR log line (Sentry picks it up). `operations.md` carries the query `SELECT mailing_id, count(*) FROM deliveries WHERE attempted_at IS NOT NULL AND sent_at IS NULL GROUP BY 1`. M6c's status module shows the same count per open or recent mailing in `cli status`, the operator console and the daily operator mail (operations plan §5, §6); each uncertain delivery is also an incident. **If a fan asks:** the operator sends that fan the summary page link (`/s/<view_token>`) by hand — no re-send machinery (backlog entry with trigger).

**A long send and the worker tick:** a tick now lasts as long as the send: ≈ 12 minutes for 10,000 recipients at 14/s. Nothing else waits on it that matters (the pipeline steps of other rows run in the next tick); the worker heartbeat's grace covers it (MVP plan §15.2).

**Preview and notices** have no ledger. A crash between SES's `250` and the status commit re-sends the preview on the retry — identical, because `_hold_the_send_time` commits the pushed send time before the first attempt. Its docstring gets the real reason: the `sentiment_ready → preview_sent` transition does not write `send_at`, so the time the preview announces must be on the row before the mail leaves. Notices are sent from inside steps (`steps.py`, three call sites), before the step commits; a failed commit repeats the notice on the retry. **Both are at-least-once, accepted:** the owner's "never twice" decision concerns fans. `_preview_key` is deleted; `render_notice_mail` loses its `appearance_id` parameter (it only built the key) and its callers lose the argument (`steps.py` two sites, the worker's `_failure_notice` context).

**Cost:** two commits per recipient instead of one per hundred — irrelevant next to SES's send rate (14/s after approval).

## 6. Feedback from SES: bounces, complaints, delivery status

### 6.1 Flow

The configuration set `platform-default` (the identity's default, so no header is needed) publishes **Bounce, Complaint, Delivery, DeliveryDelay and Reject** events to the SNS topic `ses-feedback` (standard topic, `SignatureVersion = 2`, same region). The topic has one HTTPS subscription: `https://<domain>/webhooks/ses`.

### 6.2 `POST /webhooks/ses` (`app/web/routes/webhooks.py`, rewritten; verification in a new `app/delivery/sns.py`)

The route stays `async` (raw body) and runs verification and handling through `run_in_threadpool`, because fetching a certificate is a blocking call that must not stall other requests.

1. Read the raw body (the 64 KiB limit applies). Not JSON, or `Type` not one of `SubscriptionConfirmation` / `Notification` / `UnsubscribeConfirmation` → **401**.
2. **The topic.** SNS retries only `5xx` and `429`; every other answer drops the message for good (checked 2026-09-27 in the SNS documentation). So: an **empty** `SES_FEEDBACK_TOPIC_ARN` — our own misconfiguration — answers **503** and records the incident "SES-Rückmeldungen nicht konfiguriert" (SNS retries, nothing is lost while the owner fixes it); a `TopicArn` **different** from ours with a valid signature answers **403** and records an incident naming the foreign ARN (someone else's topic, or a typo in ours — the owner decides). Nothing is ever *accepted* without the setting (the 2026-09-18 lesson).
3. **Signature** (`sns.verify(message, certificates) -> bool`): `SignatureVersion` must be `"2"` (RSA/SHA-256; version 1/SHA1 is refused); `SigningCertURL` must be `https`, its host exactly `sns.<region>.amazonaws.com` with the region **taken from the topic ARN** (`arn:aws:sns:<region>:<account>:<name>` — no second setting that could disagree), its path ending in `.pem`; the string to sign is the fixed, byte-ordered key list of the message type, each as `key\nvalue\n` — notifications: `Message`, `MessageId`, `Subject` (only if present), `Timestamp`, `TopicArn`, `Type`; confirmations: `Message`, `MessageId`, `SubscribeURL`, `Timestamp`, `Token`, `TopicArn`, `Type`; the Base64 signature is verified with `cryptography` (already a dependency) as RSA PKCS#1 v1.5 over SHA-256. Any failure → **401** (not retried by SNS — a forged message should not be), logged `webhook.ses` with `topic_ok` and `signature_ok`. A signing certificate that cannot be fetched (network) answers **503**, so SNS retries.
4. `SubscriptionConfirmation` → log `webhook.ses_subscription` at WARNING **with the `SubscribeURL`**, answer 200. The operator confirms the subscription once in the SNS console (§9 step 6) — no outgoing GET from the web process, no test seam for it, fewer lines.
5. `Notification` → parse `Message` (a JSON string, event-publishing format, `eventType` field), read the tags (`mail.tags` — each value arrives as a list; take the first element):
   - `Bounce` with `bounce.bounceType == "Permanent"` (any subtype, incl. `OnAccountSuppressionList`) → `block_addresses([r.emailAddress …], BOUNCE)`, log `email.bounced`;
   - `Complaint` → `block_addresses([…], COMPLAINT)`, log `email.complained`;
   - `Bounce` `Transient`/`Undetermined` → log `email.bounced` with `permanent=false`, nothing blocked;
   - `Delivery` → log `email.delivered` at INFO; `DeliveryDelay` → `email.delayed` at WARNING; `Reject` → `email.rejected` at ERROR — each with `kind`, `mailing`, `delivery` from the tags and the SES message id, **never the address**;
   - anything else → logged, ignored.
6. Every signed request of our topic gets **200**, including shapes we do not understand; a database error while blocking answers **503** (retried). No dedup table: the writes are set-to-value and the logs are logs; a replayed notification changes nothing that matters, and a replayed genuine bounce can only block an address that did bounce — no timestamp window needed.

**"Did the mail to X arrive?"** — the operator looks up the delivery id (`deliveries` joined to the subscriber's address) and searches the logs for `delivery=<id>`: `email.delivered`, `email.delayed`, `email.bounced`. Render keeps logs for a limited time (to verify for the Hobby workspace, MVP plan §15.2) — enough for "last week's mail"; a longer history is a backlog item with a trigger.

**Load:** one notification per delivered mail. At SES's 14/s the webhook receives ≈ 14 requests per second during a send, each an RSA verification and a log line — well within the web process; SNS retries on its own if we are slow.

**Delivery policy and silence.** The topic gets an HTTP/S delivery policy with the most retries AWS allows (`numRetries` 50 within the 3,600-second limit), so an hour of trouble on our side loses nothing. And because SES reports a *Delivery* event for every mail, silence is itself a signal: when mails went out more than 2 hours ago and no feedback event has arrived since, the worker records the incident "keine SES-Rückmeldungen" (operations plan §2) — the one failure that would otherwise stay invisible: bounces no longer blocking anybody.

### 6.3 Services seam

`Services` gets `sns_certificates: SnsCertificates` — a plain class with `get(url) -> Certificate` that fetches (httpx, 5 s) and caches **on the instance** (no new process-global state — global caches leak between tests; `tests/conftest.py` resets the few that exist). Tests pass a fake returning a certificate generated with `cryptography` from one session-scoped test key pair, so every signature test runs real RSA verification. `# ponytail: the certificate cache is unbounded (one entry per signing URL); AWS rotates the certificate rarely — bound it if that changes.`

### 6.4 What SES itself suppresses

The account-level suppression list is on for `BOUNCE` and `COMPLAINT` (default for accounts created after 2019). A send to a suppressed address is accepted (`250`), not delivered, and reported as a `Permanent/OnAccountSuppressionList` bounce — which blocks the address on our side too. Our blocks stay permanent (owner decision 2026-09-18, carried over). **Unblocking a fan** (operator, rare): remove the address from the SES suppression list (SES console → Suppression list, or `aws sesv2 delete-suppressed-destination --email-address …`), then `UPDATE subscribers SET blocked_at = NULL, blocked_reason = NULL WHERE email = …` — never for a complaint. The app's SMTP user cannot touch the list (least privilege, unchanged principle).

**Gmail sends no complaint data to SES.** A Gmail user who clicks "spam" produces no event; only Gmail Postmaster Tools shows the rate (§9 step 11).

## 7. Configuration

`config/settings.toml`, `[email]` — **local defaults**, production values set by environment (the repo's pattern, like `LOGGING__JSON`):

```toml
smtp_host = "localhost"                 # the SMTP relay; Mailpit locally, SES in production (render.yaml: EMAIL__SMTP_HOST)
smtp_port = 1025                        # 1025 = Mailpit; production 587 (STARTTLS), 2587 if a network blocks 587
max_send_rate_per_second = 1.0          # per process; web and worker share the SES account's rate — about 80 % of it after approval (§9 step 10)
daily_quota = 0                         # the SES 24-hour quota; a send that would exceed it does not start (§5). 0 = not checked (local, sandbox)
```

`[web]`: `confirm_resend_minutes` → **`confirm_cooldown_minutes`** (value unchanged: 10; the env override becomes `WEB__CONFIRM_COOLDOWN_MINUTES`). Start-up validation: `max_send_rate_per_second > 0`. No `smtp_starttls` and no region setting: both are derived (§4.1, §6.2).

**Secrets** (env only, the flat `Secrets` model):

| Variable | Used by | Notes |
|---|---|---|
| `SMTP_USERNAME`, `SMTP_PASSWORD` | web and worker (one container in production), CLI | SES SMTP credentials of the IAM user `smtp-sender` (§9 step 7); region-bound. Empty locally — Mailpit needs none. |
| `SES_FEEDBACK_TOPIC_ARN` | web | `arn:aws:sns:eu-central-1:<account>:ses-feedback`; empty = every webhook call refused (401). |

**Removed:** `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, and **`SENDER_ADDRESS`** — it existed only for Resend's `onboarding@resend.dev` before domain verification. The derived `post@mail.<domain>` works against Mailpit, and SES can only send from a verified identity anyway. Deleted: `Secrets.sender_address` and the override inside the `sender_address` property (`config.py`), its `.env.example` lines, its README row, its tests (`test_config.py`).

**`config.secret_missing` at start:** `missing_secrets(settings, NEEDED_SECRETS)` takes a static dict today. It becomes `needed_secrets(settings) -> dict` in each of `worker.py` and `web/server.py`, which adds the `SMTP_*` names only when `settings.email.smtp_host` is not in `LOCAL_HOSTS`; the web process always adds `SES_FEEDBACK_TOPIC_ARN`.

## 8. Local development: Mailpit

`docker-compose.yml` gets:

```yaml
  mailpit:
    image: axllent/mailpit:v1.27        # pin the tag current at build time
    ports:
      - "1025:1025"                     # SMTP, also for host-run tests and CLI
      - "8025:8025"                     # inbox UI and HTTP API
```

`web` and `worker` get `EMAIL__SMTP_HOST: mailpit` and `depends_on: mailpit`. Host-run processes (`uv run app …`, `uv run pytest`) use the defaults `localhost:1025`, which reach the published port. Every mail the local stack sends lands in the Mailpit UI (`http://localhost:8025`) and nowhere else.

**One integration test sends through real `smtplib` into Mailpit** and reads the message back through Mailpit's HTTP API (`GET /api/v1/messages`, `GET /api/v1/message/{ID}`): `multipart/alternative` with both parts quoted-printable, `From` with a display name containing a comma, `Reply-To`, `List-Unsubscribe`, `List-Unsubscribe-Post`, `X-SES-MESSAGE-TAGS`. Locally it is skipped with a clear reason when Mailpit is not reachable; **with `CI` set it fails instead** (a skipped test proves nothing). `.github/workflows/ci.yml` gets a `mailpit` service container (ports `1025`, `8025`) next to Postgres; the round-trip test first polls `http://localhost:8025/readyz` for up to 10 seconds, so a slow container start is not a failure.

**Live test against SES before M9** (optional; needs the domain and §9 steps 1, 3, 7): SES sandbox, recipient = an address verified in the SES console (the owner's own). Set `EMAIL__SMTP_HOST=email-smtp.eu-central-1.amazonaws.com`, `EMAIL__SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD` in `.env` and run `uv run app demo-mails <slug> --send-to <verified address>`. The owner's work network may block outbound 587; try 2587, otherwise the check moves to the deployment.

## 9. AWS setup (operator, once)

Goes into `docs/runbooks/operations.md` word for word (**M6a creates this file** — `docs/runbooks/` does not exist yet; M7 extends it). Region **eu-central-1** throughout. **Timing:** steps 1–5, 7, 8 and 11 start as soon as the domain is decided (MVP plan §20 question 1 — the domain gate); DKIM verification can take up to 72 h. Steps 6 (the subscription part), 9 and 10 happen in M9, because they need the deployed site.

1. **Account:** an AWS account for the business; root user with MFA, never used day to day; an admin IAM user with MFA. **AWS Budgets:** monthly budget of €10 with an e-mail alert at 80 % — a leaked SMTP credential shows up here first.
2. **Pricing plan:** SES → Account dashboard. New accounts start on *Essentials* ($0.16 per 1,000); switch to **à-la-carte** ($0.10 per 1,000, no fixed fee). How the switch is offered in the console is unverified → note what it looked like in `operations.md`.
3. **Domain identity** `mail.<domain>`: Easy DKIM, RSA 2048 → three CNAMEs `{token}._domainkey.mail.<domain> → {token}.{SigningHostedZone}` (take the target from the console; it can differ per region). While in the sandbox, also verify the owner's own address as a recipient.
4. **Custom MAIL FROM** `bounce.mail.<domain>`: `MX 10 feedback-smtp.eu-central-1.amazonses.com` and `TXT "v=spf1 include:amazonses.com ~all"` (exactly one MX); behaviour on MX failure: *use default* (DKIM still aligns, so DMARC passes).
5. **DMARC** `_dmarc.<domain> TXT "v=DMARC1; p=none; rua=mailto:dmarc@<domain>"` — the report address must be **on the domain itself**: an address on another domain (e.g. Gmail) needs an authorisation record on that domain, which nobody can publish, and no report would arrive (RFC 7489 §7.1). Until the domain's mailbox exists (MVP plan §20 q8, first block of M9) publish `p=none` without `rua`. After four weeks of reports without unexpected failures: `p=quarantine` — but first check that every other sender on the apex (the registrar's mailbox sending as `hallo@<domain>`) signs with aligned DKIM, or quarantine hits the owner's own replies. Relaxed alignment (no `aspf=s`/`adkim=s`), because mail is sent from `mail.<domain>`.
6. **Feedback:** SNS topic `ses-feedback` (standard), attribute `SignatureVersion = 2`, access policy allowing `ses.amazonaws.com` to `sns:Publish` with `AWS:SourceAccount = <account>` and `AWS:SourceArn = <configuration-set ARN>`. **Configuration set** `platform-default`: reputation metrics on, **no Open/Click events** (no tracking — MVP plan §11), event destination SNS `ses-feedback` for *Bounce, Complaint, Delivery, DeliveryDelay, Reject*, suppression at account level; set it as the **default configuration set of the identity**. Set the topic's HTTP/S delivery policy (`numRetries` 50, `minDelayTarget` 20, `maxDelayTarget` 120, within the 3,600-second total — §6.2). *In M9, once the app is deployed:* create the HTTPS subscription `https://<domain>/webhooks/ses`, find the `webhook.ses_subscription` log line, open its `SubscribeURL` (or confirm in the SNS console) — the subscription must show *Confirmed*. Then switch **e-mail feedback forwarding off** for the identity; if the console refuses because no identity-level notification topic is set (unverified), set `ses-feedback` as the identity's bounce and complaint topic too.
7. **SMTP user:** IAM user `smtp-sender`, no console access, one inline policy: `ses:SendRawEmail` on `arn:aws:ses:eu-central-1:<account>:identity/mail.<domain>` **and** `arn:aws:ses:eu-central-1:<account>:configuration-set/platform-default` (SES may authorise the configuration set as a resource when one applies — unverified; listing it costs nothing), with condition `StringLike ses:FromAddress = *@mail.<domain>`. "Create SMTP credentials" → `SMTP_USERNAME`/`SMTP_PASSWORD`. A second user `smtp-sender-dev` for a live test from a laptop, deleted afterwards. **Test once:** a foreign From address must be refused with `554 Access denied` (unverified that the condition applies over SMTP). Rotation: create new credentials, set them on Render, delete the old ones.
8. **Alarms:** CloudWatch alarms on `AWS/SES Reputation.BounceRate ≥ 0.05` and `Reputation.ComplaintRate ≥ 0.001`, missing data *ignore*, action: SNS topic `ops-alerts` with an e-mail subscription to the owner.
9. **Production access** (M9, needs the live website): console → *Get set up* → *Request production access*; mail type **Marketing** (newsletters dominate); website URL; contact language English. AWS usually answers within 24 h and often asks follow-up questions. The prepared answer (English) goes into `operations.md`: *what we send* (per-creator summary newsletters after each new video, double-opt-in confirmations, login links); *how addresses are collected* (only on the creator's own sign-up page, double opt-in, no imported or bought lists); *volume and frequency* (one mail per new video per subscriber; the expected monthly count); *bounce and complaint handling* (SNS → automatic permanent block; account suppression list on); *unsubscribe* (one-click `List-Unsubscribe` + footer link on every mail); the sign-up and unsubscribe URLs.
10. **Quota** (M9): after approval read the daily quota and send rate from the account dashboard, set `EMAIL__MAX_SEND_RATE_PER_SECOND` to about 80 % of the rate and `EMAIL__DAILY_QUOTA` to the quota on Render (web and worker share the account's rate, §4.1; the quota check is §5), note both in `operations.md`. Increases through *Service Quotas* (quotas count recipients). Headroom is checked on the dashboard once a month (backlog: an automatic warning).
11. **Gmail Postmaster Tools:** add and verify `mail.<domain>` (a TXT record) — the only place Gmail spam complaints become visible.

Infrastructure as code for these steps is deferred (backlog, trigger: a second environment): done once, by hand, from this list.

## 10. Costs

Amazon SES, à-la-carte, eu-central-1 (checked 2026-09-27): **$0.10 per 1,000 mails** + **$0.12 per GB** of message data; at ≈ 50 KB per mail ≈ $0.006 per 1,000 → **≈ $0.11 per 1,000**, no fixed fee. SNS: one HTTPS notification per event; the first 100,000 deliveries a month are free and the rest cost ≈ $0.60 per million (unverified, negligible either way).

| Mails per month | SES | Resend (for comparison) |
|---|---|---|
| 10,000 | ≈ $1.10 | $20 plan |
| 50,000 | ≈ $5.50 | $20 plan |
| 200,000 | ≈ $22 | ≈ $155 (plan + overage) |

The billing plan's `[costs] mail_per_thousand_usd` becomes `0.11`; the "$20 mail plan" disappears from the fixed costs; whether the tier prices follow is the owner's decision (§15 question 3).

## 11. The removal: every file, every line of Resend

**Rule (owner, 2026-09-27): a removal is complete.** Every class, function, parameter, constant, setting, environment variable, log event, fake, test, fixture, comment, docstring and documentation sentence that exists only because of Resend is deleted or rewritten in M6a — not left for later, not commented out, not kept "in case". Code that loses its reason (a parameter that only fed an idempotency key, a comment explaining Resend behaviour) goes with it. Afterwards the code must be at least as small and clear as before; a review of the whole diff for dead code and simplification is part of the milestone (§12).

**Code**

| File | Delete | Add / change |
|---|---|---|
| `src/app/delivery/email_client.py` | `ResendClient`, `to_payload`, `API_BASE`, `TIMEOUT_SECONDS` (→ SMTP timeouts), `BATCH_SIZE`, `verify_webhook_signature`, `WEBHOOK_TOLERANCE_SECONDS`, the `_rate_limit_error` helper, the module docstring ("two endpoints and a signature check"), `SERVICE = "Resend"` | `SmtpClient`, `SmtpSession`, `DeliveryUncertain`, `LOCAL_HOSTS`, `SERVICE = "Amazon SES"`; `EmailError`, `EmailTemporaryError`, `QuotaExhausted` kept — the `QuotaExhausted` docstring loses "monthly" and "plan limit" |
| `src/app/delivery/sns.py` | — | new: `verify`, `string_to_sign`, `SnsCertificates` |
| `src/app/delivery/render.py` | `OutgoingEmail.from_` and `.idempotency_key`; the `idempotency_key` parameter of `render_summary_mail`; the `appearance_id` parameter of `render_notice_mail` and its docstring lines about keys; the "without an idempotency key" sentences in the magic-link and confirm composers; the `SNAPSHOT_FIELDS` comment's "byte-identical under its stable idempotency key" | `from_name`, `from_address`; `sender()` returns both, and the magic-link and confirm composers, which build their `from_` inline today, use it too; tags extended (§4.3) |
| `src/app/delivery/mailing.py` | `from app.delivery.email_client import BATCH_SIZE`; `_preview_key` and the `replace(preview, idempotency_key=…)` call; the module docstring's "four things" | local `BATCH_SIZE = 100` (page size); `send_batches` per §5 with `should_stop`; `_pending` filters `attempted_at IS NULL`; module docstring rewritten ("never twice" rests on: snapshot, claim-before-send, advisory lock); `_hold_the_send_time` docstring (§5) |
| `src/app/web/routes/webhooks.py` | the Resend/Svix handler, `_blocking_reason` for `email.*` events, the import of `verify_webhook_signature`, and the parsing helpers `_parse`, `_object`, `_recipients` where they are shaped for the old payload | `handle_ses_webhook` (§6.2); `block_addresses` unchanged |
| `src/app/services.py` | `ResendClient` import and construction | `email=SmtpClient(settings.email.smtp_host, settings.email.smtp_port, secrets.smtp_username, secrets.smtp_password, settings.email.max_send_rate_per_second)`, `sns_certificates=SnsCertificates(http)` |
| `src/app/config.py` | `resend_api_key`, `resend_webhook_secret`, `sender_address` (secret) and the override in the `sender_address` property with its "provider refuses every sender on a domain it has not verified" docstring | `smtp_username`, `smtp_password`, `ses_feedback_topic_arn`; `EmailSettings.smtp_host`, `.smtp_port`, `.max_send_rate_per_second`; `confirm_cooldown_minutes` |
| `src/app/log.py` | `WEBHOOK_RESEND`, `WEBHOOK_SECRET_UNUSABLE` | `WEBHOOK_SES`, `WEBHOOK_SES_SUBSCRIPTION`, `EMAIL_UNCERTAIN`, `EMAIL_DELIVERED`, `EMAIL_DELAYED`, `EMAIL_BOUNCED`, `EMAIL_COMPLAINED`, `EMAIL_REJECTED` (`EMAIL_REFUSED` stays) |
| `src/app/db/models.py` + one migration | the `Delivery` comments about "exactly-once guarantee", the "batch loop" index comment, "open rates" in the ponytail, the `render_snapshot` comment's idempotency rationale | `Delivery.attempted_at`, index `WHERE attempted_at IS NULL` (§5) |
| `src/app/worker.py` | `RESEND_API_KEY` in `NEEDED_SECRETS`; "delivering batches" wording (docstrings around the mailing loop); the `_notice_kind` docstring's "crash between the provider accepting a batch and the commit"; `appearance_id` in the `_failure_notice` context | `needed_secrets(settings)` (§7); passes `should_stop` |
| `src/app/web/server.py` | `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` in `NEEDED_SECRETS` | `needed_secrets(settings)` |
| `src/app/jobs/steps.py` | `appearance_id=` in the two `render_notice_mail` calls; "batches" in the `_begin` docstring | `send(…, should_stop)` |
| `src/app/cli.py` | `MISSING_KEY_HINTS["app.delivery"] = "RESEND_API_KEY"` | `"SMTP_USERNAME/SMTP_PASSWORD (or Mailpit running locally)"` |
| `src/app/subscriptions.py`, `web/routes/creator.py` | — (only `confirm_cooldown_minutes`) | the docstrings naming "the mail provider's suppression list" stay true |

**Tests**

| File | Change |
|---|---|
| `tests/unit/test_email_client.py` | rewritten for `SmtpClient`: every row of §4.4, rate spacing with the fake clock, `From` quoting, `ValueError` on CR/LF, quoted-printable parts, tags header, STARTTLS derivation |
| `tests/unit/test_sns.py` | new: v2 signature valid; v1 refused; wrong host, `http`, non-`.pem` path refused; tampered `Message`; `Subject` present/absent; confirmation string-to-sign; region derived from the ARN |
| `tests/fakes.py` | `FakeEmailClient` loses `send_batch`, `batches`, `batch_fails_with`, `batches_before_failure`, `lose_response` and the `base64`/`hmac`/`hashlib`/`time` imports they needed; gains `session()` and options `fail_with`, `fails_from` (n-th mail), `uncertain_at` (records the mail, then raises `DeliveryUncertain`), `on_send`. `WEBHOOK_SECRET` and `svix_headers` replaced by an SNS message signer over a session-scoped test key pair; `services()` builds a default fake `SnsCertificates` |
| `tests/unit/test_operator_errors.py` | `TestResend` → `TestSmtp` (530/535/554, quota 454); the `NeedsOperator("Resend", …)` expectation |
| `tests/unit/test_config.py` | `SENDER_ADDRESS` tests deleted; `RESEND_API_KEY` in the missing-secrets test replaced; `EmailSettings(...)` constructions gain the new fields |
| `tests/unit/test_render_summary.py` | the comment about the idempotency key; `from_` assertions → `from_name`/`from_address` |
| `tests/integration/test_mailing.py` | exactly-once suite rebuilt on claims (a mailing larger than the quota left does not start and is parked with both numbers; crash after claim → never re-sent; uncertain → run ends, not re-sent, logged; > 3 uncertain → `NeedsOperator`; definite failure → released and re-sent once; any other exception after the claim → released; stop flag → no claim, no attempt counted; blocked mid-send still stops the rest; `recipient_count` excludes uncertain); the preview-key class and every `mailing/…`/`preview/…` key assertion deleted; `QuotaExhausted("Resend", …)` |
| `tests/integration/test_fan_area.py` | webhook section → SNS (valid bounce blocks; transient does not; suppression-list subtype blocks; complaint outranks bounce; delivery/delay events log with ids and without address; bad signature → 401; empty topic setting → 503 + incident; foreign topic → 403 + incident; certificate not fetchable → 503; feedback silence after a send → incident; subscription confirmation logged with its URL; replay is a no-op; garbage → 401); `RESEND_WEBHOOK_SECRET` fixture |
| `tests/integration/test_transcribe.py` | the `notice/{kind}/{id}` key assertion deleted |
| `tests/integration/test_web.py` | the oversized-body path `/webhooks/resend` → `/webhooks/ses` |
| `tests/integration/test_cli.py`, `test_worker.py`, `test_creator_area.py`, `test_summarize.py` | constructor and option names only |
| `tests/integration/test_mail_roundtrip.py` | new: the Mailpit round trip (§8) |

**Configuration and deployment:** `.env.example` (Resend block → SMTP/SNS block; `SENDER_ADDRESS` gone), `render.yaml` (Resend keys → `SMTP_*`, `SES_FEEDBACK_TOPIC_ARN`, `EMAIL__SMTP_HOST`, `EMAIL__SMTP_PORT`), `docker-compose.yml` (Mailpit), `.github/workflows/ci.yml` (Mailpit service), `pyproject.toml` (the httpx comment names Resend).

**Documentation:** `README.md` (the Sperrliste paragraph, the key table rows, the test-address and tunnel paragraphs → Mailpit and the simulator); `docs/ARCHITECTURE.md` (the payload-freeze rationale, "Blocks are permanent" (Resend → SES suppression list), the fan-area webhook text and unblock procedure, the 401 sentence, "new idempotency key" on postpone, the whole "Exactly once" section → "Never twice", a Decisions entry "Amazon SES over SMTP; Listmonk evaluated and rejected"); `docs/runbooks/operations.md` (new: §9, unblocking, uncertain deliveries, "did the mail arrive?"); `docs/backlog.md`; `implementation-notes.html` (the setting name `confirm_resend_minutes` described as current); **the manifest** (`docs/manifest/creator-plattform-manifest.md` names "Resend oder Postmark" twice and promises "genau einmal" — updated with the other decisions, MVP plan M6b).

**The gate — M6a is not done until this prints nothing:**

```sh
git grep -nI -e Resend -e RESEND -e resend_ -e 'resend\.' -e svix -e whsec -e idempotency_key -e Idempotency-Key \
  -- src tests config migrations pyproject.toml .env.example render.yaml docker-compose.yml .github \
     README.md docs/ARCHITECTURE.md docs/runbooks docs/backlog.md docs/manifest ':!src/app/static'
```

Case-sensitive on purpose: the vendored `src/app/static/htmx.min.js` contains `htmx:beforeSend` (excluded), and the English verb must not trip the gate — **code and docs write "send again", never "resend".** Documentation that records the change — ARCHITECTURE's Decisions entry, the manifest's change notes — describes it without naming the removed provider ("the previous transactional mail service"). Plans and `implementation-notes.html` keep the name only in dated history. The gate runs again at the end of every later milestone **without the two `idempotency_key`/`Idempotency-Key` patterns** — Stripe uses idempotency keys legitimately from M7b (billing plan §5).

## 12. Milestone M6a

### M6a — Amazon SES replaces Resend (≈ 3 sessions) — *added 2026-09-27*
Test-first throughout: the claim-before-send rule starts with the test that fails the way the old design fails without an idempotency key (a crash after the provider accepted → the mail is sent twice).
- [ ] Settings and secrets (§7) with validation; `confirm_cooldown_minutes`; `needed_secrets(settings)`; `.env.example`, `render.yaml`.
- [ ] `OutgoingEmail` with `from_name`/`from_address` (§4.2); `SmtpClient` + `SmtpSession` + the mapping of §4.4, with unit tests for every row, rate spacing, `From` quoting, CR/LF, quoted-printable.
- [ ] Migration `deliveries.attempted_at` + index (hand-written, §5); `send_batches` on claims with `should_stop`; `render_notice_mail` without `appearance_id`.
- [ ] `/webhooks/ses` + `sns.py` + `SnsCertificates` in `Services` (§6), incl. delivery-status logging, with the tests of §11.
- [ ] Mailpit in `docker-compose.yml` and CI; the Mailpit round-trip test (§8).
- [ ] Every row of §11 done; the gate prints nothing.
- [ ] `docs/runbooks/operations.md` created (§9, unblocking, uncertain deliveries, "did the mail arrive?"); README, ARCHITECTURE, backlog, notes as listed in §11.
- [ ] **Manifest §7.6 and §7.8** (the mail provider and "Öffnungs- und Klickraten liefert der Dienst") updated to Amazon SES without tracking, in German, each change marked „*geändert am 27.09.2026*“, the old provider not named — so the gate, which includes `docs/manifest`, can pass. The manifest's other updates follow in M6b.
- [ ] Mutation probes: claim moved after the send (the crash test must fail); release on failure removed; uncertain treated as retry-and-resend; pending filter on `sent_at` instead of `attempted_at`; stop check removed; the > 3 uncertain cap removed; `SignatureVersion` check removed; certificate host check loosened to a suffix match; `TopicArn` check removed; the empty-topic answer changed from 503 to 401; the quota check removed; `Transient` treated as `Permanent`; `From` built by string formatting; the claim also released after a failed step-6 commit (the double-send test must fail); `starttls()` without the verifying context.
- [ ] A review of the whole diff for dead code and simplification before the milestone is called done (MVP plan §3 "a removal is complete").
- **Done when:** `docker compose up` → a local sign-up's confirm mail and a mailing to three confirmed subscribers (one creator name with a comma) appear in Mailpit, fan mails with `List-Unsubscribe` + `List-Unsubscribe-Post` and both MIME parts; a worker stopped with SIGTERM mid-send and started again sends nobody twice and leaves no uncertain delivery; a worker killed with SIGKILL mid-send leaves at most one; the full suite, ruff and the gate are clean. **Live SES acceptance happens in M9** (domain and public URL): a real mail to the owner's Gmail with `dkim=pass` for `mail.<domain>`, `spf=pass` for `bounce.mail.<domain>`, `dmarc=pass`, a DKIM `h=` list containing `list-unsubscribe` and `list-unsubscribe-post`; `bounce@simulator.amazonses.com` and `complaint@simulator.amazonses.com` each end with the subscriber blocked with the right reason; the delivery of a real mail appears as `email.delivered` in the log.

## 13. Verified facts

Checked 2026-09-27 against docs.aws.amazon.com, aws.amazon.com/ses/pricing and the CPython 3.13 source. **Unconfirmed** facts are marked and have a check in §9 or M9.

- **Pricing:** plans since 2026 — new accounts start on *Essentials* ($0.16 per 1,000, from 2026-07-21); *à-la-carte* $0.10 per 1,000 outbound + $0.12 per GB of message data; no fixed fee on either. The old 3,000-free-mails tier is gone (new AWS accounts get up to $200 of general free-tier credit instead).
- **Sandbox:** only verified recipients or the mailbox simulator, 200 mails/24 h, 1/s, per region. Production access by console form or `aws sesv2 put-account-details --production-access-enabled --mail-type MARKETING --website-url …`; first answer within 24 h. The granted quota "varies" — the widely quoted 50,000/day and 14/s are **unconfirmed**. Quotas count recipients.
- **Identity:** a subdomain can be a domain identity; Easy DKIM = 3 CNAMEs, RSA 2048; custom MAIL FROM needs exactly one MX to `feedback-smtp.eu-central-1.amazonses.com` + SPF TXT; DMARC alignment is relaxed when sending from a subdomain.
- **SMTP:** `email-smtp.eu-central-1.amazonaws.com`, STARTTLS on 25/587/2587, TLS wrapper on 465/2465, TLS mandatory; region-specific credentials derived from an IAM key; minimum permission `ses:SendRawEmail`, restrictable by identity ARN and `ses:FromAddress` (**unconfirmed for SMTP**, and whether the configuration set must be listed — §9 step 7). Max 40 MB per message, 50 recipients (we send one). Replies: `250 Ok <MessageId>`; `454 Throttling failure: Maximum sending rate exceeded` / `Daily message quota exceeded`; `421`; `451`; `530`; `535`; `554` access denied / address not verified; `552` too long.
- **Python 3.13 `smtplib`/`email`:** `mail()`/`rcpt()` return codes; `data()` raises `SMTPDataError` only before `354` and returns the final reply; read/write errors become `SMTPServerDisconnected`; `SMTP.__exit__` raises on a QUIT other than 221; a CR/LF in a header value raises `ValueError` on assignment; `set_content` under `policy.SMTP` picks `8bit` for non-ASCII unless a `cte` is given; a display name with a comma must go through `headerregistry.Address`.
- **No idempotency:** neither API v2 `SendEmail` nor SMTP has one. AWS: "on rare occasions, SES may accept an email for delivery even though the send request returns an error". SES overwrites `Message-ID` and `Date`.
- **Feedback:** configuration-set event publishing to a standard SNS topic in the same region; event types incl. Send, Delivery, Bounce, Complaint, Reject, DeliveryDelay, Open, Click; SNS HTTPS with `SubscriptionConfirmation`, a CA-trusted certificate on our side, ≈ 15 s timeout; **only `5xx` and `429` are retried — every other answer drops the message** (default HTTP/S policy: 3 retries 20 s apart; a custom delivery policy allows up to 100 retries within 3,600 s); topics sign with **SignatureVersion 1 (SHA1) by default** — set 2. Account suppression list on for bounce + complaint; suppressed sends are accepted, not delivered, reported as bounces. **Gmail provides no complaint data to SES.** Reputation: bounce rate review at 5 %, pause at 10 %; complaint rate review at 0.1 %, pause at 0.5 %.
- **List-Unsubscribe:** SES passes our own headers through (it replaces them only when its own list management is used, which we do not). **Unconfirmed:** that Easy DKIM's signed-header list covers both (checked live in M9).
- **Tracking:** off unless a configuration set publishes Open/Click events; ours publishes neither.
- **Data protection:** AWS DPA with SCCs is part of the AWS service terms; processing in eu-central-1; AWS is a US company (CLOUD Act) — recorded as a processor in the privacy notice.

## 14. Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| Production access refused or delayed | AWS reviews every account; new accounts get questions | Verified domain first; the prepared answer (§9 step 9); apply as soon as the site is live. **Fallback without code change:** another SMTP relay that allows newsletters (e.g. Lettermint, EU, from €10 per 10,000) — host and two secrets; only its bounce webhook would be new code. |
| A fan misses a mailing | Claim-before-send turns a crash inside one SMTP exchange into a loss for that fan | Deploys stop cleanly before the claim (§5 step 2.3); a hard crash loses at most one fan per run; > 3 per mailing stops it for the operator; logged at ERROR; the fan gets the page link by hand. Owner decision 2026-09-27. |
| A long send occupies the worker | One tick sends the whole list (≈ 12 min per 10,000 at 14/s) | Other rows wait one tick; the heartbeat grace covers it (MVP plan §15.2); a deploy ends it cleanly between two mails. |
| Gmail complaints invisible | Gmail does not report to SES | Postmaster Tools (§9 step 11); double opt-in; one-click unsubscribe. |
| The account is paused for reputation | Bounce ≥ 10 % or complaint ≥ 0.5 % | Double opt-in and MX check keep bounces low; alarms at 5 % / 0.1 %; permanent blocks. |
| A leaked SMTP credential sends spam in our name | Static credentials | Sending-only IAM user restricted to the identity and the From domain; budget alert; rotation documented. |
| The work network blocks SMTP ports | It already blocks tunnels (MVP plan §17, M5 status) | Port 2587; development needs no SES at all (Mailpit). |

## 15. Questions — decided and open

The same questions, in German, are in `implementation-notes.html` §5.

Decided on 2026-09-27 by the owner: Resend removed completely; SES directly, no Listmonk (§2); for the uncertain recipient, rather no double mail (§5); delivery status visible in our logs (§6).

Open:

1. **Domain and DNS provider** (MVP plan §20 question 1, the domain gate) — SES needs DNS records on the real domain; development does not wait for it (Mailpit).
2. **AWS account** — the owner creates it after the domain decision (§9 step 1); nothing in M6a's code needs it.
3. **Tier prices after the mail-cost drop.** The tiers were set against ≈ $0.90 per 1,000 mails; with SES our cost at the upper edge of the largest tier falls from ≈ €157 to ≈ €22 a month (billing plan §1). Default: the table stays as confirmed on 2026-09-21 until the owner decides.
