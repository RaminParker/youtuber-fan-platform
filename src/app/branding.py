"""Turning a creator's brand colour into colours that can actually be read.

A creator picks one colour. It then carries links, buttons and rules on their
pages and in their mails — on a white mail, on a light page and on a dark one.
An unadjusted brand colour fails at least one of those: near-black vanishes in
dark mode, near-white on a white page, and white text on a pale button is
invisible. None of it is visible to the creator, whose own machine sits in one
mode.

So the colour stays the brand, and what has to be *read* is derived from it:
lightened or darkened along its own hue until it clears the WCAG AA contrast
ratio for body text.
"""

from __future__ import annotations

#: The two backgrounds a page is read on; mails are always on the light one.
PAGE_LIGHT = "#ffffff"
PAGE_DARK = "#171612"

#: WCAG 2.1 AA for normal text.
AA_CONTRAST = 4.5

#: How far one step moves a colour towards white or black. Small enough to stop
#: close to the brand, large enough to always arrive.
STEP = 0.06


def _channels(colour: str) -> tuple[int, int, int]:
    """Read ``#rgb`` or ``#rrggbb`` into three 0-255 values."""
    value = colour.lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _hex(channels: tuple[float, float, float]) -> str:
    """Write three 0-255 values back as ``#rrggbb``."""
    return "#" + "".join(f"{round(max(0, min(255, channel))):02x}" for channel in channels)


def _relative_luminance(colour: str) -> float:
    """Perceived brightness of a colour, as WCAG defines it."""
    parts = []
    for channel in _channels(colour):
        fraction = channel / 255
        parts.append(
            fraction / 12.92 if fraction <= 0.04045 else ((fraction + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = parts
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours (1 to 21)."""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def ink_on(accent: str) -> str:
    """Return the text colour to use *on* the accent — white or near-black."""
    return "#ffffff" if contrast("#ffffff", accent) >= contrast("#111111", accent) else "#111111"


def readable_on(accent: str, background: str) -> str:
    """Return the accent, moved just far enough to be readable on ``background``.

    The direction follows the page: away from a dark background towards white,
    away from a light one towards black. The hue is kept, because this is still
    the creator's colour — only its lightness is negotiable.
    """
    if contrast(accent, background) >= AA_CONTRAST:
        return accent

    target = 255 if _relative_luminance(background) < 0.5 else 0
    channels = _channels(accent)
    for step in range(1, int(1 / STEP) + 1):
        moved = tuple(channel + (target - channel) * (step * STEP) for channel in channels)
        candidate = _hex(moved)
        if contrast(candidate, background) >= AA_CONTRAST:
            return candidate
    return "#ffffff" if target else "#111111"
