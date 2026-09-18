"""The mail transport: batches, back-off, and the webhook signature."""

import base64
import json

import httpx
import pytest

from app.delivery.email_client import (
    BATCH_SIZE,
    WEBHOOK_TOLERANCE_SECONDS,
    EmailError,
    EmailTemporaryError,
    QuotaExhausted,
    ResendClient,
    to_payload,
    verify_webhook_signature,
)
from app.delivery.render import OutgoingEmail
from app.errors import TemporaryError
from tests.fakes import WEBHOOK_SECRET, svix_headers

NOW = 1_789_000_000.0


def mail(to: str = "fan@example.org", key: str | None = None) -> OutgoingEmail:
    return OutgoingEmail(
        from_="Pilotkanal via Klartext <post@mail.klartext.tld>",
        to=to,
        subject="Pilotkanal: Ein Video",
        html="<p>Hallo</p>",
        text="Hallo",
        reply_to="hallo@klartext.tld",
        headers={"List-Unsubscribe": "<https://klartext.tld/abmelden/t>"},
        idempotency_key=key,
    )


def client_for(handler) -> tuple[ResendClient, list]:
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return ResendClient("re_test", httpx.Client(transport=httpx.MockTransport(wrapped))), seen


def ok(payload):
    return lambda request: httpx.Response(200, json=payload)


class TestPayload:
    def test_the_shape_the_provider_expects(self):
        body = to_payload(mail())

        assert body["to"] == ["fan@example.org"]
        assert body["reply_to"] == "hallo@klartext.tld"
        assert body["headers"]["List-Unsubscribe"].startswith("<https://")

    def test_an_empty_reply_to_is_omitted_rather_than_sent_blank(self):
        bare = OutgoingEmail(from_="a", to="b", subject="c", html="d", text="e")

        assert "reply_to" not in to_payload(bare)


class TestSingleSend:
    def test_it_returns_the_provider_id(self):
        client, _ = client_for(ok({"id": "msg-1"}))

        assert client.send(mail()) == "msg-1"

    def test_the_idempotency_key_travels_as_a_header(self):
        # This is what makes a retry after a lost response safe.
        client, seen = client_for(ok({"id": "msg-1"}))

        client.send(mail(key="mailing/7/1"))

        assert seen[0].headers["Idempotency-Key"] == "mailing/7/1"

    def test_no_key_means_no_header(self):
        client, seen = client_for(ok({"id": "msg-1"}))

        client.send(mail())

        assert "Idempotency-Key" not in seen[0].headers


class TestBatch:
    def test_it_posts_a_list_and_returns_the_ids_in_order(self):
        client, seen = client_for(ok({"data": [{"id": "a"}, {"id": "b"}]}))

        ids = client.send_batch([mail("one@example.org"), mail("two@example.org")])

        assert ids == ["a", "b"]
        assert json.loads(seen[0].content)[1]["to"] == ["two@example.org"]

    def test_the_first_mails_key_covers_the_whole_batch(self):
        client, seen = client_for(ok({"data": []}))

        client.send_batch([mail(key="mailing/7/1"), mail()])

        assert seen[0].headers["Idempotency-Key"] == "mailing/7/1"

    def test_an_empty_batch_needs_no_request(self):
        client, seen = client_for(ok({"data": []}))

        assert client.send_batch([]) == []
        assert seen == []

    def test_more_than_the_limit_is_refused_before_the_call(self):
        client, seen = client_for(ok({"data": []}))

        with pytest.raises(ValueError):
            client.send_batch([mail()] * (BATCH_SIZE + 1))

        assert seen == []


class TestErrors:
    def test_a_passing_rate_limit_is_worth_retrying(self):
        client, _ = client_for(lambda r: httpx.Response(429, json={"name": "rate_limit_exceeded"}))

        with pytest.raises(EmailTemporaryError) as caught:
            client.send(mail())

        assert not isinstance(caught.value, QuotaExhausted)

    @pytest.mark.parametrize("name", ["daily_quota_exceeded", "monthly_quota_exceeded"])
    def test_an_exhausted_plan_is_named_separately(self, name):
        # Same 429, different problem: patience will not fix a plan limit.
        client, _ = client_for(lambda r: httpx.Response(429, json={"name": name}))

        with pytest.raises(QuotaExhausted):
            client.send(mail())

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_provider_trouble_is_worth_retrying(self, status):
        client, _ = client_for(lambda r: httpx.Response(status, text="oops"))

        with pytest.raises(EmailTemporaryError):
            client.send(mail())

    def test_a_refused_message_is_permanent(self):
        client, _ = client_for(lambda r: httpx.Response(422, json={"message": "invalid to"}))

        with pytest.raises(EmailError):
            client.send(mail())

    def test_temporary_means_what_the_worker_catches(self):
        assert issubclass(EmailTemporaryError, TemporaryError)
        assert issubclass(QuotaExhausted, TemporaryError)


class TestWebhookSignature:
    """A forged webhook could block every subscriber on the platform."""

    @staticmethod
    def sign(body: bytes, message_id="msg_1", timestamp=str(int(NOW)), secret=WEBHOOK_SECRET):
        return svix_headers(body, secret, message_id=message_id, timestamp=timestamp)

    def test_a_genuine_signature_is_accepted(self):
        body = b'{"type":"email.bounced"}'

        assert verify_webhook_signature(body, self.sign(body), WEBHOOK_SECRET, now=NOW) is True

    def test_a_changed_body_is_rejected(self):
        body = b'{"type":"email.bounced"}'
        headers = self.sign(body)

        assert (
            verify_webhook_signature(
                b'{"type":"email.delivered"}', headers, WEBHOOK_SECRET, now=NOW
            )
            is False
        )

    def test_the_wrong_secret_is_rejected(self):
        body = b"{}"
        other = "whsec_" + base64.b64encode(b"a-different-secret-entirely").decode()

        assert (
            verify_webhook_signature(body, self.sign(body, secret=other), WEBHOOK_SECRET, now=NOW)
            is False
        )

    def test_an_old_request_is_rejected(self):
        # Otherwise a captured request stays replayable forever.
        body = b"{}"
        old = str(int(NOW - WEBHOOK_TOLERANCE_SECONDS - 1))

        assert (
            verify_webhook_signature(body, self.sign(body, timestamp=old), WEBHOOK_SECRET, now=NOW)
            is False
        )

    def test_a_request_from_just_inside_the_window_is_accepted(self):
        body = b"{}"
        recent = str(int(NOW - WEBHOOK_TOLERANCE_SECONDS + 10))

        assert (
            verify_webhook_signature(
                body, self.sign(body, timestamp=recent), WEBHOOK_SECRET, now=NOW
            )
            is True
        )

    def test_several_signatures_are_allowed_and_one_match_is_enough(self):
        # Providers send more than one during a secret rotation.
        body = b"{}"
        headers = self.sign(body)
        headers["svix-signature"] = "v1,Zm9yZ2VkCg== " + headers["svix-signature"]

        assert verify_webhook_signature(body, headers, WEBHOOK_SECRET, now=NOW) is True

    @pytest.mark.parametrize("missing", ["svix-id", "svix-timestamp", "svix-signature"])
    def test_a_missing_header_is_rejected(self, missing):
        body = b"{}"
        headers = self.sign(body)
        del headers[missing]

        assert verify_webhook_signature(body, headers, WEBHOOK_SECRET, now=NOW) is False

    def test_a_nonsense_timestamp_is_rejected(self):
        body = b"{}"
        headers = self.sign(body)
        headers["svix-timestamp"] = "not-a-number"

        assert verify_webhook_signature(body, headers, WEBHOOK_SECRET, now=NOW) is False

    @pytest.mark.parametrize("secret", ["", "whsec_not-base64!!", "nonsense"])
    def test_an_unusable_secret_rejects_instead_of_raising(self, secret):
        # Every other failure mode here returns False; a misconfigured secret
        # must not be the one that reaches the caller as an exception.
        body = b"{}"

        assert verify_webhook_signature(body, self.sign(body), secret, now=NOW) is False

    @pytest.mark.parametrize("secret", ["", "whsec_"])
    def test_an_empty_secret_rejects_a_request_signed_with_the_empty_key(self, secret):
        # An empty secret decodes to an empty HMAC key without complaint, and
        # anyone can sign with that. Unconfigured must mean "refuse everything".
        body = b'{"type":"email.complained","data":{"to":["victim@example.org"]}}'

        headers = self.sign(body, secret=secret)

        assert verify_webhook_signature(body, headers, secret, now=NOW) is False

    def test_a_non_ascii_signature_is_rejected_not_raised(self):
        body = b"{}"
        headers = self.sign(body)
        headers["svix-signature"] = "v1,\xe4"

        assert verify_webhook_signature(body, headers, WEBHOOK_SECRET, now=NOW) is False

    def test_header_case_does_not_matter(self):
        body = b"{}"
        headers = {k.upper(): v for k, v in self.sign(body).items()}

        assert verify_webhook_signature(body, headers, WEBHOOK_SECRET, now=NOW) is True
