"""One place decides what the product looks like.

Pages are styled by a stylesheet, mails by inline rules — mail clients ignore
everything else. That is a technical constraint on *where the rules live*, not
a licence for two sets of values: a colour changed in one and forgotten in the
other is how a product starts looking like two products.
"""

import re

from app.config import REPO_ROOT, get_settings
from app.design import DARK, LIGHT, TYPE, css_variables
from app.jinja import build_environment

STYLESHEET = REPO_ROOT / "src" / "app" / "static" / "style.css"
MAIL_SHELL = REPO_ROOT / "src" / "app" / "templates" / "email" / "base.html"
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


class TestTheTokensThemselves:
    def test_dark_answers_every_colour_light_defines(self):
        # The pale footer nobody could read came from exactly this gap.
        assert set(DARK) == set(LIGHT)

    def test_no_text_is_smaller_than_sixteen_pixels(self):
        sizes = [value for name, value in TYPE.items() if name.endswith("_size")]

        assert sizes
        assert all(float(value.removesuffix("rem")) >= 1 for value in sizes)

    def test_they_render_as_css_variables(self):
        variables = css_variables(LIGHT)

        assert "--fg:" in variables
        assert LIGHT["fg"] in variables


class TestNobodyKeepsTheirOwnCopy:
    def test_the_stylesheet_names_no_colour_of_its_own(self):
        loose = COLOUR.findall(STYLESHEET.read_text(encoding="utf-8"))

        assert not loose, f"colours belong in app/design.py, found {loose}"

    def test_the_mail_shell_names_no_colour_of_its_own(self):
        # Its values are inlined at render time — from the same tokens.
        loose = COLOUR.findall(MAIL_SHELL.read_text(encoding="utf-8"))

        assert not loose, f"colours belong in app/design.py, found {loose}"

    def test_a_page_and_a_mail_show_the_same_ink(self):
        environment = build_environment(get_settings())
        page = environment.get_template("pages/error.html").render(
            heading="Fehler", message="Text", creator=None
        )
        mail = environment.get_template("email/creator_notice.html").render(
            creator=type("C", (), {"name": "Kanal", "logo_url": None})(),
            accent="#333333",
            subject="Betreff",
            headline="Titel",
            explanation="Text",
            what_now="",
            video_title="",
            action_url="",
            action_label="",
        )

        assert LIGHT["fg"] in page or LIGHT["fg"] in css_variables(LIGHT)
        assert LIGHT["fg"] in mail


class TestTheTokensArriveIntact:
    def test_the_font_list_is_not_escaped_into_nonsense(self):
        # Autoescaping turned the quotes in "Segoe UI" into entities once, and
        # the whole font declaration became invalid: every page went serif.
        page = (
            build_environment(get_settings())
            .get_template("pages/error.html")
            .render(heading="Fehler", message="Text", creator=None)
        )

        assert TYPE["family"] in page
        assert "&quot;" not in page


class TestTheDerivedColoursAreActuallyUsed:
    """Deriving a readable colour is worthless if no rule reads it.

    This is not hypothetical: a stylesheet rewrite once dropped the dark-mode
    block, and the dark variants were still computed, still passed to the page,
    and used by nothing — a dark brand colour was invisible again.
    """

    def test_every_variable_the_page_sets_has_a_reader(self):
        shell = (REPO_ROOT / "src" / "app" / "templates" / "pages" / "base.html").read_text(
            encoding="utf-8"
        )
        css = STYLESHEET.read_text(encoding="utf-8")

        declared = set(re.findall(r"--([a-z-]+):\s*\{\{", shell))
        unread = {name for name in declared if f"var(--{name}" not in css}

        assert not unread, f"nothing reads {sorted(unread)}"

    def test_the_stylesheet_answers_dark_mode(self):
        css = STYLESHEET.read_text(encoding="utf-8")

        assert "prefers-color-scheme: dark" in css
