"""The worker process: one loop, one thing at a time.

There is no queue library. The state of every piece of work already lives in
``appearances.status`` and ``mailings.status``; a queue would duplicate it and
add tables, a connector and LISTEN/NOTIFY semantics on top. The loop looks for
rows that are due, runs their step, and sleeps. A crash anywhere resumes at the
next tick, because every step re-reads its row before acting.

``# ponytail: one sequential worker, and the only process that runs steps (the
CLI ingests, it never executes). Add SELECT … FOR UPDATE SKIP LOCKED and a
second worker when one channel's volume stops fitting.``
"""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import FrameType

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import log
from app.config import Settings, get_settings
from app.db.engine import session_scope
from app.db.models import Appearance, AppearanceStatus, Creator, NoticeKind, Source
from app.errors import CostCapExceeded, TemporaryError
from app.jobs import steps
from app.jobs.schedule import WAIT_FOR_THE_WORLD, has_attempts_left, retry_at

#: How much of an exception message the row keeps for the operator.
ERROR_LENGTH = 2000

logger = log.get_logger(__name__)

#: Which step advances a row in which status. A status that is absent here is
#: terminal, or is waited on by something other than the appearance loop.
APPEARANCE_STEPS: dict[str, Callable[[Session, int, datetime], None]] = {
    AppearanceStatus.DETECTED: steps.enrich,
    AppearanceStatus.ENRICHED: steps.transcribe,
    AppearanceStatus.TRANSCRIBED: steps.summarize,
}

_stopping = False
#: Set by the signal handler so the loop's wait ends at once.
_wake = threading.Event()


def handle_stop_signal(signum: int, frame: FrameType | None) -> None:
    """Finish the current tick, then leave the loop.

    The hosting platform sends SIGTERM on every deploy; killing a step halfway
    through would strand a row until its retry falls due.
    """
    global _stopping
    _stopping = True
    _wake.set()
    logger.info(log.WORKER_STOPPING, signal=signal.Signals(signum).name)


def due_appearances(session: Session, now: datetime) -> list[tuple[int, str]]:
    """Return the id and status of every appearance whose step may run now."""
    statement = (
        select(Appearance.id, Appearance.status)
        .where(
            Appearance.status.in_(list(APPEARANCE_STEPS)),
            or_(Appearance.next_attempt_at.is_(None), Appearance.next_attempt_at <= now),
        )
        .order_by(Appearance.id)
    )
    return [(row.id, row.status) for row in session.execute(statement)]


def run_appearance_step(appearance_id: int, status: str, now: datetime) -> None:
    """Run one step in its own transaction and record whatever comes of it.

    Each step commits on its own, so one bad row never rolls back the work done
    for the others in the same tick.
    """
    log.bind(appearance_id=appearance_id, step=status)
    try:
        with session_scope() as session:
            APPEARANCE_STEPS[status](session, appearance_id, now)
    except Exception as error:
        record_outcome(appearance_id, now, error)
    finally:
        log.clear_context()


def record_outcome(appearance_id: int, now: datetime, error: Exception) -> None:
    """Turn a failed step into the right bookkeeping, in a session of its own.

    The separate session is not optional: the step's transaction has just been
    rolled back by the very failure being recorded.

    Three outcomes, one place:

    - **Wait.** The cost cap is not an error, it is a clock. Counting it would
      give a row up for having been expensive on one busy day.
    - **Retry.** A temporary failure costs an attempt and gets a later slot.
    - **Give up.** Either the ladder is exhausted or the failure is one no
      repetition improves — a revoked key, a model that will not fill the
      schema. Both end the row, and both tell the creator.

    They are one function because the notice belongs to the *state*, not to the
    route into it: with two recorders, the path that reaches ``failed`` through
    the retry ladder stayed silent while the notice text — "wir haben es
    mehrfach versucht" — was written for exactly that path.
    """
    with session_scope() as session:
        appearance = session.get(Appearance, appearance_id)
        if appearance is None:
            return

        if isinstance(error, CostCapExceeded):
            appearance.next_attempt_at = now + WAIT_FOR_THE_WORLD
            logger.warning(log.LLM_COST_CAP_HIT, error=str(error))
            return

        appearance.last_error = f"{type(error).__name__}: {error}"[:ERROR_LENGTH]

        if isinstance(error, TemporaryError):
            appearance.attempts += 1
            if has_attempts_left(appearance.attempts):
                appearance.next_attempt_at = retry_at(appearance.attempts, now)
                logger.warning(
                    log.STEP_RETRY,
                    attempt=appearance.attempts,
                    next_attempt_at=appearance.next_attempt_at,
                    error=str(error),
                )
                return
        else:
            logger.exception(log.ITEM_FAILED)

        _give_up(session, appearance, error)


def _give_up(session: Session, appearance: Appearance, error: Exception) -> None:
    """End the row and tell the creator. The one place ``failed`` is written."""
    steps.mark_failed(appearance)
    logger.error(log.ITEM_FAILED, attempts=appearance.attempts, error=str(error))

    source = session.get(Source, appearance.source_id)
    creator = session.get(Creator, source.creator_id) if source else None
    if creator is not None:
        steps.notify_creator(
            creator,
            NoticeKind.FAILED,
            video_title=appearance.title,
            appearance_id=appearance.id,
        )


def run_due_steps(now: datetime) -> int:
    """Run every appearance step that is due. Returns how many ran."""
    with session_scope() as session:
        due = due_appearances(session, now)
    for appearance_id, status in due:
        try:
            run_appearance_step(appearance_id, status, now)
        except Exception:
            # The step handlers above already record what they can; this is the
            # backstop for a failure while recording. One row must never cost
            # the others their turn.
            logger.exception(log.WORKER_STEP_CRASHED, appearance_id=appearance_id)
    return len(due)


#: The manifest's retention periods are days; a daily sweep honours them.
CLEANUP_EVERY = timedelta(days=1)


def run_periodic_jobs(now: datetime, settings: Settings) -> None:
    """Run the jobs that go by the clock rather than by a row's status.

    A due run is recorded — and committed — before the job starts. A job that
    then fails, for any reason, waits for its interval like one that succeeded:
    otherwise an unexpected error turns a six-hourly poll into a once-a-minute
    one with a traceback each time. Each job has its own transaction, so one
    failing never costs another its run.

    ``# ponytail: a job killed mid-run waits a full interval; both are
    idempotent sweeps, so the next run catches up.``
    """
    jobs = (
        (
            steps.POLL_FEEDS,
            timedelta(hours=settings.worker.feed_poll_hours),
            lambda session: steps.poll_feeds(session, now),
        ),
        (steps.CLEANUP, CLEANUP_EVERY, lambda session: steps.cleanup(session, now, settings)),
    )
    for name, every, run in jobs:
        try:
            with session_scope() as session:
                if not steps.job_is_due(session, name, now, every):
                    continue
                steps.record_run(session, name, now)
            with session_scope() as session:
                run(session)
        except Exception:
            logger.exception(log.WORKER_PERIODIC_FAILED, job=name)


def run_tick(now: datetime, settings: Settings | None = None) -> None:
    """Run everything that is due at ``now``.

    ``now`` is passed in rather than read inside, which is what lets the tests
    drive the whole pipeline with a stepped clock.

    Parameters
    ----------
    now
        The current time, in UTC.
    settings
        Overrides the process-wide settings. Only tests pass this.
    """
    settings = settings or get_settings()
    started = time.monotonic()
    # Due work first, periodic jobs second, as the plan specifies: a failing
    # poll must never cost the pipeline its tick.
    ran = run_due_steps(now)
    run_periodic_jobs(now, settings)
    logger.info(log.WORKER_TICK, due=ran, duration_ms=round((time.monotonic() - started) * 1000))


def main() -> None:
    """Configure the process and run the loop until it is asked to stop."""
    settings = get_settings()
    log.configure_logging(settings)
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    logger.info(log.WORKER_STARTED, loop_seconds=settings.worker.loop_seconds)
    while not _stopping:
        started = time.monotonic()
        try:
            run_tick(datetime.now(UTC), settings)
        except Exception:
            # One bad tick must never end the process: the next one may succeed,
            # and whatever failed is still in the database, waiting.
            logger.exception(log.WORKER_TICK_FAILED)
        finally:
            log.clear_context()

        elapsed = time.monotonic() - started
        # An interruptible wait, not time.sleep: since PEP 475 a sleep resumes
        # after a signal with a recomputed deadline, so SIGTERM would go
        # unnoticed for a full minute — and the platform sends SIGKILL long
        # before that.
        _wake.wait(max(0.0, settings.worker.loop_seconds - elapsed))

    logger.info(log.WORKER_STOPPED)


if __name__ == "__main__":
    main()
