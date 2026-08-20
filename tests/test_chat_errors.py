import os
import unittest
from unittest.mock import patch

import anthropic
import httpx
from fastapi.testclient import TestClient

from app.main import app


CONFIGURATION_MESSAGE = (
    "Le service IA est indisponible en raison d'un problème de configuration."
)
CONNECTION_MESSAGE = (
    "Impossible de contacter le service IA. Vérifiez votre connexion et réessayez."
)
TIMEOUT_MESSAGE = "Le service IA met trop de temps à répondre. Veuillez réessayer."
RATE_LIMIT_MESSAGE = (
    "Le service IA est temporairement surchargé. "
    "Veuillez réessayer dans quelques instants."
)
API_MESSAGE = "Le service IA a rencontré une erreur. Veuillez réessayer."
INTERNAL_MESSAGE = "Une erreur interne est survenue. Veuillez réessayer."
SENSITIVE_DETAIL = "sk-ant-secret-test technical provider detail"


class ChatErrorHandlingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
        )

    def tearDown(self) -> None:
        self.client.close()

    def status_error(self, error_class, status_code: int):
        response = httpx.Response(
            status_code,
            request=self.request,
            json={"error": {"message": SENSITIVE_DETAIL}},
        )
        return error_class(
            SENSITIVE_DETAIL,
            response=response,
            body={"error": {"message": SENSITIVE_DETAIL}},
        )

    def assert_controlled_error(
        self,
        exception: Exception,
        expected_status: int,
        expected_message: str,
    ) -> None:
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}),
            patch("app.main.run_agent", side_effect=exception),
        ):
            response = self.client.post("/chat", json={"message": "Test sans Claude"})

        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(response.json(), {"detail": expected_message})
        self.assertNotIn(SENSITIVE_DETAIL, response.text)
        self.assertNotIn("sk-ant", response.text)

    def test_missing_api_key_returns_safe_json(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.main.run_agent") as run_agent,
        ):
            response = self.client.post("/chat", json={"message": "Test sans clé"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": CONFIGURATION_MESSAGE})
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertNotIn("ANTHROPIC_API_KEY", response.text)
        run_agent.assert_not_called()

    def test_invalid_api_key_returns_configuration_error(self):
        self.assert_controlled_error(
            self.status_error(anthropic.AuthenticationError, 401),
            503,
            CONFIGURATION_MESSAGE,
        )

    def test_connection_error_returns_service_unavailable(self):
        self.assert_controlled_error(
            anthropic.APIConnectionError(
                message=SENSITIVE_DETAIL,
                request=self.request,
            ),
            503,
            CONNECTION_MESSAGE,
        )

    def test_timeout_returns_gateway_timeout(self):
        self.assert_controlled_error(
            anthropic.APITimeoutError(request=self.request),
            504,
            TIMEOUT_MESSAGE,
        )

    def test_rate_limit_returns_retry_message(self):
        self.assert_controlled_error(
            self.status_error(anthropic.RateLimitError, 429),
            429,
            RATE_LIMIT_MESSAGE,
        )

    def test_anthropic_status_error_returns_bad_gateway(self):
        self.assert_controlled_error(
            self.status_error(anthropic.APIStatusError, 500),
            502,
            API_MESSAGE,
        )

    def test_generic_anthropic_error_returns_bad_gateway(self):
        self.assert_controlled_error(
            anthropic.APIError(
                SENSITIVE_DETAIL,
                self.request,
                body={"secret": SENSITIVE_DETAIL},
            ),
            502,
            API_MESSAGE,
        )

    def test_unexpected_error_returns_internal_error(self):
        self.assert_controlled_error(
            RuntimeError(SENSITIVE_DETAIL),
            500,
            INTERNAL_MESSAGE,
        )


if __name__ == "__main__":
    unittest.main()
