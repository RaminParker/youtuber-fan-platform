"""The Jinja environment. There is exactly one, and mails and pages share it.

That sharing is the point: the summary body, the sentiment box and the platform
footer are the same partials in a mail and on its "online ansehen" page, so the
two cannot drift apart.
"""

from __future__ import annotations

import functools
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.config import Settings, get_settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

DATETIME_FORMAT = "%d.%m.%Y um %H:%M Uhr"
DATE_FORMAT = "%d.%m.%Y"


def as_clock(seconds: int) -> str:
    """Format a position in a video as ``mm:ss``, or ``h:mm:ss`` past the hour."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _localise(value: datetime, timezone: str, fmt: str) -> str:
    """Render a UTC timestamp in the product's timezone."""
    return value.astimezone(ZoneInfo(timezone)).strftime(fmt)


def build_environment(settings: Settings) -> Environment:
    """Build the environment. Use :func:`get_jinja` unless you are a test.

    ``autoescape`` is switched on for HTML only, so that the plain-text twin of
    every mail template stays unescaped and readable.
    """
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        # Deliberately off. They swallow the newlines a plain-text mail is made
        # of, and HTML does not care about the whitespace they would save.
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        # A typo in a template name must fail loudly, not render an empty page.
        undefined=StrictUndefined,
    )
    timezone = settings.product.timezone
    environment.filters["local_datetime"] = lambda v: _localise(v, timezone, DATETIME_FORMAT)
    environment.filters["clock"] = as_clock
    environment.filters["local_date"] = lambda v: _localise(v, timezone, DATE_FORMAT)
    environment.globals["product"] = settings.product
    environment.globals["base_url"] = settings.base_url
    return environment


@functools.lru_cache(maxsize=1)
def get_jinja() -> Environment:
    """Return the process-wide environment, built on first use."""
    return build_environment(get_settings())


def render_partial(template: str, **context) -> str:
    """Render a fragment by name, without the `partials/` prefix.

    What HTMX swaps into a page: the same template the page includes, so the
    fragment and the page cannot drift apart.
    """
    return get_jinja().get_template(f"partials/{template}.html").render(**context)


def render_page(template: str, **context) -> str:
    """Render a page template by name, without the `pages/` prefix.

    That prefix and the `.html` suffix are the template layout's contract; they
    belong in one place, not in every route module.
    """
    return get_jinja().get_template(f"pages/{template}.html").render(**context)
