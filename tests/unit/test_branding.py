"""A creator picks a colour; every text on it still has to be readable.

The accent is used for links, buttons and rules. Left unchecked, a dark brand
colour disappears on a dark page and a light one on a white one — and the
creator never sees it, because their own machine may be in the other mode.
"""

import pytest

from app.branding import AA_CONTRAST, UI_CONTRAST, contrast, ink_on, readable_on, surface_on

DARK_PAGE = "#171612"
LIGHT_PAGE = "#ffffff"

ACCENTS = ["#333333", "#000000", "#ffffff", "#ffe500", "#c4452d", "#0b5cff", "#7cf5c0", "#8a8a8a"]


class TestContrast:
    def test_black_on_white_is_the_maximum(self):
        assert contrast("#000000", "#ffffff") == pytest.approx(21, abs=0.1)

    def test_a_colour_on_itself_is_the_minimum(self):
        assert contrast("#c4452d", "#c4452d") == pytest.approx(1, abs=0.01)

    def test_short_hex_is_understood(self):
        assert contrast("#fff", "#000") == pytest.approx(21, abs=0.1)


class TestReadableLinks:
    @pytest.mark.parametrize("accent", ACCENTS)
    @pytest.mark.parametrize("page", [LIGHT_PAGE, DARK_PAGE])
    def test_every_accent_becomes_readable_on_every_page(self, accent, page):
        assert contrast(readable_on(accent, page), page) >= AA_CONTRAST

    @pytest.mark.parametrize("page", [LIGHT_PAGE, DARK_PAGE])
    def test_a_colour_that_already_reads_well_is_left_alone(self, page):
        accent = "#c4452d" if page == LIGHT_PAGE else "#7cf5c0"

        assert readable_on(accent, page) == accent

    def test_the_hue_survives_the_adjustment(self):
        # A red brand must not come back blue-ish, only lighter or darker.
        adjusted = readable_on("#c4452d", DARK_PAGE)
        red, green, blue = (int(adjusted[i : i + 2], 16) for i in (1, 3, 5))

        assert red > green and red > blue


class TestTextOnTheAccentItself:
    @pytest.mark.parametrize("accent", ACCENTS)
    def test_a_button_label_is_readable_on_its_own_button(self, accent):
        assert contrast(ink_on(accent), accent) >= AA_CONTRAST

    def test_white_on_a_dark_brand_black_on_a_light_one(self):
        assert ink_on("#0b5cff") == "#ffffff"
        assert ink_on("#ffe500") == "#111111"


class TestTheAccentAsASurface:
    """A button is a shape before it is a label: it has to be visible at all.

    WCAG 1.4.11 asks 3:1 for interface elements against what surrounds them.
    The near-black default reaches 1.4 on a dark page — a creator in dark mode
    would see white text floating on nothing.
    """

    @pytest.mark.parametrize("accent", ACCENTS)
    @pytest.mark.parametrize("page", [LIGHT_PAGE, DARK_PAGE])
    def test_every_accent_becomes_a_visible_shape(self, accent, page):
        assert contrast(surface_on(accent, page), page) >= UI_CONTRAST

    @pytest.mark.parametrize("accent", ACCENTS)
    @pytest.mark.parametrize("page", [LIGHT_PAGE, DARK_PAGE])
    def test_and_its_label_still_reads_on_it(self, accent, page):
        surface = surface_on(accent, page)

        assert contrast(ink_on(surface), surface) >= AA_CONTRAST

    def test_a_brand_that_already_stands_out_is_left_alone(self):
        assert surface_on("#c4452d", DARK_PAGE) == "#c4452d"

    def test_the_default_grey_is_lifted_off_a_dark_page(self):
        lifted = surface_on("#333333", DARK_PAGE)

        assert lifted != "#333333"
        assert contrast(lifted, DARK_PAGE) >= UI_CONTRAST
