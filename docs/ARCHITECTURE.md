# Architecture

English, like the code. The manifest (`docs/manifest/`) says *what* and *why* in
product terms; the plan (`docs/plans/`) says what to build; this file says how
the code that exists is cut, and records the decisions behind it.

## Where to find what

| You want to change… | Go to |
|---|---|
| a tunable value | `config/settings.toml` — the comments there are the documentation |
| a secret or an environment-specific value | `.env.example` lists every one |
| what a table looks like | `src/app/db/models.py`, one file, all tables and vocabularies |
| the name of a log event | `src/app/log.py` — the constants are the authority |
| how the product is addressed | `settings.product.name`, the one place the name lives |
| what the worker does per tick | `src/app/worker.py` |
| what a page or a mail looks like | `src/app/templates/` |

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

### The online page always shows the full text
The mail variant governs the mail only. If the page mirrored the variant, a
teaser mail's "weiterlesen" link would arrive at the same teaser, and the full
text would exist nowhere.

## The pipeline as it stands

`detected → enriched → transcribed → analyzed`, with four terminal exits
(`skipped_short`, `skipped_no_transcript`, `skipped_too_long`, `unavailable`)
and one failure state. Two rules are worth knowing before reading `jobs/steps.py`:

- **Waiting is not failing.** A premiere that has not started, a livestream
  recording whose duration YouTube has not computed yet, a creator whose daily
  LLM budget is spent — all of these park the row for six hours *without*
  counting an attempt. Only genuine errors count, and only they can exhaust the
  ladder and reach `failed`.
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

`record_call` writes in a session of its own and commits immediately. This is
deliberate and load-bearing: a step that pays for a summary and then fails on a
later write would otherwise roll back the record of what it spent, and ten
retries would re-pay against a ledger that never grew — defeating the one
mechanism that exists to stop exactly that.

## Still to be written

The mailing transition table and the exactly-once mechanics belong here once M6
lands. Until then the plan is the authority for them.
