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
| `subscriptions.py` (`send_confirm_mail`) | "send after the answer, undo on failure" is written twice (confirm mail, magic link) | a third mail needs it (M6 preview, contact form) → one `send_or_undo` helper |

## Known limits, accepted for now

| Limit | Why it is acceptable today | Revisit when … |
|---|---|---|
| A fan who unsubscribes while a mailing is sending still gets that one mail | re-filtering each batch would break the payload freeze (plan §8.4) | plan §20 question 9 is answered otherwise |
| Background mail tasks share the web process's thread pool; a slow provider holds a slot for up to 30 s | one creator, a handful of sign-ups a minute | sign-up volume makes the pool a bottleneck → a small outbox table sent by the worker |
| A Resend 429 on a confirm mail is not retried; the fan simply submits again | the brake is released on failure, so the retry works | confirm mails start failing in bursts |
| `--forwarded-allow-ips='*'` makes the per-IP limit forgeable | the per-address brake does not depend on the IP | before go-live: set Render's proxy addresses (notes question 9, M9) |
