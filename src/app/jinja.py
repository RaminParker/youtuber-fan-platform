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

from app.branding import PAGE_DARK, PAGE_LIGHT, ink_on, readable_on, surface_on
from app.config import Settings, get_settings
from app.design import Design

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

DATETIME_FORMAT = "%d.%m.%Y um %H:%M Uhr"
DATE_FORMAT = "%d.%m.%Y"

# Spelled out rather than taken from the locale: a container's locale is
# whatever the base image ships, and a preview must never say "Tuesday".
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip


def as_clock(seconds: int) -> str:
    """Format a position in a video as ``mm:ss``, or ``h:mm:ss`` past the hour."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _localise(value: datetime, timezone: str, fmt: str) -> str:
    """Render a UTC timestamp in the product's timezone."""
    return value.astimezone(ZoneInfo(timezone)).strftime(fmt)


def long_datetime(value: datetime, timezone: str) -> str:
    """Render a moment the way a person says it: "Dienstag, 23. September, um 18:00 Uhr"."""
    local = value.astimezone(ZoneInfo(timezone))
    weekday, month = WEEKDAYS[local.weekday()], MONTHS[local.month - 1]
    return f"{weekday}, {local.day}. {month}, um {local:%H:%M} Uhr"


def thousands(number: int) -> str:
    """Group digits the German way: 1.234."""
    return f"{number:,}".replace(",", ".")


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
    environment.filters["long_datetime"] = lambda v: long_datetime(v, timezone)
    environment.filters["thousands"] = thousands
    environment.filters["local_date"] = lambda v: _localise(v, timezone, DATE_FORMAT)
    # Brand colours are the creator's; what has to be read is derived from them.
    environment.globals["ink_on"] = ink_on
    environment.globals["link_on_light"] = lambda accent: readable_on(accent, PAGE_LIGHT)
    environment.globals["link_on_dark"] = lambda accent: readable_on(accent, PAGE_DARK)
    environment.globals["surface_on_light"] = lambda accent: surface_on(accent, PAGE_LIGHT)
    environment.globals["surface_on_dark"] = lambda accent: surface_on(accent, PAGE_DARK)
    environment.globals["design"] = Design
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
