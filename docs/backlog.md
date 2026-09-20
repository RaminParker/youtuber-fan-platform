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
| **Self-service re-verification for blocked fans** | the first support request of a fan whose mailbox works again, or when manual unblocking becomes a monthly chore | Today the operator unblocks by hand (ARCHITECTURE.md → "The fan area"). Needs a way to lift Resend's suppression that does not put a full-access key in the web process — e.g. an operator CLI with a key that lives only on the operator's machine, or a Resend API scope that allows it. Owner decision 2026-09-18. |
| PubSubHubbub push for new uploads | a creator needs detection faster than the six-hourly poll | Plan header, §17 "Post-go-live"; verified hub facts in plan §18. |
| Map-reduce summarisation | a real video exceeds `content.max_transcript_chars` | Plan header; today such a video is skipped and the creator notified. |
| Whisper transcription | the podcast connector arrives (Phase 2), or captions are missing too often | Plan header, manifest §7.4. |
| Feature voting on the landing page | the roadmap section exists (M8) and there is more than one creator to ask | Manifest §5.6; plan header. |
| Logo upload | a creator has no public logo URL | Plan header; today the logo is a URL, defaulting to the YouTube avatar. |
| "Alle abbestellen" across creators | the fan dashboard arrives (Phase 2) | Plan header; unsubscribing is per creator today. |
| Open and click tracking | the owner decides to measure the manifest §6.3 open-rate criterion in-house | Plan §20 question 4; off by default for privacy and deliverability. |
| Stripe billing and self-service onboarding | Phase 2 | Manifest §4.4. |
| **Kostenübersicht pro Creator, für den Betreiber** | before the second paying creator, or before the first price is quoted — whichever comes first | Owner request 2026-09-20: "ich muss abschätzen können, wie teuer jeder Kunde ist, sonst zahle ich drauf." **What the provider can and cannot answer** (checked against its Usage & Cost API docs, 2026-09-20): usage in tokens groups by model, API key, workspace and period; **cost in dollars groups only by workspace**, never by API key; both need an Admin key and an organisation (not available for individual accounts). The provider knows nothing about creators — a creator only becomes visible there if each one gets their own workspace and key, which costs a workspace, a key and a gateway routing rule per onboarding. **So the split stays ours:** `llm_calls` records `creator_id` per call, and the invoice supplies the scale — `share of creator = (our estimate for them ÷ our estimate for all) × invoice total`. Only the *ratio* has to be right, and it is, because tokens are counted rather than guessed; a stale price cancels out. The provider itself recommends tokens as the cost proxy when many keys are involved. **Smallest useful step:** `cli status` (M7) prints per creator and month: LLM cost from the ledger, mails sent from `deliveries`, videos processed, plus the link to the invoice. **Later, if it earns it:** a page behind the operator login with the same numbers and deep links, never mirrored data. Per-creator workspaces become interesting when a customer disputes an invoice or customers differ wildly in size. Costs stay operator-only — no page, no mail (a test enforces it). |
| Stronger credentials than static API keys | before go-live (M9) for the cheap parts; federated, keyless access when a provider offers it for server-to-server calls | Owner question 2026-09-19. Static keys are acceptable for the MVP but must be: one key per environment, restricted (YouTube key to the YouTube Data API v3; Anthropic key scoped to a workspace with a spend limit; Resend key sending-only and domain-bound — plan §17 M9), rotated on a schedule and after any leak. Evaluate short-lived, federated credentials (OIDC / workload identity from the hosting platform) where Google, Anthropic or Resend support them for this use; OAuth already carries the one call that needs the creator's own authority (captions). |

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
| `delivery/email_client.py` (`send_batch`) | one address the provider rejects blocks a whole mailing | it happens once → per-address handling |
| `web/routes/fan.py` (`/s/`) | no per-state visibility check on summary pages | view tokens leave mails, previews and the confirmation page |
| `addresses.py` | the local part is lower-cased too | a real provider turns out to be case-sensitive |
| `subscriptions.py` (`send_confirm_mail`) | "send after the answer, undo on failure" is written twice (confirm mail, magic link) | a third mail *sent after an HTTP answer* needs it — the contact form (M8) → one `send_or_undo` helper. The M6 preview is not one: it is sent by the worker inside its transaction, and a failure rolls back and retries (checked 2026-09-18). |

## Known limits, accepted for now

| Limit | Why it is acceptable today | Revisit when … |
|---|---|---|
| A fan blocked (bounce, complaint) mid-send is dropped from the remaining batches, while one who unsubscribes still gets the mail | a complaint costs the sending reputation of every creator; an unsubscribe does not (owner decisions 2026-09-18 and 2026-09-20) | the two ever need to behave the same |
| A fan who unsubscribes while a mailing is sending still gets that one mail | re-filtering each batch would break the payload freeze (plan §8.4); **owner decision 2026-09-18** | a complaint from exactly this case |
| The retry ladder of a send counts every failed attempt, even when batches in between went through | ten failures in about a day mean something is badly wrong; the mailing resumes where it stopped once the operator resets it | long lists meet a flaky provider and `failed` sends show up with most deliveries done |
| Background mail tasks share the web process's thread pool; a slow provider holds a slot for up to 30 s | one creator, a handful of sign-ups a minute | sign-up volume makes the pool a bottleneck → a small outbox table sent by the worker |
| A Resend 429 on a confirm mail is not retried; the fan simply submits again | the brake is released on failure, so the retry works | confirm mails start failing in bursts |
| `--forwarded-allow-ips='*'` makes the per-IP limit forgeable | the per-address brake does not depend on the IP | before go-live: set Render's proxy addresses (notes question 9, M9) |
