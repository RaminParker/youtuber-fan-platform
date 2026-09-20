"""What the product looks like: every colour and every size, once.

Pages carry a stylesheet, mails carry inline rules, because mail clients drop
everything else. That is a constraint on where the rules end up, not on where
they are decided — both read the tokens below, so changing a colour is one
edit and cannot land in only half of the product.

Not in `settings.toml`: this is not a knob an operator turns per environment,
it is the design. What varies per creator is their accent colour, and that one
lives in the database and is made readable in `app.branding`.
"""

from __future__ import annotations

#: Colours of a page or a mail read in daylight.
LIGHT = {
    "fg": "#1a1a1a",  # body text
    "muted": "#5c5c5c",  # footers, hints, the second line of a header
    "bg": "#ffffff",  # the sheet a page is written on
    "canvas": "#f4f2ee",  # what surrounds the card in a mail
    "card": "#ffffff",  # the card itself
    "rule": "#e3e0da",  # hairlines and borders, warm enough for both surfaces
    "quiet": "#f6f4f0",  # the sentiment box, the example mail
    "highlight": "#fff8e1",  # the creator's action bar: the one thing to notice
    "bright": "#ffffff",  # text on a dark accent
    "dark_ink": "#111111",  # text on a light accent
}

#: The same roles at night. Every key of LIGHT is answered here — a missing one
#: is how the footer once ended up grey on near-black.
DARK = {
    "fg": "#ece8e1",
    "muted": "#a9a49a",
    "bg": "#171612",
    "canvas": "#171612",
    "card": "#201e19",
    "rule": "#34312b",
    "quiet": "#201e19",
    "highlight": "#2b2720",
    "bright": "#ffffff",
    "dark_ink": "#111111",
}

#: Type and shape. Nothing that carries text goes below 1rem: the product is
#: read on phones, by people who did not ask for small print (manifest §5.5).
TYPE = {
    "family": '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    "base": "17px",
    "mail_base": "16px",  # mail clients scale rem unreliably; px is the safe unit
    "line": "1.6",
    "body_size": "1rem",
    "lead_size": "1.05rem",
    "title_size": "1.6rem",
    "section_size": "1.15rem",
    "mail_title_size": "1.25rem",
    "radius": "6px",
    "card_radius": "10px",
    "measure": "38rem",  # how wide a column may get before it is hard to read
    "mail_measure": "37.5rem",
}


#: What a page wears when it belongs to nobody in particular.
DEFAULT_ACCENT = "#333333"


def css_variables(palette: dict[str, str]) -> str:
    """Render one palette as CSS custom properties, ready for a ``:root`` block."""
    return " ".join(f"--{name}: {value};" for name, value in sorted(palette.items()))


def type_variables() -> str:
    """Render the type and shape tokens the stylesheet asks for."""
    return " ".join(f"--{name.replace('_', '-')}: {value};" for name, value in sorted(TYPE.items()))


class Design:
    """The one object templates reach for. Values, not decisions."""

    light = LIGHT
    dark = DARK
    type = TYPE
    default_accent = DEFAULT_ACCENT
    variables = staticmethod(css_variables)
    type_variables = staticmethod(type_variables)
