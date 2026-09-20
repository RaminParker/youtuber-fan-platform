"""A rejected key or an exhausted plan must say so, by name, and never cost a video.

The response bodies below are the real ones, captured on 2026-09-19 from the
live services, not invented shapes.
"""

import httpx
import pytest

from app.analysis.llm import BifrostGateway, LLMError
from app.analysis.schemas import Sentiment
from app.delivery.email_client import EmailError, QuotaExhausted, ResendClient
from app.delivery.render import OutgoingEmail
from app.errors import NeedsOperator, TemporaryError
from app.sources.youtube.data_api import YouTubeDataApi, YouTubeTemporaryError

YOUTUBE_KEY_INVALID = {
    "error": {
        "code": 400,
        "message": "API key not valid. Please pass a valid API key.",
        "errors": [{"message": "API key not valid.", "domain": "global", "reason": "badRequest"}],
        "status": "INVALID_ARGUMENT",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}
        ],
    }
}
YOUTUBE_QUOTA = {
    "error": {
        "code": 403,
        "message": "The request cannot be completed because you have exceeded your quota.",
        "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}],
    }
}
GATEWAY_KEY_UNKNOWN = {
    "type": "access_not_found",
    "status_code": 401,
    "error": {"message": "access not found. The provided credential does not exist or has been revoked."},
}  # fmt: skip
GATEWAY_NO_PROVIDER_KEY = {
    "is_bifrost_error": False,
    "error": {"message": "no keys found for provider: anthropic and model: claude-sonnet-4-5"},
}
MODEL_RETIRED = {
    "is_bifrost_error": False,
    "status_code": 404,
    "error": {"type": "not_found_error", "message": "model: claude-retired-9-9"},
}
MODEL_BLOCKED = {
    "type": "model_blocked",
    "status_code": 403,
    "error": {"message": "Model 'claude-opus-4-1' is not allowed for virtual key 'app'"},
}
PROVIDER_NO_CREDIT = {
    "error": {"message": "Your credit balance is too low to access the Anthropic API."}
}


def youtube(status, body) -> YouTubeDataApi:
    handler = lambda request: httpx.Response(status, json=body)  # noqa: E731
    return YouTubeDataApi("test-key", httpx.Client(transport=httpx.MockTransport(handler)))


def gateway(status, body) -> BifrostGateway:
    handler = lambda request: httpx.Response(status, json=body)  # noqa: E731
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BifrostGateway("http://gateway", "sk-bf-test", 30, client)


def resend(status, body) -> ResendClient:
    handler = lambda request: httpx.Response(status, json=body)  # noqa: E731
    return ResendClient("re_test", httpx.Client(transport=httpx.MockTransport(handler)))


def ask(client: BifrostGateway):
    return client.complete_json(
        model="anthropic/claude-sonnet-4-5", system="s", user="u", schema=Sentiment, max_tokens=10
    )


MAIL = OutgoingEmail(from_="a@b.c", to="d@e.f", subject="s", html="h", text="t")


class TestTheErrorItself:
    def test_it_names_service_problem_and_what_to_check(self):
        error = NeedsOperator("YouTube Data API", "API key rejected", "check YOUTUBE_API_KEY")

        assert str(error) == "YouTube Data API: API key rejected — check YOUTUBE_API_KEY"

    def test_it_is_not_a_retry(self):
        # A retry would burn the ladder on something only a person can fix,
        # and after ten attempts give the video up for our misconfiguration.
        assert not issubclass(NeedsOperator, TemporaryError)


class TestYouTube:
    def test_a_rejected_key_names_the_variable(self):
        with pytest.raises(NeedsOperator) as caught:
            youtube(400, YOUTUBE_KEY_INVALID).videos(["aaaaaaaaaaa"])

        assert "YOUTUBE_API_KEY" in str(caught.value)
        assert "API_KEY_INVALID" in str(caught.value)

    def test_an_exhausted_quota_says_when_it_resets(self):
        with pytest.raises(NeedsOperator) as caught:
            youtube(403, YOUTUBE_QUOTA).videos(["aaaaaaaaaaa"])

        assert "quota" in str(caught.value)
        assert "09:00" in str(caught.value)

    def test_a_rate_limit_is_still_a_plain_retry(self):
        body = {"error": {"errors": [{"reason": "rateLimitExceeded"}]}}
        with pytest.raises(YouTubeTemporaryError):
            youtube(403, body).videos(["aaaaaaaaaaa"])


class TestTheGateway:
    def test_an_unknown_gateway_key_names_both_sides(self):
        with pytest.raises(NeedsOperator) as caught:
            ask(gateway(401, GATEWAY_KEY_UNKNOWN))

        assert "LLM_GATEWAY_KEY" in str(caught.value)
        assert "revoked" in str(caught.value)

    def test_a_gateway_without_a_usable_provider_key_names_it(self):
        with pytest.raises(NeedsOperator) as caught:
            ask(gateway(400, GATEWAY_NO_PROVIDER_KEY))

        assert "ANTHROPIC_API_KEY" in str(caught.value)
        assert "no keys found" in str(caught.value)

    def test_no_credit_left_is_the_operators_too(self):
        with pytest.raises(NeedsOperator) as caught:
            ask(gateway(400, PROVIDER_NO_CREDIT))

        assert "credit balance" in str(caught.value)

    def test_a_model_the_provider_no_longer_has_names_the_setting(self):
        with pytest.raises(NeedsOperator) as caught:
            ask(gateway(404, MODEL_RETIRED))

        message = str(caught.value)
        assert "anthropic/claude-sonnet-4-5" in message  # the model we asked for
        assert "claude-retired-9-9" in message  # the provider's own words
        assert "config/settings.toml" in message
        assert caught.value.problem.startswith("model ")  # not blamed on a key

    def test_a_model_the_gateway_does_not_allow_names_its_file(self):
        with pytest.raises(NeedsOperator) as caught:
            ask(gateway(403, MODEL_BLOCKED))

        assert "allowed_models" in str(caught.value)
        assert "config/bifrost.json" in str(caught.value)
        assert caught.value.problem.startswith("model ")

    def test_any_other_refusal_stays_a_plain_error(self):
        with pytest.raises(LLMError):
            ask(gateway(400, {"error": {"message": "max_tokens: must be positive"}}))


class TestResend:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_rejected_key_names_the_variable(self, status):
        body = {"name": "invalid_api_key", "message": "API key is invalid"}
        with pytest.raises(NeedsOperator) as caught:
            resend(status, body).send(MAIL)

        assert "RESEND_API_KEY" in str(caught.value)
        assert "API key is invalid" in str(caught.value)

    def test_an_exhausted_plan_needs_the_operator(self):
        body = {"name": "daily_quota_exceeded", "message": "You have reached your daily quota"}
        with pytest.raises(QuotaExhausted) as caught:
            resend(429, body).send_batch([MAIL])

        assert isinstance(caught.value, NeedsOperator)
        assert "daily_quota_exceeded" in str(caught.value)

    def test_a_refused_message_stays_a_plain_error(self):
        with pytest.raises(EmailError):
            resend(422, {"message": "invalid to"}).send(MAIL)


class TestOneModelNameInTwoFiles:
    """The gateway only lets through models it is told about; the app names them.
    A model changed in one file and not the other must fail here, not in production."""

    def test_every_configured_model_is_allowed_by_the_gateway(self):
        import json

        from app.config import REPO_ROOT, get_settings

        llm = get_settings().llm
        gateway = json.loads((REPO_ROOT / "config" / "bifrost.json").read_text())
        allowed = {
            f"{config['provider']}/{model}"
            for key in gateway["governance"]["virtual_keys"]
            for config in key["provider_configs"]
            for model in config["allowed_models"]
        }

        # The provider lists only dated model ids; the key must name the alias
        # we use, or the gateway finds "no keys" for it.
        served = {
            f"{provider}/{model}"
            for provider, config in gateway["providers"].items()
            for key in config["keys"]
            for model in key.get("models", [])
        }

        configured = {llm.model_summary, llm.model_sentiment}
        assert configured <= allowed, "add the model to allowed_models in config/bifrost.json"
        assert configured <= served, "add the model to the key's models in config/bifrost.json"
