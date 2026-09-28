# Backlog — everything deliberately left for after the MVP

The MVP plan (`docs/plans/2026-09-mvp-implementation-plan.md`) builds Phase 1
and nothing more. Everything that was considered and consciously deferred is
collected here, so that a good idea is postponed, not forgotten.

**Rule:** nothing here is built before its trigger fires (manifest §10: "Es wird
nicht vorgebaut"). When an item is picked up, it moves into a plan and is
struck from this list. Anyone who defers something — in a plan, a review, or a
`# ponytail:` comment — adds a line here in the same change.

## Where the other future lists live

| What | Authority |
|---|---|
| Product ideas for creators and fans (chat assistant, discussion area, monthly digest, question radar, quote cards …) — also the source of the website's roadmap | Manifest §12 "Zukunftsliste" |
| What each phase adds (multi-tenancy, fan dashboard, briefings, podcast connector …) | Manifest §10 "Roadmap & Meilensteine" |
| Open decisions for the owner | Plan §20 and `implementation-notes.html` §5 |

## Deferred features

| Item | Trigger — build it when … | Notes / origin |
|---|---|---|
| **Self-service re-verification for blocked fans** | the first support request of a fan whose mailbox works again, or when manual unblocking becomes a monthly chore | Today the operator unblocks by hand (ARCHITECTURE.md → "The fan area"). Needs a way to lift the provider's suppression (since 2026-09-27: SES's account suppression list) that does not put a broader credential in the web process — e.g. an operator CLI with an IAM key that lives only on the operator's machine and may call `sesv2:DeleteSuppressedDestination`. Owner decision 2026-09-18. |
| PubSubHubbub push for new uploads | a creator needs detection faster than the six-hourly poll | Plan header, §17 "Post-go-live"; verified hub facts in plan §18. |
| Map-reduce summarisation | a real video exceeds `content.max_transcript_chars` | Plan header; today such a video is skipped and the creator notified. |
| Whisper transcription | the podcast connector arrives (Phase 2), or captions are missing too often | Plan header, manifest §7.4. |
| Feature voting on the landing page | the roadmap section exists (M8) and there is more than one creator to ask | Manifest §5.6; plan header. |
| Logo upload | a creator has no public logo URL | Plan header; today the logo is a URL, defaulting to the YouTube avatar. |
| "Alle abbestellen" across creators | the fan dashboard arrives (Phase 2) | Plan header; unsubscribing is per creator today. |
| Open and click tracking | the owner decides to measure the manifest §6.3 open-rate criterion in-house | Plan §20 question 4; off by default for privacy and deliverability. |
| Self-service onboarding, checkout, stored payment methods, customer portal | Phase 2 | Manifest §4.4. *Changed 2026-09-21:* invoicing in arrears moved into the MVP (`docs/plans/2026-09-billing-plan.md`, M7b); what stays here is everything a creator would do without the operator. |
| Stronger credentials than static API keys | before go-live (M9) for the cheap parts; federated, keyless access when a provider offers it for server-to-server calls | Owner question 2026-09-19. Static keys are acceptable for the MVP but must be: one key per environment, restricted (YouTube key to the YouTube Data API v3; Anthropic key scoped to a workspace with a spend limit; SES SMTP user allowed only `ses:SendRawEmail` on the identity and the From domain — SES plan §9 step 7), rotated on a schedule and after any leak. Evaluate short-lived, federated credentials (OIDC / workload identity from the hosting platform) where Google, Anthropic or AWS support them for this use; OAuth already carries the one call that needs the creator's own authority (captions). |
| Move hosting to a VPS (`docker compose` + Caddy + restic; e.g. netcup, ≈ €7) | the Render bill passes €25 a month without a matching rise in revenue, Render's terms or prices change, or a customer requires an EU-owned processor | MVP plan §15.2: the same image and compose file run there; one day of setup, then ≈ 15–30 minutes a month. Hetzner restricted new servers in 2026 — check again when triggered. |
| Infrastructure as code for the AWS/SES setup (OpenTofu, `hashicorp/aws`) | a second environment (staging), or the account has to be rebuilt | SES plan §9: eleven steps, done once by hand; the provider covers all but production access and the pricing plan. |
| Automatic warning when the lists approach SES's daily quota | the largest day's sending passes half the quota | SES plan §9 step 10: checked monthly on the SES dashboard today. The billing plan's quota counter covers YouTube only. |
| Operator command to send an uncertain delivery again | an uncertain delivery happens more than once a month, or fans ask about missing mails | SES plan §5: today the operator mails that fan the summary page link by hand. |
| Remotion company licence | the business has more than three employees and the video is re-rendered | MVP plan §17 M10; the free licence covers up to three. |
| High availability: two instances and a high-availability database (from ≈ €60/month) | sign-ups or creator actions lost to downtime become measurable, or a customer contract demands an uptime figure | Operations plan §8: today composure instead of redundancy — resume from the database, self-restarting worker, alerts from outside. |
| Log stream to an external provider (full log text beyond 7 days) | a question about an event older than a week that the incident list cannot answer | Operations plan §8: incidents are kept 180 days in the database; Render keeps logs 7 days on Hobby. |
| A deploy workflow that waits for the quiet window before deploying | a deploy measurably delayed or disturbed a send | Operations plan §7.1: designed and dropped 2026-09-27 — deploys are safe by design, Render deploys after CI (`checksPass`); the quiet window is shown on the console and in the daily mail. |
| Actions in the operator console (reset a failed row, send again to one fan, unpark) | the same runbook SQL is typed more than once a month | Operations plan §5: the console is read-only except "erledigt"; actions are CLI and runbook today. |
| Worker as its own Render service again (+$7) | the shared container's memory runs out, or a long send noticeably slows the web process | Lean-platform plan §3: measured before M6b closes; reduce first. |
| Longer history of per-mail delivery status | a question about a mail older than Render's log retention, or a creator asks for delivery numbers | SES plan §6.2: today the status lives in the logs only. A `deliveries` column or a log drain would keep it. |
| A design tool (Penpot, free and open source) | the owner wants to explore layouts on a canvas, or a designer joins | MVP plan §17 D: today the drafts are the real templates, reviewed in the browser. |
| Infrastructure as code for the Render and B2 setup | a second environment | `render.yaml` already describes the services; B2 and the monitoring accounts are set up by hand from `operations.md`. |
| Captcha on the sign-up form | the daily confirm-mail cap is hit by a real attack, not by a launch | Billing plan §6: honeypot, warning and cap come first; a captcha costs every fan a step and brings a third party onto the page. |
| Stripe webhook instead of the daily poll | a creator complains about the delay between paying and resuming, or open invoices pass ≈ 50 | Billing plan §1 point 8: polling needs no public endpoint and no signature handling; the "check now" button covers the impatient case. |
| Metered price per mail instead of tiers | hand-set overrides become a chore (≈ 10 creators), or tier edges cause disputes | Billing plan §1 "Rejected alternatives". |
| Per-creator attribution of YouTube quota | the quota warning fires and the log does not make the cause obvious | Billing plan §6 counts units per day for the whole project; the call sites that know the creator are `enrich`, `poll_feeds` and the cleanup re-check. |

## Deliberate shortcuts in the code

Each is a `# ponytail:` comment at the named place; the comment is the authority
for its ceiling. Find them all with `grep -rn "ponytail:" src/`.

| Where | Ceiling today | Upgrade when … |
|---|---|---|
| `worker.py` | one sequential worker, the only step runner | one channel's volume no longer fits one loop → `FOR UPDATE SKIP LOCKED` and a second worker |
| `worker.py` (periodic jobs) | a job killed mid-run waits a full interval | a job becomes expensive to miss |
| `services.py` | process-global service override for tests | a second process model appears |
| `sources/youtube/feed.py` | a channel with more than 15 uploads between two polls loses items | such a channel is onboarded → fall back to `playlistItems` |
| `jobs/steps.py` (`poll_feeds`) | the six-hourly poll is the only upload trigger | see PubSubHubbub above |
| `analysis/summarize.py` | single-call summarisation | see map-reduce above |
| `db/models.py` (`analyses`) | one analysis per kind, no history | prompts are A/B-compared in production |
| `db/models.py` (`deliveries`) | no per-delivery delivered/bounced state, no provider id | the Phase-2 analytics dashboard |
| `delivery/email_client.py` (`SmtpClient`) | any 5xx from SES stops the whole mailing (*Changed 2026-09-27*, was `send_batch`) | it happens once → per-address handling |
| `delivery/sns.py` | the SNS signing-certificate cache is unbounded (one entry per URL) | AWS rotates the certificate more than a handful of times a year |
| `ops/start.sh` | web and worker share one container; a crashed worker is restarted in place, a crashed web process restarts both | the worker needs its own resources (see "Worker as its own Render service") |
| `delivery/mailing.py` (`send_batches`) | a whole list is sent inside one worker tick (≈ 12 min per 10,000 at 14/s) | lists grow so large that other rows wait noticeably → send one page per tick |
| `web/routes/fan.py` (`/s/`) | no per-state visibility check on summary pages | view tokens leave mails, previews and the confirmation page |
| `addresses.py` | the local part is lower-cased too | a real provider turns out to be case-sensitive |
| `subscriptions.py` (`send_confirm_mail`) | "send after the answer, undo on failure" is written twice (confirm mail, magic link) | a third mail *sent after an HTTP answer* needs it — the contact form (M8) → one `send_or_undo` helper. The M6 preview is not one: it is sent by the worker inside its transaction, and a failure rolls back and retries (checked 2026-09-18). |

## Known limits, accepted for now

| Limit | Why it is acceptable today | Revisit when … |
|---|---|---|
| A fan blocked (bounce, complaint) mid-send is dropped from the remaining batches, while one who unsubscribes still gets the mail | a complaint costs the sending reputation of every creator; an unsubscribe does not (owner decisions 2026-09-18 and 2026-09-20) | the two ever need to behave the same |
| A fan who unsubscribes while a mailing is sending still gets that one mail | re-filtering each batch would break the payload freeze (plan §8.4); **owner decision 2026-09-18** | a complaint from exactly this case |
| A send's retry ladder resets only on progress: ten temporary failures **in a row, without a single mail going out in between**, end the mailing (*corrected 2026-09-27*: this row used to say every failure counts; the code and ARCHITECTURE reset the ladder whenever a batch — from M6a: a mail — goes out) | ten failures without any progress in about a day mean something is badly wrong; the mailing resumes where it stopped once the operator resets it | a flaky provider ends sends that were still making slow progress |
| Background mail tasks share the web process's thread pool; a slow provider holds a slot for up to 30 s | one creator, a handful of sign-ups a minute | sign-up volume makes the pool a bottleneck → a small outbox table sent by the worker |
| A throttled confirm mail (an SMTP `4xx` from SES) is not retried; the fan simply submits again | the brake is released on failure, so the retry works | confirm mails start failing in bursts |
| `--forwarded-allow-ips='*'` makes the per-IP limit forgeable | the per-address brake does not depend on the IP | before go-live: set Render's proxy addresses (notes question 9, M9) |
