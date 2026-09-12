"""Logging must carry the bound context and obey the configured format."""

import json
import logging

import pytest
import structlog

from app import log
from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    log.clear_context()
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def configure(monkeypatch, *, as_json: bool) -> None:
    monkeypatch.setenv("LOGGING__JSON", str(as_json).lower())
    get_settings.cache_clear()
    log.configure_logging(get_settings())


class TestContext:
    def test_bound_values_appear_on_every_line(self, monkeypatch, capsys):
        configure(monkeypatch, as_json=True)
        log.bind(appearance_id=42, step="transcribe")

        log.get_logger(__name__).info(log.TRANSCRIPT_FETCHED, origin="youtube_official")

        record = json.loads(capsys.readouterr().err)
        assert record["event"] == "transcript.fetched"
        assert record["appearance_id"] == 42
        assert record["step"] == "transcribe"
        assert record["origin"] == "youtube_official"
        assert record["level"] == "info"
        assert record["timestamp"].endswith("Z")

    def test_clearing_the_context_unbinds_everything(self, monkeypatch, capsys):
        configure(monkeypatch, as_json=True)
        log.bind(appearance_id=42)
        log.clear_context()

        log.get_logger(__name__).info(log.WORKER_TICK)

        assert "appearance_id" not in json.loads(capsys.readouterr().err)


class TestFormat:
    def test_the_setting_alone_picks_json(self, monkeypatch, capsys):
        configure(monkeypatch, as_json=True)

        log.get_logger(__name__).info(log.WORKER_TICK, due=0)

        assert json.loads(capsys.readouterr().err)["due"] == 0

    def test_console_output_is_not_json(self, monkeypatch, capsys):
        configure(monkeypatch, as_json=False)

        log.get_logger(__name__).info(log.WORKER_TICK, due=0)

        err = capsys.readouterr().err
        assert "worker.tick" in err
        with pytest.raises(json.JSONDecodeError):
            json.loads(err)


class TestStdlibRouting:
    def test_a_plain_stdlib_logger_gets_the_same_shape(self, monkeypatch, capsys):
        configure(monkeypatch, as_json=True)

        logging.getLogger("uvicorn.error").warning("started")

        record = json.loads(capsys.readouterr().err)
        assert record["event"] == "started"
        assert record["logger"] == "uvicorn.error"

    def test_uvicorn_loses_its_own_handlers(self, monkeypatch):
        # Otherwise the access log keeps uvicorn's format next to ours.
        logging.getLogger("uvicorn.access").addHandler(logging.NullHandler())
        logging.getLogger("uvicorn.access").propagate = False

        configure(monkeypatch, as_json=True)

        access = logging.getLogger("uvicorn.access")
        assert access.handlers == []
        assert access.propagate is True

    def test_chatty_libraries_are_quietened(self, monkeypatch):
        configure(monkeypatch, as_json=True)

        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
