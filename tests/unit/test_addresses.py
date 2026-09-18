"""What counts as an address, and what counts as the same one."""

from types import SimpleNamespace

import dns.exception
import dns.resolver
import pytest

from app.addresses import InvalidAddress, canonical, validate


class FakeResolver:
    """Answers MX queries from a table instead of the network."""

    def __init__(self, answer: list[str] | None = None, raises: Exception | None = None) -> None:
        self.answer = answer or ["mx.example.net."]
        self.raises = raises

    def resolve(self, domain, record_type, **kwargs):
        if self.raises is not None:
            raise self.raises
        return [SimpleNamespace(preference=10, exchange=host) for host in self.answer]


class TestCanonical:
    def test_trims_and_lower_cases(self):
        assert canonical("  Fan@Example.ORG ") == "fan@example.org"


class TestSyntax:
    @pytest.mark.parametrize(
        ("raw", "stored"),
        [
            ("fan@example.org", "fan@example.org"),
            ("  Fan.Name+kanal@Example.ORG ", "fan.name+kanal@example.org"),
            ("fan@müller.de", "fan@xn--mller-kva.de"),
        ],
    )
    def test_accepts_and_normalises(self, raw, stored):
        assert validate(raw, check_dns=False) == stored

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not-an-address",
            "fan@localhost",
            "fan@example",
            "fan@example.org.",
            "<fan@example.org>",
            "a<fan@example.org>",
            "Fan <fan@example.org>",
            '"fan"@example.org',
            "fan name@example.org",
            "fan@@example.org",
            "fan\x00@example.org",
            "fän@example.org",
            "fan@[192.0.2.1]",
            "fan@example.test",
            "x" * 65 + "@example.org",
            "fan@" + "a" * 250 + ".org",
        ],
    )
    def test_rejects(self, raw):
        # Each of these either cannot receive mail or smuggles a second spelling
        # of one address past the per-address brake and the complaint block.
        with pytest.raises(InvalidAddress):
            validate(raw, check_dns=False)


class TestDeliverability:
    def test_a_domain_with_a_mail_server_passes(self):
        assert validate("fan@example.org", check_dns=True, resolver=FakeResolver()) == (
            "fan@example.org"
        )

    def test_a_domain_that_does_not_exist_is_rejected(self):
        # Mistyped domains (gmial.com, gmx.dee) are the commonest bounce; each
        # bounce costs sending reputation every creator shares.
        with pytest.raises(InvalidAddress):
            validate(
                "fan@gmx.dee", check_dns=True, resolver=FakeResolver(raises=dns.resolver.NXDOMAIN())
            )

    def test_a_domain_that_refuses_mail_is_rejected(self):
        # RFC 7505 null MX: the domain says outright that it accepts no mail.
        with pytest.raises(InvalidAddress):
            validate("fan@example.org", check_dns=True, resolver=FakeResolver(answer=["."]))

    def test_a_dns_timeout_lets_the_address_through(self):
        # Our resolver having a bad minute must not lock fans out.
        resolver = FakeResolver(raises=dns.exception.Timeout())

        assert validate("fan@example.org", check_dns=True, resolver=resolver) == "fan@example.org"
