# Billing Plan — usage, pricing, invoices, pause

> **Status:** planned, not started · **Date:** 2026-09-21 · **Part of the MVP.** This plan is one step of the MVP plan (`2026-09-mvp-implementation-plan.md`, §17: milestones **M7a** and **M7b**, between M7 and M8). It lives in its own file because it is a self-contained topic with its own decisions and facts; the MVP plan only points here. The conventions of the MVP plan apply unchanged: §3 principles, §14 testing (mutation probes for money rules), §16 documentation, "*Changed YYYY-MM-DD*" for every deviation, `docs/backlog.md` for everything deferred.
>
> **Why it exists.** Manifest §4.4 had "manual contract, invoice by hand" for the MVP and Stripe from Phase 2; manifest §4.3 tiered by list size. The owner changed both in a pricing workshop on 2026-09-21 (manifest updated the same day): invoicing moves into the MVP, and the price follows the mails sent, not the list size.
>
> **Progress:** M7a `[ ]` · M7b `[ ]` — tick the boxes in §9 as work completes.

## Table of contents

1. [What was decided, and why](#1-what-was-decided-and-why)
2. [What the code review found](#2-what-the-code-review-found-the-data-was-not-yet-good-enough-to-bill-from)
3. [Configuration](#3-configuration)
4. [Data model](#4-data-model)
5. [Modules](#5-modules)
6. [Early warnings and safety caps (M7a)](#6-early-warnings-and-safety-caps-m7a)
7. [Invoicing and the pause (M7b)](#7-invoicing-and-the-pause-m7b)
8. [Tests](#8-tests)
9. [Milestones](#9-milestones)
10. [Verified Stripe facts](#10-verified-stripe-facts)
11. [Risks](#11-risks)
12. [Questions — decided and open](#12-questions--decided-and-open)

---

## 1. What was decided, and why

**Goal of the price: cover the cost, plus a small compensation.** Not value pricing. The owner must never pay for a customer, and the creator must never face a black box.

**What a creator costs** (measured 2026-09-19/20, provider prices in MVP plan §18):

| Driver | Size | Scales with |
|---|---|---|
| LLM | ≈ 3 ct for a 15-minute video, ≈ 8 ct for 30–45 minutes, ≤ 25 ct at the transcript ceiling | videos × length |
| Mail | ≈ $0.90 per 1,000 at the provider's overage price, ≈ $0.35–0.40 inside a plan | **videos × list size**, plus one confirm mail per sign-up |
| YouTube API | free; a capacity limit, not a cost (§6) | videos |
| Fixed | hosting ≈ $27, mail plan $20 from the first list above 100 fans, proxy if needed | nothing |

Two conclusions carry the model. **Mail dominates**: above roughly 300 fans, sending one video costs more than analysing it. And the two drivers are not independent — mail cost is their *product* — so list size alone (manifest §4.3) cannot be the price metric: a daily uploader and a monthly one with the same list differ by a factor of thirty.

**The model.**

1. **One public tier table by mails sent per calendar month.** Counted is every mail sent to a creator's fans in his name: summary mails and confirm mails. Previews, notices and login links are not counted (one per mailing; noise).
2. **Each calendar month is priced on its own** from its measured count, and frozen when it ends. *Refined while designing the threshold in point 4: an average over a period is undefined for a period that ends early, and one line per month is easier to verify than an average — decided, see §12.*
3. **Billed in arrears.** Nothing is estimated on an invoice. Every creator starts in the smallest tier, because every list starts at zero. A forecast ("if 1–3 % of your subscribers sign up …") belongs to the sales conversation and the landing page, never to an invoice.
4. **One invoice after six unbilled months, or as soon as €100 have accrued**, whichever comes first. Small amounts are collected rarely (the payment fee has a fixed part), and the owner's exposure per customer stays near €100. The owner accepts the default risk of billing in arrears (decision 2026-09-21).
5. **The owner can override the price per creator**, including €0, at any time, for the months not yet frozen. The creator's page shows both: "agreed with you: €0 / list price in your tier: €9".
6. **The creator sees his numbers at any time**: this month's count and tier, what has accrued, when the next invoice is due at the latest, every past month itemised per mailing, every invoice with its status and payment link. **He never sees what he costs us** — the existing test that keeps cost words out of every template stays as it is and now guards exactly this line.
7. **Stripe only**, as invoices (`send_invoice`), not as subscriptions: the amount is ours to compute, Stripe sends, hosts, collects, reminds and produces the PDF. No card data, no checkout, no customer portal in the MVP.
8. **No webhook.** A daily job asks Stripe for the state of our open invoices. No public endpoint, no signature check, no replay handling — the surface where M5's worst defect sat — and everything is testable against a fake. A "check now" button covers the impatient case.
9. **Unpaid → automatic pause**, announced a week ahead, explained in the mail and on the page with the payment link, lifted automatically when the invoice is paid (owner decision 2026-09-21).

**Tier table** (final prices; the owner invoices as a small business under §19 UStG, so no VAT is added; German creators only for now):

| Tier | Mails per month, up to | Price per month | Our cost at the upper edge¹ |
|---|---|---|---|
| S | 2,000 | €5 | ≈ €2 |
| M | 5,000 | €9 | ≈ €4.50 |
| L | 10,000 | €15 | ≈ €8.50 |
| XL | 25,000 | €29 | ≈ €20 |
| 2XL | 50,000 | €55 | ≈ €40 |
| 3XL | 100,000 | €99 | ≈ €79 |
| 4XL | 200,000 | €179 | ≈ €140 |
| above | — | individual: the owner sets an override | — |

¹ At the provider's overage price (≈ €0.77 per 1,000), plus LLM and the payment fee. Inside a mail plan the real average is about half; that difference is the contribution to the fixed costs, and it grows with volume without the creator seeing a surcharge.

**Scenarios** (list = 1 %…3 % of YouTube subscribers — an assumption nobody has data for; it is the most important number still missing, and only a pilot delivers it):

| Channel type | Videos / month | Mails / month | Tier | Price | Variable cost | Left |
|---|---|---|---|---|---|---|
| 19k subscribers, weekly | 4 | 0.8k … 2.3k | S … M | €5 … 9 | €0.90 … 2 | +€4 … 7 |
| 24k subscribers, weekly | 4 | 1.0k … 2.9k | S … M | €5 … 9 | €1 … 2.50 | +€4 … 6.50 |
| 223k subscribers, 2–3 per week | 11 | 25k … 74k | XL … 3XL | €29 … 99 | €20 … 58 | +€9 … 41 |

**Where the model stops carrying.** No customer costs more than he pays, by construction. The fixed costs are a different matter: about nine to ten small customers cover the hosting, or a single mid-sized one. If the real sign-up rate is far below 0.5 %, every customer sits in tier S. If the mail provider changes, the tier prices are recomputed from `[costs]` (they go down). Above 200,000 mails a month the price is negotiated.

**Rejected alternatives.** *A flat price from an assumed list size (3 % of subscribers):* it overcharges exactly when the service underdelivers and undercharges exactly when it gets expensive; and the list size is not an assumption — we count it. *A formula per mail, metered:* fair, but a taximeter; kept in the backlog for the day hand-set overrides become a chore. *Stripe subscriptions:* they want a fixed recurring amount; ours is computed. *Attribution at the providers* (a workspace and key per creator): the providers do not know our creators; our counts give the shares, their invoices give the totals.

## 2. What the code review found (the data was not yet good enough to bill from)

1. **Failed LLM calls are booked with zero tokens** (`record_call` with `error`), and a schema retry loses the tokens of its first attempt (`BifrostGateway.complete_json` returns only the last `usage`). The ledger counts tokens only for calls that succeeded; the daily cap cannot see the rest. → M7a.
2. **`deliveries` is not a durable count.** Its rows cascade with `subscriptions`, and unsubscribed subscriptions are deleted after 30 days, so a month's count shrinks in hindsight. `mailings.recipient_count` with `sent_at` is durable and is what billing reads. The backlog entry that named `deliveries` is corrected.
3. **Confirm mails are counted nowhere**, and cannot be reconstructed: pending sign-ups are deleted after seven days and `confirm_sent_at` is overwritten by a re-send. → a counter at the moment of sending.
4. **No history of anything that is later deleted** → months are frozen, with their itemisation, when they end.
5. **`creators` has no notion of paused, unpaid or billed.**
6. **The sign-up form is a cost and reputation attack surface.** Per-IP limit 20/minute, per-address brake, DNS check — but no honeypot and no ceiling per creator. A distributed bot with invented addresses at real domains gets through; the damage is less the money than confirm mails to strangers and the complaints that follow, which cost every creator's deliverability. → honeypot, warning, daily cap (§6).

## 3. Configuration

New tables in `config/settings.toml` (the rules of MVP plan §6.1 apply: no secrets, every tunable here). **Owner rule 2026-09-21: every number that shapes a price, a deadline or a limit lives here and nowhere else, and each carries a one-line comment that says what it does** — the comments below are part of the deliverable, and a test fails when a key in these tables has none.

```toml
[pricing]                               # the ONE tier table: billing and the landing page read it
currency = "EUR"
[[pricing.tiers]]
name = "S"                              # shown to the creator
up_to_mails = 2000                      # summary + confirm mails in one calendar month
price_eur = 5                           # final price; no VAT is added (§19 UStG)
# … M, L, XL, 2XL, 3XL, 4XL as in §1; above the last tier the owner sets an override

[billing]
invoice_after_months = 6                # at the latest
invoice_at_eur = 100                    # or as soon as this much has accrued; caps the default risk per creator
days_until_due = 14                     # payment term printed on the invoice
pause_after_days_overdue = 21           # align with the last reminder configured at Stripe
pause_warning_days = 7                  # heads-up notice this long before the pause
invoice_footer = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."   # legally required while the small-business rule applies

[costs]                                 # operator-only; what `cli costs` multiplies with
mail_per_thousand_usd = { value = 0.90, source = "provider price list, overage", checked_on = 2026-09-21 }
eur_per_usd = { value = 0.85, source = "owner, rough", checked_on = 2026-09-21 }

[youtube]
daily_quota_units = 10000               # Google raises it on request; then raise it here
quota_warn_at = 0.7                     # WARNING in the log: time to request more quota
quota_alarm_at = 0.9                    # ERROR in the log: videos will be parked soon

[web]                                   # additions
confirm_mails_warn_per_day = 500        # per creator; WARNING in the log, nothing is blocked
confirm_mails_cap_per_day = 2000        # per creator; above it sign-ups get "try tomorrow". Raise before a big launch
```

Start-up validation (pattern: `LLMSettings.check_every_used_model_has_a_price`): tiers non-empty, `up_to_mails` and `price_eur` strictly ascending, thresholds `0 < warn < alarm ≤ 1`, warn < cap. `[costs]` entries carry `source` and `checked_on` like the model prices and join the existing stale-price warning. Stripe's minimum charge (€0.50) is a module constant next to its single use, not a setting. New secret: `STRIPE_API_KEY` (restricted key; §7), needed by worker, web and CLI; listed in `.env.example`, `render.yaml` (`sync: false`) and the README key table.

## 4. Data model

| Table / column | Purpose | Key columns and constraints |
|---|---|---|
| `creators` + | billing and pause state | `billing_starts_at` nullable (null = not billed: demo creators, before the contract), `price_override_eur_cents` nullable (0 = free), `stripe_customer_id` nullable unique, `paused_at` nullable, `paused_reason` (`PausedReason`: `unpaid` / `operator`), `resumed_at` nullable. The customer's legal name and address live at Stripe only (data minimisation; one source). |
| `confirm_mail_days` | confirm mails actually sent, per creator and day | PK `(creator_id, day)` (day in `product.timezone`), `sent` int. `INSERT … ON CONFLICT DO UPDATE SET sent = sent + 1`. Cascades with the creator. Feeds the tier count, the warning and the cap. |
| `youtube_quota_days` | API units spent per Pacific day | PK `day`, `units` int. Same upsert. Exact across web, worker, CLI and restarts — which retires MVP plan §12's "per-process counters lie". |
| `billing_months` | one row per creator and calendar month; the running month is refreshed daily, a finished month is frozen | unique `(creator_id, month)`; `summary_mails`, `confirm_mails`, `mailings`, `tier` nullable (null = above the table), `list_price_eur_cents` nullable, `price_eur_cents` nullable (null = individual price still missing), `announced_tier` nullable, `lines` jsonb (per mailing: sent date, video title, recipients — frozen so that a later deletion cannot change an invoice's explanation), `frozen_at` nullable, `invoice_id` nullable FK. Cascades with the creator. |
| `invoices` | our record of what was sent to Stripe | `creator_id` (`SET NULL` — a ledger row outlives the creator), `status` (`InvoiceStatus`: `pending` / `open` / `paid` / `void` / `uncollectible` / `waived`), `amount_eur_cents`, `stripe_invoice_id` nullable unique, `number`, `hosted_url`, `due_at`, `paid_at`, `pause_warned_at`, `created_at`. A month belongs to at most one invoice through `billing_months.invoice_id`. |

Summary mails are **not** counted into a counter: `mailings.sent_at` and `recipient_count` are durable and already exactly-once; the daily refresh sums them. LLM cost stays in `llm_calls` only. One fact, one place.

Money is integer euro cents in the database. Templates receive formatted euro strings, never a variable whose name contains `cents` — the cost-words test forbids that substring, deliberately.

## 5. Modules

```
app/billing/
  pricing.py        pure, DB-free (like jobs/schedule.py): tier_for(mails), month_price(mails, override), due_for_invoice(months, now)
  usage.py          count_confirm_mail, count_youtube_units, refresh_months (running month + freeze), tier announcements
  invoicing.py      issue (pending → open, resumable), sync (open → paid/void/uncollectible), pause/resume rule
  pause.py          pause(session, creator, reason, now), resume(...): the two transitions and what they cancel
  stripe_client.py  StripeClient over plain httpx: create_customer, create_invoice, add_item, get_invoice, finalize
```

`StripeClient` becomes the sixth field of `Services`; `tests/fakes.py` gets `FakeStripe`, which keeps invoices in memory, enforces idempotency keys the way Stripe does (same key + different parameters → error) and lets a test mark an invoice paid. No SDK: the app speaks plain HTTP to every provider; the client sends `Idempotency-Key` and a pinned `Stripe-Version`, maps network/429/5xx to `TemporaryError` and 401/403 to `NeedsOperator`.

## 6. Early warnings and safety caps (M7a)

Owner rule 2026-09-21: **a limit that can stop the service is announced in the log well before it is reached.**

- **YouTube quota.** `YouTubeDataApi` takes an optional `on_units` callback (unit tests pass none; `build_services` passes `usage.count_youtube_units`). The callback upserts `youtube_quota_days` in a session of its own (the `record_call` pattern) and returns the total before and after; crossing `quota_warn_at` logs `quota.youtube_high` at WARNING once, crossing `quota_alarm_at` at ERROR once, both with used/limit and "request more quota now — the form takes weeks". A counter failure is logged and never fails the API call. `cli status` prints "YouTube today: 1,240 / 10,000". Rough capacity for the README: with official captions ≈ 255 units per video → warning near 27 new videos a day, limit near 39; without OAuth ≈ 5 units per video. The quota resets at midnight Pacific (09:00 Berlin); an exhausted quota already parks rows without losing them (`NeedsOperator`, MVP plan §9.4).
- **Confirm mails.** `send_confirm_mail` increments `confirm_mail_days` after the provider accepted the mail (own session, next to `subscription.confirm_sent`). `record_sign_up` checks the day's count *before any write*: at `confirm_mails_cap_per_day` it raises `SignUpsSuspended`, the route answers every address alike with "Gerade melden sich ungewöhnlich viele an — bitte versuch es morgen noch einmal" (no enumeration: the answer does not depend on the address), and `signup.cap_hit` is logged at ERROR once per creator and day. Crossing `confirm_mails_warn_per_day` logs `signup.volume_high` at WARNING once. A burst of concurrent requests may overshoot the cap by a few mails — it is a safety net, not an invariant. `# ponytail: fixed cap per creator; scale it with list size when a real launch is throttled by it`.
- **Honeypot.** `signup_form.html` gets a second input that people cannot see or tab into (`aria-hidden`, `tabindex="-1"`, `autocomplete="off"`, hidden by the stylesheet). A request that fills it gets the normal "Schau in dein Postfach" answer, stores nothing, sends nothing, logs `signup.honeypot`.
- **The ledger counts what failed.** `complete_json` sums `usage` over its attempts; `LLMError` carries the usage seen so far; `record_call` books it. A call that died without an answer (timeout) stays at zero tokens — nobody knows them — and is recognisable by `ok = false`.
- **Price below cost.** When a month is frozen for a creator without an override and its estimated cost (mails × `[costs]` + ledger) exceeds its price, `billing.price_below_cost` is logged at WARNING with both numbers.
- **`cli costs [--month YYYY-MM]`** — the operator's view, printed, never a page: per creator videos analysed, LLM cost from the ledger, mails (summary + confirm), estimated mail cost, price charged, difference; totals; then the three links where the truth lives (LLM usage page, mail provider invoice, Stripe) and the share formula `our estimate for him ÷ our estimate for all × the provider's invoice`.

## 7. Invoicing and the pause (M7b)

**Three daily periodic jobs**, registered in this order in `run_periodic_jobs`; each collects its creator notices and sends them after its commit (traps 1 and 27):

1. `refresh_usage` — for every creator with `billing_starts_at`: upsert the running month (counts, tier, price, `lines`); freeze every finished month that is not frozen (`frozen_at = now`; the price is fixed from this moment, a later override does not reach back). When the running month's tier rises above `announced_tier`, set it and send the notice "this month you have moved into tier M (€9)" — the manifest's "no tier jump without announcement", as far as a usage-based tier allows it.
2. `issue_invoices` — for every creator whose unbilled frozen months satisfy `pricing.due_for_invoice` (count ≥ `invoice_after_months`, or sum ≥ `invoice_at_eur`), and for `cli bill <slug>` (final invoice on termination): in one transaction insert an `invoices` row (`pending`) and attach the months. Then, resumable and each call with its own idempotency key (`inv-<id>-create`, `inv-<id>-item-<month>`, `inv-<id>-finalize`):
   - sum below €0.50 (override 0, or nothing sent) → `waived`, no Stripe call;
   - a month without a price (above the table, no override) → `NeedsOperator`, nothing attached;
   - create the draft with `collection_method=send_invoice`, `days_until_due`, `auto_advance=false`, `footer`, `rendering[pdf][page_size]=a4`, `metadata[invoice_id]`; store `stripe_invoice_id` and commit before the next call;
   - one item per month ("Oktober 2026 · 1.840 Mails · Stufe S") with `invoice=<id>` — an item without it lands on no invoice;
   - **read the draft back and compare its total with ours; on any difference stop with `NeedsOperator` and never finalize** — a draft is harmless, a finalized invoice is a legal document;
   - finalize with `auto_advance=true` (without it Stripe sends neither the invoice nor a reminder); store `number`, `hosted_url`, `due_at`; status `open`.
   Stripe forgets idempotency keys after 24 hours: a `pending` row older than that is not retried but reported (`NeedsOperator`: look at the dashboard, then finish or delete the draft by hand — the steps go into `operations.md`).
3. `sync_invoices` — `GET` every `open` invoice (a handful), take over `paid` / `void` / `uncollectible`. Then the rule, which lives here and not at Stripe (Stripe has no "overdue" state and marks uncollectible after 30 days at the earliest): an invoice unpaid at `due_at + pause_after_days_overdue − pause_warning_days` gets the heads-up notice once (`pause_warned_at`); at `due_at + pause_after_days_overdue` the creator is paused. A creator paused as `unpaid` with no such invoice left is resumed. An operator pause (`cli pause`) is never lifted by the job.

**What "paused" means** (`pause.py`): `poll_feeds` skips his sources, `due_appearances` skips his rows (no LLM cost), his stoppable mailings are cancelled and named in the pause notice (a mailing may not wait forever — trap 28); a mailing already `sending` finishes, because half a send is worse than a whole one — so `due_mailings` skips a paused creator's rows *except* `sending`. The sign-up page, the summary pages and the CSV export stay open: the list is his. On resume `resumed_at = now`, and **a video published while he was paused is back catalogue** (`is_backfill = published_at < max(source.created_at, creator.resumed_at)`, in `ingest_item` and in `enrich`'s correction): without this rule `compute_send_at` would schedule up to fifteen old videos for `now + 48 h` and his fans would get them in one burst.

**Notices** (new `NoticeKind`s, German, through `notify_creator`): `TIER_CHANGED`, `PAYMENT_OVERDUE` (which invoice, amount, payment link, the date of the pause), `PAUSED_UNPAID` (the same, what is paused, what stays open, "sobald bezahlt ist, läuft alles automatisch weiter"), `RESUMED`.

**Creator page** `GET /creator/abrechnung` (needs M7's creator area): this month as of the last refresh with its date, the tier table with his position, the agreed price next to the list price when an override exists, accrued months, "next invoice on … at the latest, or as soon as €100 are reached", every frozen month with its `lines`, every invoice with status and `hosted_url`. When paused, every creator page carries a banner with the reason and the payment link. `POST /creator/abrechnung/pruefen` (rate-limited) syncs his open invoices now and redirects back.

**The rules, in five lines, in one place** (owner requirement 2026-09-21: complete, no hidden rule, short enough to be read — "zu viel Text liest keiner"). One partial, `partials/billing_rules.html`, shown on the billing page and on the landing page next to the tier table; every number in it is rendered from `[pricing]` and `[billing]`, none is typed into the template. Draft:

> **So rechnen wir ab**
> 1. Wir zählen die Mails, die wir in deinem Namen verschicken: Zusammenfassungen und Bestätigungsmails.
> 2. Jeder Monat landet nach seiner Mailzahl in einer Stufe. Du startest in der kleinsten: 5 €.
> 3. Die Rechnung kommt nachträglich — nach sechs Monaten, oder früher, sobald 100 € zusammengekommen sind.
> 4. Bleibt eine Rechnung drei Wochen nach Fälligkeit offen, pausieren wir den Versand, mit Vorwarnung. Nach der Zahlung läuft alles von selbst weiter.
> 5. Deine Liste gehört dir: Export und Kündigung jederzeit.

The test of completeness: every rule in §1 that can change what a creator pays or receives has a line here; a rule that does not fit into these five lines is too complicated and is simplified, not footnoted. A test renders the partial with changed settings and finds the changed numbers.

**CLI**: `billing-setup <slug> --legal-name --address … [--starts]` (creates the Stripe customer with `preferred_locales=de`, idempotent per creator; sets `billing_starts_at`), `price <slug> --eur N | --list`, `pause` / `resume <slug>`, `bill <slug>`, `costs`.

## 8. Tests

Unit: tier edges (2,000 → S, 2,001 → M, above the table → none), override beats tier, zero override, `due_for_invoice` at five and six months and at €99.99 / €100; settings validation; honeypot; the cost-words test unchanged and green with the new templates.

Integration (fakes, `committed_database` where `session_scope` is involved; every new periodic job seeds `job_runs` like the existing ones — trap 15): a month frozen, then an unsubscribe-and-cleanup, a deleted appearance and a changed override → the frozen row and its `lines` are unchanged; confirm counter not incremented when the provider refuses the mail; cap → no mail, no row, the same answer for a new, a known and a blocked address; warning logged once per crossing; quota warning once per crossing, a failing counter does not fail the call; failed-call tokens reach the ledger and the daily cap; issue → crash after each Stripe call → re-run yields exactly one invoice with exactly one item per month; a month never on two invoices (two concurrent runs); total mismatch → never finalized; `auto_advance=true` and the footer present at finalize; waived below €0.50 without a Stripe call; pending older than 24 h is reported, not retried; pause only after the grace, warning exactly once, resume on `paid`, operator pause not lifted; a paused creator causes no feed request and no LLM call, a `sending` mailing completes, stoppable ones are cancelled with one notice sent after the commit; a video published during the pause becomes back catalogue; the billing page of creator A shows nothing of creator B.

Mutation probes (MVP plan §14 — rules that guard money): the month-to-invoice attachment, the compare-before-finalize guard, the `waived` branch, the grace comparison, the `sending` exception in `due_mailings`, the pause filter in `due_appearances`, the cap comparison, freeze immutability.

**Cannot be verified before go-live:** Stripe sends no mail in a sandbox, so the invoice mail and the reminders are first seen with a live account (M9); the exact permissions a restricted key needs are found in the sandbox from the error messages.

## 9. Milestones

Order: after the MVP plan's M7, first M7a, then M7b; then back to the MVP plan for M8. M7a extends M7's `cli status`, M7b builds on M7's creator area.

### M7a — Usage ledger, early warnings, operator cost view (≈ 2 sessions) — *added 2026-09-21*
Independent of Stripe and useful on its own: after it, the owner knows what each creator costs and hears about a limit before it is hit. Specification: §2–§6. Test-first throughout; the ledger fix is a bug and starts with the test that fails the way the bug fails.
- [ ] Ledger fix: `complete_json` sums `usage` over its attempts, `LLMError` carries the usage seen so far, `record_call` books it. Tests: a schema retry books both attempts; a double schema failure books both and counts against the daily cap.
- [ ] `[youtube]`, `[costs]` and the two `[web]` thresholds in `settings.toml` with start-up validation, each key with its one-line explanation (§3; a test refuses a key without one); `[costs]` joins the stale-price warning.
- [ ] Migration: `confirm_mail_days`, `youtube_quota_days`. `billing/usage.py`: `count_confirm_mail`, `count_youtube_units` (own session, never fails its caller); `YouTubeDataApi(on_units=…)` wired in `build_services`; log events `quota.youtube_high`, `signup.volume_high`, `signup.cap_hit`, `signup.honeypot`, `billing.price_below_cost` in `app/log.py`.
- [ ] Sign-up: honeypot field in `signup_form.html` (+ stylesheet rule through `app/design.py`'s conventions), cap check in `record_sign_up` before any write, `SignUpsSuspended` → the one answer for every address, counter increment after the provider accepted the mail.
- [ ] `cli costs [--month]`; `cli status` (M7) gains the quota line and today's confirm mails per creator.
- [ ] README (German): "Grenzen und Frühwarnungen" — the quota arithmetic, the two sign-up thresholds, where the warnings appear, what to do. `operations.md`: requesting quota, raising the cap before a launch.
- [ ] Tests and mutation probes as listed in §8 for this part.
- **Done when:** on a test config with `daily_quota_units = 20`, a poll produces the WARNING and then the ERROR exactly once each; with `confirm_mails_cap_per_day = 3` the fourth sign-up of the day gets the "try tomorrow" answer and no mail; `cli costs` prints, for the local test creator, an LLM figure equal to the sum of his ledger rows and a mail count equal to his sent mailings plus his confirm mails.

### M7b — Pricing, invoices, pause (≈ 4 sessions) — *added 2026-09-21*
Needs M7 (creator area) and M7a (counts). Specification: §3–§8; Stripe facts in §10. Developed entirely against `FakeStripe` and a Stripe sandbox — no activated account is needed before M9.
- [ ] `[pricing]` and `[billing]` in `settings.toml` with validation and a one-line explanation per key (§3); `billing/pricing.py` (pure) with its unit tests first.
- [ ] Migration: the `creators` columns, `billing_months`, `invoices`; `PausedReason`, `InvoiceStatus`, four new `NoticeKind`s with their German texts.
- [ ] `billing/stripe_client.py` + `FakeStripe`; `StripeClient` in `Services`; `STRIPE_API_KEY` in `Secrets`, `.env.example`, `render.yaml`, README key table (restricted key: customers, invoices, invoice items — found in the sandbox).
- [ ] `refresh_usage` (running month, freeze, tier notice), then `issue_invoices` (resumable, compare-before-finalize, `waived`, 24-hour rule), then `sync_invoices` (status, heads-up, pause, resume) as periodic jobs; notices after the commit.
- [ ] `billing/pause.py`; the pause filters in `poll_feeds`, `due_appearances`, `due_mailings` (except `sending`); `resumed_at` in the back-catalogue rule of `ingest_item` and `enrich`.
- [ ] `GET /creator/abrechnung`, `POST /creator/abrechnung/pruefen`, the paused banner, `partials/billing_rules.html` (five lines, numbers from the settings; also used by the landing page in M8); templates without any cost word.
- [ ] CLI: `billing-setup`, `price`, `pause`, `resume`, `bill`.
- [ ] Docs: ARCHITECTURE.md (module, the two new state vocabularies, a Decisions entry "invoices in arrears, no webhook"), `operations.md` (Stripe dashboard settings, a disputed invoice → credit note in the dashboard, a stuck `pending` invoice, pausing by hand), `onboarding.md` (`billing-setup`, what to tell the creator about tiers and the pause).
- [ ] Tests and mutation probes as listed in §8.
- **Done when:** in a Stripe sandbox, a test creator with three seeded months gets exactly one invoice whose PDF shows three lines, the §19 footer and the right total; marking it paid flips it to `paid` at the next sync; leaving a second one unpaid (with shortened thresholds) produces the heads-up, then the pause with cancelled mailings, and paying it resumes him without a manual step; his page shows every number the invoice was built from and no cost figure.

## 10. Verified Stripe facts

Checked on 2026-09-21 against docs.stripe.com, stripe.com/de/pricing and support.stripe.com. Where a fact could not be confirmed it is marked and turned into a sandbox task.

- One-off invoice: `POST /v1/customers` → `POST /v1/invoices` (`collection_method=send_invoice` requires `days_until_due` or `due_date`; optional `footer`, `description`, `account_tax_ids[]`, `metadata`, `rendering[pdf][page_size]=a4` — the default is Letter) → `POST /v1/invoiceitems` with `invoice=<id>` (`pending_invoice_items_behavior` defaults to `exclude`: an item without `invoice` is not picked up) → `POST /v1/invoices/{id}/finalize` (assigns number, PDF, `hosted_invoice_url`; status `open`). Up to 250 items, on drafts only. After finalize the invoice is immutable; corrections are credit notes (`POST /v1/credit_notes`, own number and PDF; one that brings an open invoice to zero makes it `paid`).
- **`auto_advance` defaults to `false` on create, and then Stripe sends no invoice mail, no reminder and runs no automation.** It can be passed to `finalize`. The mail on finalize also needs the dashboard setting "e-mail finalized invoices".
- Status is one of `draft`, `open`, `paid`, `uncollectible`, `void`; **there is no overdue status** — overdue is `open` with `due_date` in the past. Stripe can mark uncollectible after 30, 60 or 90 days, never void on its own. Reminders for one-off invoices are configured in the dashboard (Billing → Invoices); **unconfirmed:** the exact day values on offer.
- `Idempotency-Key`: POST only, up to 255 characters, kept for at least 24 hours; the same key with different parameters is an error; the first result is replayed, including a 500.
- Rate limits: 100 requests/s live, 25/s in a sandbox; a daily poll of a handful of invoices is nowhere near. `GET /v1/invoices?status=open&collection_method=send_invoice` lists them in one call.
- Amounts: minimum charge €0.50; an invoice below it goes to `paid` at once and the amount moves to the customer balance — so we never create one (§7 `waived`). **Partly confirmed:** a zero total finalizes as `paid`.
- Germany: tax id type `de_stn` (Steuernummer) as default account tax id; sequential numbering at account level is the EU default, prefix configurable, never set `number` yourself; a legal sentence goes into the default footer or the `footer` parameter. Payment methods on the hosted page for a German account: card, SEPA Direct Debit, SEPA bank transfer, PayPal (activated in live mode only).
- Fees (German price list): EEA standard cards 1.5 % + €0.25; SEPA Direct Debit €0.35 flat (failed €3.50, dispute €15); SEPA bank transfer 0.5 %, capped at €5; Invoicing Starter 0.4 % per paid invoice on top, nothing for unpaid, void or uncollectible ones. A €30 half-year invoice costs ≈ €0.82 by card, ≈ €0.47 by SEPA debit.
- Sandbox: available right after sign-up, without activation. **No e-mail is sent in test mode** (an `invoice.sent` event fires, nothing else). A paid invoice is simulated with `POST /v1/invoices/{id}/pay` and `paid_out_of_band=true`, or card 4242… on the hosted page. Test clocks are documented for subscriptions only and are not needed here.
- Restricted keys: every resource None/Read/Write. **Unconfirmed:** whether invoice items are a resource of their own and whether finalize needs more than Invoices: Write — the permission error names what is missing; build the key in the sandbox from those messages.
- Activation of a German individual account asks for name, date of birth, address, phone, a **website URL**, a product description and a bank account (taken from the Connect requirements, a proxy for direct sign-up — **unconfirmed** for the direct form). No tax number appears in that list; the invoice needs one regardless.
- No SDK is required; the SDK's only relevant extra is the automatic retry of `lock_timeout` 429s, which the client treats as a temporary error.

## 11. Risks

| Risk | Why it is real | Mitigation in this plan |
|---|---|---|
| An invoice is wrong, doubled or never sent | Money and reputation at once; `auto_advance` defaults to silence; idempotency keys expire after 24 h | Months are frozen and attach to exactly one invoice; every Stripe call has its own key; the draft's total is compared with ours before finalize; a `pending` row older than 24 h is reported, not retried; all of it pinned by mutation probes (§8). |
| Sign-up flood (bot) | Public form, loose per-IP limit; confirm mails to strangers bring complaints that hit every creator | Honeypot, warning at 500 and cap at 2,000 confirm mails per creator and day, one answer for everybody (§6); captcha in the backlog. |
| A limit stops the service unannounced | YouTube quota, mail volume | Counted in the database, WARNING at 70 %, ERROR at 90 % (§6); capacity arithmetic in the README. |
| Fixed costs outrun revenue | ≈ $27 hosting from go-live, + $20 mail plan from the first real list; small tiers leave €4–7 each | Nothing is deployed before a pilot has agreed; variable cost is covered by construction; hosting and mail provider are parked for a separate review (backlog) — the tiers follow `[costs]`. |
| A paused creator's fans get a burst of old videos on resume | `compute_send_at` floors at `now + 48 h` for every video it meets | Videos published during a pause are back catalogue (§7), tested. |

## 12. Questions — decided and open

The same questions, in German, are numbers 13–19 in `implementation-notes.html` §5.

Decided in the workshop of 2026-09-21: cost-covering tiers by mails per month, entry €5, arrears, six months or €100, Stripe only, automatic pause, confirm mails counted, safety cap. Still open:*

10. **A disputed invoice.** Assumption: the creator's page itemises every month per mailing from frozen numbers; if he still objects, the owner decides and corrects with a credit note in the Stripe dashboard — no dispute workflow in the app. **Decided 2026-09-21 by the owner: yes.**
11. **Each calendar month is priced on its own**, instead of the period average discussed in the workshop. Reason: the €100 rule ends periods early, and an average over a partial period is undefined; one line per month is also easier to check. Consequence: a creator near a tier edge can change tier from month to month. **Decided 2026-09-21 by the owner: accepted** — on the condition that the creator finds the rules complete, short and plain on his page (§7, the five lines).
12. **A month without a single mail costs the smallest tier (€5).** **Decided 2026-09-21 by the owner: yes — no special rules.** For the same reason there is no free month for a paused creator either: the tier table is the only pricing rule.
13. **While a creator is paused, his sign-up page stays open** (the list is his; confirm mails are counted and capped). **Decided 2026-09-21 by the owner: it stays open.**
14. **Defaults:** due 14 days after the invoice, heads-up 7 days before the pause, pause 21 days after the due date; confirm-mail warning at 500 and cap at 2,000 per creator and day; quota warning at 70 %, alarm at 90 %. **Decided 2026-09-21 by the owner: these values — and every one of them central, configurable and explained by a comment (§3).**
15. **Hosting and mail-provider cost** — the owner settles this outside this plan (decided 2026-09-21). Until then `[costs]` holds the current provider's overage price, the conservative case.
16. **Business registration and tax number** — no invoice without them (MVP plan §17, M9 checklist). Development and sandbox tests do not wait for it.
17. **Confirmed by the owner on 2026-09-21:** the seven tiers and their prices as in §1; €5 keep accruing while a creator is paused (no special rules); a tier change during the month is announced by one short mail (§7 `TIER_CHANGED`); invoices offer SEPA Direct Debit and card, no PayPal, no bank transfer.
