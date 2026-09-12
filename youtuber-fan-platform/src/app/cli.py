"""Operator commands. argparse, and one function call per subcommand.

The commands are deliberately thin: the work lives in the layer that owns it,
and this module only parses arguments and prints results.

One rule holds throughout: **the CLI never runs a pipeline step.** It ingests
and it reports; the worker is the single process that executes steps. A second
runner would happily repeat an expensive step on a row the worker is already
working on.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import log
from app.analysis.llm import LLMError, cost_cents
from app.analysis.stored import load_analysis
from app.analysis.summarize import summarise
from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    Creator,
    Source,
    SourceKind,
)
from app.delivery.email_client import EmailError
from app.delivery.render import OutgoingEmail, render_summary_mail
from app.errors import TemporaryError
from app.jobs import steps
from app.services import get_services
from app.sources.youtube import feed as youtube_feed
from app.sources.youtube.data_api import YouTubeError
from app.sources.youtube.oauth import GrantRevoked
from app.transcripts.srt import parse_srt

#: The fixed set the prompts are judged against, kept with the tests because
#: that is where the other fixtures live.
SAMPLE_TRANSCRIPTS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "transcripts"

logger = log.get_logger(__name__)


def find_creator(session: Session, slug: str) -> Creator:
    """Look a creator up by slug, or exit with a readable message."""
    creator = session.scalar(select(Creator).where(Creator.slug == slug))
    if creator is None:
        sys.exit(f"No creator with slug {slug!r}.")
    return creator


def source_of(session: Session, creator: Creator) -> Source:
    """Return the creator's source, or exit with a readable message."""
    source = session.scalar(select(Source).where(Source.creator_id == creator.id))
    if source is None:
        sys.exit(f"Creator {creator.slug!r} has no source yet.")
    return source


def handle_onboard(args: argparse.Namespace) -> None:
    """Create a creator and their source, and print the sign-up link."""
    settings = get_settings()
    profile = get_services().youtube.source_profile(args.channel_id)
    if profile is None:
        sys.exit(f"No channel with id {args.channel_id!r}.")

    with session_scope() as session:
        creator = Creator(
            slug=args.slug,
            name=args.name,
            contact_email=args.email.lower(),
            # The channel's own avatar is a better default than no logo at all,
            # and the creator can replace it on the settings page.
            logo_url=profile.avatar_url,
        )
        session.add(creator)
        session.flush()
        session.add(
            Source(
                creator_id=creator.id,
                kind=SourceKind.YOUTUBE,
                external_id=args.channel_id,
                title=profile.title,
            )
        )

    print(f"Onboarded {args.name} ({profile.title}).")
    print(f"Sign-up page: {settings.base_url}/k/{args.slug}")


def handle_poll(args: argparse.Namespace) -> None:
    """Fetch the source's feed once and ingest what is new."""
    with session_scope() as session:
        source = source_of(session, find_creator(session, args.slug))
        entries = youtube_feed.fetch_feed(source.external_id)
        ingested = [
            steps.ingest_item(
                session,
                source,
                external_id=entry.video_id,
                title=entry.title,
                url=entry.url,
                published_at=entry.published_at,
            )
            for entry in entries
        ]

    found = sum(1 for appearance in ingested if appearance is not None)
    print(f"{len(entries)} entries in the feed, {found} newly recorded.")
    print("The worker picks them up on its next tick.")


def handle_process(args: argparse.Namespace) -> None:
    """Ingest one specific item, back catalogue included."""
    items = get_services().youtube.item_details([args.video_id])
    if not items:
        sys.exit(f"No video with id {args.video_id!r}.")
    item = items[0]

    with session_scope() as session:
        source = source_of(session, find_creator(session, args.slug))
        appearance = steps.ingest_item(
            session,
            source,
            external_id=item.external_id,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            allow_backlog=True,
        )

    if appearance is None:
        print(f"{item.title!r} was already recorded; nothing to do.")
        return
    print(f"Recorded {item.title!r}. The worker picks it up on its next tick.")


def handle_backfill(args: argparse.Namespace) -> None:
    """Ingest the creator's recent videos so their pages exist from day one.

    Nothing is mailed: these are older than the source, so the pipeline files
    them as back catalogue. The point is that the creator can judge the quality
    on their own videos before a single fan hears about it.
    """
    settings = get_settings()
    count = args.count or settings.content.backfill_count

    with session_scope() as session:
        source = source_of(session, find_creator(session, args.slug))
        items = get_services().youtube.latest_items(source.external_id, count)
        ingested = [
            steps.ingest_item(
                session,
                source,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                published_at=item.published_at,
                allow_backlog=True,
            )
            for item in items
        ]

    found = sum(1 for appearance in ingested if appearance is not None)
    print(f"{len(items)} videos found, {found} newly recorded.")
    print("The worker processes them; nothing is mailed.")


def handle_demo_mails(args: argparse.Namespace) -> None:
    """Render the newest analysed videos as mails, in all three variants.

    This is what the Phase 0 conversation is held with: real summaries of the
    candidate's own videos, in every format they could choose.
    """
    settings = get_settings()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with session_scope() as session:
        creator = find_creator(session, args.slug)
        source = source_of(session, creator)
        analysed = session.scalars(
            select(Appearance)
            .where(
                Appearance.source_id == source.id,
                Appearance.status == AppearanceStatus.ANALYZED,
            )
            .order_by(Appearance.published_at.desc())
            .limit(args.count)
        ).all()

        if not analysed:
            sys.exit(f"No analysed videos for {args.slug!r} yet. Run `backfill` and wait.")

        for appearance in analysed:
            summary = load_analysis(session, appearance.id, AnalysisKind.SUMMARY)
            sentiment = load_analysis(session, appearance.id, AnalysisKind.SENTIMENT)
            for variant in settings.email.variants:
                mail = render_summary_mail(
                    creator=creator,
                    appearance=appearance,
                    summary=summary,
                    sentiment=sentiment,
                    subscription=None,
                    settings=settings,
                    variant=variant,
                    stop_token="demo",
                    send_at=datetime.now(UTC),
                    view_url=f"{settings.base_url}/s/{appearance.view_token}",
                )
                stem = f"{appearance.external_id}.{variant}"
                (out / f"{stem}.html").write_text(mail.html, encoding="utf-8")
                (out / f"{stem}.txt").write_text(mail.text, encoding="utf-8")
                print(f"  {out}/{stem}.html")
                if args.send_to:
                    get_services().email.send(
                        OutgoingEmail(**{**mail.__dict__, "to": args.send_to})
                    )

    if args.send_to:
        print(f"Also sent to {args.send_to}.")


def handle_eval_prompts(args: argparse.Namespace) -> None:
    """Run the current prompts over the fixed sample transcripts and write the results.

    Manifest §8: prompts are product. This is the cheapest quality assurance
    there is — run it before changing a prompt version, read the output, and
    decide whether the new version is actually better. It costs real money, so
    it is a command and not a test.
    """
    settings = get_settings()
    transcripts = sorted(SAMPLE_TRANSCRIPTS.glob("*.srt"))
    if not transcripts:
        sys.exit(f"No sample transcripts in {SAMPLE_TRANSCRIPTS}.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for path in transcripts:
        segments = parse_srt(path.read_text(encoding="utf-8"))
        print(f"{path.name}: {len(segments)} segments, summarising…")
        completion = summarise(
            get_services().llm,
            segments,
            title=path.stem.replace("_", " "),
            channel=args.channel,
            settings=settings,
        )
        summary = completion.result
        target = out / f"{path.stem}.{settings.llm.summary_prompt_version}.md"
        target.write_text(_as_markdown(path.stem, summary, completion), encoding="utf-8")
        print(
            f"  -> {target}  "
            f"({completion.tokens_in} in, {completion.tokens_out} out, "
            f"{cost_cents(settings.llm.model_summary, completion.tokens_in, completion.tokens_out, settings):.2f} cents)"
        )


def _as_markdown(name: str, summary, completion) -> str:
    """Render one summary for a human to read and judge."""
    lines = [
        f"# {summary.headline}",
        "",
        f"*{name} — {completion.model}, {completion.tokens_in} in / {completion.tokens_out} out*",
        "",
        f"**Sprache:** {summary.language}",
        "",
        "## Kernaussage",
        summary.core_message,
        "",
        "## Kernpunkte",
    ]
    lines += [
        f"- {point.text}" + (f"  _[{point.timestamp_seconds}s]_" if point.timestamp_seconds else "")
        for point in summary.key_points
    ]
    lines += ["", "## Abschnitte"]
    for section in summary.sections:
        lines += [f"### {section.title}"]
        lines += [f"- {point.text}" for point in section.key_points]
    lines += ["", "## Zitat", f"> {summary.quote}"]
    if summary.quote_timestamp_seconds:
        lines += ["", f"_bei {summary.quote_timestamp_seconds}s_"]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(prog="app", description=__doc__.splitlines()[0])
    subcommands = parser.add_subparsers(dest="command", required=True)

    onboard = subcommands.add_parser("onboard", help="create a creator and their source")
    onboard.add_argument("--slug", required=True, help="the sign-up URL segment")
    onboard.add_argument("--name", required=True, help="shown to fans in every mail")
    onboard.add_argument("--email", required=True, help="login and notices")
    onboard.add_argument("--channel-id", required=True, help="the UC… channel id")
    onboard.set_defaults(handler=handle_onboard)

    poll = subcommands.add_parser("poll", help="read the feed once, now")
    poll.add_argument("slug")
    poll.set_defaults(handler=handle_poll)

    process = subcommands.add_parser("process", help="ingest one item by id")
    process.add_argument("slug")
    process.add_argument("video_id")
    process.set_defaults(handler=handle_process)

    backfill = subcommands.add_parser("backfill", help="ingest the recent back catalogue")
    backfill.add_argument("slug")
    backfill.add_argument("--count", type=int, default=None, help="how many videos")
    backfill.set_defaults(handler=handle_backfill)

    demo = subcommands.add_parser("demo-mails", help="render mails for the sales conversation")
    demo.add_argument("slug")
    demo.add_argument("--count", type=int, default=3, help="how many videos")
    demo.add_argument("--out", default="out", help="where to write them")
    demo.add_argument("--send-to", default="", help="also send them to this address")
    demo.set_defaults(handler=handle_demo_mails)

    evaluate = subcommands.add_parser(
        "eval-prompts", help="run the current prompts over the sample transcripts"
    )
    evaluate.add_argument("--out", default="out", help="where to write the rendered summaries")
    evaluate.add_argument("--channel", default="Beispielkanal", help="channel name for the prompt")
    evaluate.set_defaults(handler=handle_eval_prompts)

    return parser


#: What is almost certainly missing when a given layer refuses to work. An
#: operator running `onboard` for the first time should be told which key to
#: put in `.env`, not shown a stack trace from inside an HTTP client.
MISSING_KEY_HINTS = {
    "app.sources.youtube": "YOUTUBE_API_KEY (and for captions GOOGLE_OAUTH_CLIENT_ID/_SECRET)",
    "app.analysis": "ANTHROPIC_API_KEY and LLM_GATEWAY_URL/_KEY",
    "app.delivery": "RESEND_API_KEY",
}


def explain(error: Exception) -> str:
    """Turn an expected operational failure into something worth reading."""
    module = type(error).__module__
    hint = next((h for prefix, h in MISSING_KEY_HINTS.items() if module.startswith(prefix)), "")
    lines = [f"{type(error).__name__}: {error}"]
    if hint:
        lines += ["", f"This usually means a missing or wrong key in .env: {hint}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Parse the arguments and run the chosen command."""
    log.configure_logging(get_settings())
    args = build_parser().parse_args(argv)
    log.bind(command=args.command, at=datetime.now(UTC).isoformat())
    try:
        args.handler(args)
    except (TemporaryError, YouTubeError, LLMError, EmailError, GrantRevoked) as error:
        # These are the ways the outside world says no. A traceback would tell
        # the operator nothing they can act on; a bug still gets one.
        sys.exit(explain(error))


if __name__ == "__main__":
    main()
