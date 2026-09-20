# Architecture

English, like the code. The manifest (`docs/manifest/`) says *what* and *why* in
product terms; the plan (`docs/plans/`) says what to build; this file says how
the code that exists is cut, and records the decisions behind it.

## Where to find what

| You want to change… | Go to |
|---|---|
| a tunable value | `config/settings.toml` — the comments there are the documentation |
| a colour, a font size, a corner radius | `src/app/design.py` — pages and mails both read it |
| a secret or an environment-specific value | `.env.example` lists every one |
| what a table looks like | `src/app/db/models.py`, one file, all tables and vocabularies |
| the name of a log event | `src/app/log.py` — the constants are the authority |
| how the product is addressed | `settings.product.name`, the one place the name lives |
| what the worker does per tick | `src/app/worker.py` |
| what a page or a mail looks like | `src/app/templates/` |
| the sign-up, confirm and unsubscribe rules | `src/app/subscriptions.py` |
| what counts as a valid address | `src/app/addresses.py` |
| when a mail goes out, and how it goes out exactly once | `src/app/delivery/mailing.py`, `src/app/jobs/schedule.py` (see "Mailings" below) |
| what was deferred, and when to build it | `docs/backlog.md` |

## The cut

```
sources/      →  transcripts/  →  analysis/  →  delivery/
(source-specific) (two providers)  (source-independent)  (mail + pages)
                         ↑
                 jobs/  drives all of it, one step at a time
                 web/   shows it and takes input
```

Exactly two abstractions exist from day one, both named by the manifest: the
source/transcript interface and the LLM gateway. Everything else — the mail
client, the YouTube API client — is a plain class. Test fakes duck-type them;
no Protocol is written until a second implementation actually exists.

## State lives in the database

There is no queue. `appearances.status` and `mailings.status` *are* the queue:
the worker selects rows that are due, runs the step for that status, and writes
the new status. Consequences worth knowing:

- A crash anywhere resumes at the next tick, because every step re-reads its row
  before acting.
- Two columns (`attempts`, `next_attempt_at`) and one function are the entire
  retry system.
- Nothing is scheduled ahead of time, so changing a send time needs no
  cancellation logic.

## Decisions

Short entries, one per decision that a reader would otherwise have to
reverse-engineer. New decisions are appended, not rewritten.

### A modular monolith, not services
One repository, one image, two processes (web and worker). Modules are Python
packages with clear seams, so that phase 2 adds files instead of rewriting them.
Distribution would buy nothing at this size and cost a deployment story.

### A status machine instead of a job queue
Considered and rejected: a queue library. The state already lives in the two
status columns; a queue would duplicate it, add four tables, a connector and
LISTEN/NOTIFY semantics, and make "what is this row doing right now" a question
with two answers. The cost of the decision is a worker that polls every 60
seconds, which is invisible next to a 48-hour minimum delay.

### Poll the feed, do not subscribe to push
The public Atom feed is polled every six hours. Push notifications would shorten
detection to seconds, which shortens nothing anyone can observe when the mail
goes out days later. Push is purely additive later.

### Sync SQLAlchemy and `def` endpoints
FastAPI runs `def` endpoints in a threadpool; the worker is one sequential loop.
Async would add a second colour of function and buy no throughput at one
channel's volume.

### `VARCHAR` + `CHECK`, not native Postgres enums
Alembic autogenerate mishandles native enums, and adding a status value would
need a migration of its own. Migrations spell the allowed values out rather than
importing the `StrEnum`, because a migration is a snapshot of the past, not a
view of today's code.

### The LLM gateway is a separate container
The application speaks plain OpenAI-compatible HTTP and never imports a provider
SDK. Swapping or removing the gateway is a change of one URL. It costs one more
moving part for a single provider today; the manifest accepts that trade to keep
the model choice open.

### Two transcript providers, no Whisper in the MVP
Official captions when the creator has connected YouTube, the unofficial library
otherwise. A video with no captions is skipped and the creator told. Whisper
arrives with the podcast connector, which is the first source that truly needs
it.

### The mail payload is frozen when the preview goes out
`mailings.render_snapshot` freezes the creator's rendering-relevant fields at
`preview_sent`. Two things depend on it: the fans get exactly the mail the
creator saw and chose not to stop, and a retried batch carries a byte-identical
payload under a stable idempotency key. The alternative — hashing the body into
the key — was rejected because it turns a changed body into a second mail for
recipients who had already received the first.

### One source for what the product looks like
Pages carry a stylesheet, mails carry inline rules, because mail clients drop
everything else. That is a constraint on where rules end up, not on where they
are decided: `app/design.py` holds every colour and size, the page shell emits
them as custom properties, the mail shell inlines the same values. A test keeps
both honest — neither file may name a colour of its own — because a colour
changed in one and forgotten in the other is how a product starts looking like
two products. What is *not* in there is the creator's accent: that varies per
customer, lives in the database, and is made readable below.

### The brand colour stays; what must be read is derived from it
A creator picks one colour, and it then has to work on a white mail, a light
page and a dark one. Left alone it fails at least one of those — near-black
vanishes in dark mode, pale yellow on white, and white button text on a pale
button. `app/branding.py` keeps the colour for surfaces (buttons, rules) and
derives what carries text: the link colour is moved along its own hue until it
clears WCAG AA against the page, and a button's label is black or white,
whichever reads. The creator never sees the failure mode on their own machine,
which sits in one mode — so it cannot be left to their judgement.

### The online page always shows the full text
The mail variant governs the mail only. If the page mirrored the variant, a
teaser mail's "weiterlesen" link would arrive at the same teaser, and the full
text would exist nowhere.

### Blocks are permanent, and the app holds a sending-only key

Decided 2026-09-18. The plan first let a confirmation lift a bounce block. That
cannot work with Resend: a hard bounce puts the address on an account-wide
suppression list that does not expire, so the confirm mail never arrives; and
removing an entry needs a full-access key, which could also delete domains and
read every mail. Least privilege won: the app keeps a key that can only send,
blocks are permanent, and the rare fan whose mailbox works again is unblocked
by the operator (see "The fan area").

## The pipeline as it stands

`detected → enriched → transcribed → analyzed`, with four terminal exits
(`skipped_short`, `skipped_no_transcript`, `skipped_too_long`, `unavailable`)
and one failure state. Two rules are worth knowing before reading `jobs/steps.py`:

- **Waiting is not failing.** A premiere that has not started, a livestream
  recording whose duration YouTube has not computed yet, a creator whose daily
  LLM budget is spent — all of these park the row for six hours *without*
  counting an attempt. Only genuine errors count, and only they can exhaust the
  ladder and reach `failed`.
- **A key or a plan is the operator's, not the video's.** A rejected API key
  or an exhausted quota raises `NeedsOperator`: the row waits an hour without
  counting an attempt, nobody but the operator hears of it, and every attempt
  logs `operator.action_needed` at ERROR — service, the provider's own words,
  and which setting to check. Missing secrets are logged at start
  (`config.secret_missing`).
- **`now` is always a parameter.** No step reads the clock. That is what lets
  the tests drive a seven-day schedule in milliseconds.

## The transcript chain

Official captions first when the creator has connected YouTube, the unofficial
library second. Two details that are not obvious from the code:

- The official provider is offered **only on a row's first attempt**. It costs
  250 quota units, and a provider that declined a video once will decline it
  again; ten attempts would spend 2,500 units to learn nothing.
- If any provider fails *temporarily*, the whole step is temporary — even when
  another provider failed permanently. Losing a video to one blocked address
  would be the wrong answer when the retry ladder has a day and the minimum
  delay is two.

Provenance is stored with every transcript because it is legally relevant: the
official API and the unofficial library are not the same thing in a dispute.

## The cost ledger

It is an **estimate**, and it says so: the provider's invoice is the authority.
What makes the estimate trustworthy is that every line can be checked years
later. Four rules:

- **The price follows the model that answered**, not the one that was asked
  for. The configuration names a family (`anthropic/claude-sonnet-4-5`), the
  gateway answers with the snapshot it routed to (`…-20250929`); `price_of`
  matches the family, and an exact entry wins over it.
- **A model nobody priced is never booked at zero.** An answer that cannot be
  matched is charged at the price of the model we *asked* for — start-up
  guarantees that one has a price — and the row is marked `assumed`, with
  `operator.action_needed` in the log. A zero would not be a missing number but
  a wrong one: the daily cap sums the ledger, so zeros switch off the only
  guard against a runaway loop.
- **A shorter answer than any configured family is not guessed.** `claude-sonnet`
  could be either of two configured models, and picking one would book a call at
  another model's price with nothing saying so.
- **Every row keeps the price it was booked at** (`price_input`,
  `price_output`, `price_source`), so a line written before a price change
  still means what it meant then.
- **Cached input is billed at its own factors** (read ≈ 0.1×, write ≈ 1.25×),
  because the provider does. The tokens are kept separately on the row.

Prices carry a source and a check date in `config/settings.toml`; the worker
logs `llm.prices_stale` at start once one is older than three months.

**The invoice is a link, not a copy.** `llm.usage_dashboard` points at the
provider's own usage page — spend per model, per key, per period, in dollars.
It is printed with every figure the app produces (the worker's `llm.models`
line at start, the stale-price warning, `eval-prompts`), because a number
nobody can check is worth nothing. Mirroring that page into our database was
rejected: it would be a second source that silently rots, and the link stays
correct when the provider changes how it bills.

**Cost is the operator's, and nobody else's.** It lives in `llm_calls`, in the
logs and in operator commands. No page and no mail may show it — not to a fan,
and not to a creator, who would learn what their channel costs us and start
negotiating against our margin. A test refuses any template that mentions it.

**Switching the model** is `model_summary` / `model_sentiment` plus a price
entry in `config/settings.toml`, then `uv run app gateway-config`, which
teaches the gateway the same names, and a recreate. The application settings
decide; the gateway file follows. A test refuses a mismatch.

`record_call` writes in a session of its own and commits immediately. This is
deliberate and load-bearing: a step that pays for a summary and then fails on a
later write would otherwise roll back the record of what it spent, and ten
retries would re-pay against a ledger that never grew — defeating the one
mechanism that exists to stop exactly that.

## The fan area

The rules live in `subscriptions.py` (sign-up, confirm, unsubscribe, the
confirm mail) and `addresses.py` (what an address is); `web/routes/fan.py` only
speaks HTTP. The bounce webhook is `web/routes/webhooks.py`, the retention
sweep `cleanup` in `jobs/steps.py` (daily). Four rules hold them together:

- **The public form can only add, never take away.** A confirmed fan who signs
  up again gets the confirm mail again and nothing else changes.
- **A block is permanent.** Bounce, complaint and `email.suppressed` all block
  the address for every creator; a complaint outranks a bounce and is never
  replaced by one. The blocks mirror Resend's account-wide suppression list,
  which does not expire — a mail to a blocked address would be dropped anyway,
  and editing that list needs a full-access API key the app deliberately does
  not hold. **To unblock** a fan whose mailbox works again (operator only,
  never for a complaint): remove the address from the suppression list in the
  Resend dashboard, then
  `UPDATE subscribers SET blocked_at = NULL, blocked_reason = NULL WHERE email = '…';`
- **The answer never depends on the address — not its text, not its timing.**
  New, known, blocked, throttled, or the mail provider down: always "Schau in
  dein Postfach", and just as fast, because the confirm mail is sent after the
  response. Only an address that cannot receive mail at all (strict syntax,
  MX lookup) gets the form back with an error.
- **Two brakes, because one is forgeable.** The per-IP limit trusts forwarded
  addresses; the per-address brake allows one confirm mail per address per
  window across all creators. It reads the address row under a lock taken by
  `INSERT … ON CONFLICT DO UPDATE … RETURNING`, so two simultaneous sign-ups
  run one after the other and the second is throttled.

The cleanup deletes expired sign-ups, old unsubscriptions and then every
address without a subscription — except complaint blocks, which are what stops
a new sign-up. It skips (`SKIP LOCKED`) any address a sign-up holds, so it can
never cascade into a subscription being added.

## Request handling

Rules every route inherits, so no route can forget them (`web/server.py`,
`web/deps.py`):

- **Commit before the answer.** Routes take their session as `DbSession`
  (`Depends(get_session, scope="function")`): it commits before the response
  is sent. A page that says "done" never goes out ahead of a failed commit.
- **Mail after the answer.** Anything a response time could betray goes into a
  background task, which runs only after a successful commit.
- **Hostile input is refused early.** Bodies over 64 KiB get 413; a path with a
  control character is a 404 before it reaches a route; the webhook answers
  401 to anything unsigned, including when no secret is configured.
- **Nothing personal leaves in an error report.** Sentry gets no frame locals,
  no request bodies, no PII.

## Mailings: from schedule to inbox

One mailing per video. Its status is written in `delivery/mailing.py` and
nowhere else; the steps in `jobs/steps.py` and the stop/postpone routes in
`web/routes/mailings.py` only call it. When a step is due is one pure function,
`jobs/schedule.py:next_mailing_step`.

| From | To | Trigger |
|---|---|---|
| — | `scheduled` | `summarize`: send time = publication + delay, never earlier than now + minimum |
| `scheduled` | `sentiment_ready` | `prepare_sentiment` at T−2h; without a sentiment if none can be had before the preview is due |
| `scheduled` | `cancelled` | `prepare_sentiment` or the daily `cleanup`: the video is gone or private |
| `sentiment_ready` | `preview_sent` | `send_preview` at T−1h; pushes T to at least one stop window from now, freezes the payload |
| `preview_sent` | `sending` | `send` at T, once the preview has been out a full stop window; takes the recipient snapshot |
| `preview_sent` | `cancelled` | `send`'s re-check: the video is gone or private |
| `sending` | `sent` | `send`, when no delivery is pending |
| `scheduled`/`sentiment_ready`/`preview_sent` | `stopped` | the creator's stop link |
| `scheduled`/`sentiment_ready`/`preview_sent` | `scheduled` | the postpone link: later send time, new token, new sentiment, new preview |
| `sentiment_ready`/`preview_sent`/`sending` | `failed` | the retry ladder is exhausted, or an error no retry fixes; the creator is told after the commit |

Two rules make the table safe with two writers (worker and web process) and no
lock between them:

- **Every transition is one conditional statement**, `UPDATE … WHERE id = :id
  AND status = :expected`. Zero rows means someone else won; the loser logs
  `mailing.transition_lost` and does nothing else. The routes use the same
  shape keyed on the stop token.
- **A new schedule is a new token.** Postponing rotates `stop_token`, so every
  link of the old preview is dead, and the next preview is a new mail with a new
  idempotency key.

### Exactly once

Four mechanisms, each necessary:

1. **Snapshot.** In the transaction that moves `preview_sent → sending`, one
   `INSERT … SELECT` writes a `deliveries` row for every confirmed, unblocked
   subscription of the creator. Unique `(mailing_id, subscription_id)`. Whoever
   confirms later waits for the next mailing; whoever leaves during the send
   still gets this one (owner decision, 2026-09-18).
2. **Stable batches.** A batch is the next 100 pending deliveries `ORDER BY id`,
   sent with the idempotency key `mailing/{id}/{first_delivery_id}`. Its rows are
   marked sent in the commit after the provider accepted it. A crash between the
   call and the commit rebuilds the same batch under the same key, and the
   provider recognises the repeat.
3. **Frozen payload.** Every mail of a mailing renders from `render_snapshot`,
   written with `preview_sent`. The repeat in (2) is therefore byte-identical —
   what the provider does with a known key and a changed body is undocumented,
   and this design never asks.
4. **A block re-read per batch.** `_pending` filters blocked addresses again
   for every batch, not once at the snapshot: a bounce or a complaint that
   lands mid-send stops the rest. Those rows stay unsent, which is what the
   ledger should say about them, and `recipient_count` counts what was sent.
5. **Advisory lock.** `send` holds `pg_try_advisory_lock(mailing_id)` on a
   connection of its own for the whole run — a *session* lock, because a
   transaction lock would end with the first batch's commit. A second worker
   (a deploy overlap) finds it taken and returns. A failed unlock throws the
   connection away instead of returning it to the pool still locked.

Three rules keep the send honest when something goes wrong:

- **Progress clears the ladder.** A batch that went through resets `attempts`,
  so a long list cannot die of ten scattered provider hiccups with most of it
  unsent.
- **The finish is committed inside the lock.** Releasing the lock is the last
  thing that can fail, and a finished send must not be undone by it; a failed
  unlock throws the connection away and is logged, never raised.
- **A mailing does not wait forever.** Anything only an operator can fix parks
  the row hourly — but past `GIVE_UP_ON_A_MAILING_AFTER` the mailing ends and
  the creator is told, because they were shown a preview naming a time.

### The creator's brakes

The preview is the fan mail itself, with a bar on top: when it goes out, to how
many, and two links. They lead to a page with one button (link scanners follow
links); the POST acts. The answer is always true: "Gestoppt" only when this
request stopped the mail, otherwise what actually happened — on its way,
already stopped, cancelled, or a link replaced by a newer preview (410).
Postponing adds `schedule.postpone_hours`, up to publication plus
`max_delay_hours`; past that cap only stopping is offered, with the reason.
