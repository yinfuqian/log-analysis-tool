import unittest

import httpx
from flask import Flask

from app.auth.account_requests import (
    AccountRequestError,
    AccountRequestService,
    HttpAccountRequestProvider,
    MockAccountRequestProvider,
)
from app.auth.routes import auth_bp


class FakeResponse:
    status_code = 200

    def __init__(self, payload=None):
        self.payload = payload or {"msg": "操作成功", "code": 200}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpSession:
    def __init__(self, error=None, response=None):
        self.error = error
        self.response = response or FakeResponse()
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class AccountRequestTests(unittest.TestCase):
    def test_mock_provider_returns_generated_request_metadata(self):
        service = AccountRequestService(MockAccountRequestProvider())

        result = service.submit("alice", "secret", "张三")

        self.assertTrue(result["request_id"].startswith("AR-"))
        self.assertIn("+", result["requested_at"])
        self.assertEqual(result["delivery_status"], "accepted")
        self.assertNotIn("password", result)

    def test_http_provider_maps_account_request_to_send_email_fields(self):
        session = FakeHttpSession()
        provider = HttpAccountRequestProvider(
            "https://notify.example/apply",
            token="api-token",
            timeout=7,
            session=session,
        )
        payload = {
            "request_id": "AR-1",
            "requested_at": "2026-07-18T17:00:00+08:00",
            "username": "alice",
            "password": "secret",
            "applicant_name": "张三",
        }

        result = provider.send(payload)

        self.assertEqual(result["code"], 200)
        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"], {
            "register_account": "alice",
            "register_user": "张三",
            "register_pwd": "secret",
        })
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer api-token")
        self.assertEqual(kwargs["timeout"], 7)

    def test_http_provider_rejects_failed_application_status(self):
        session = FakeHttpSession(response=FakeResponse({"msg": "操作失败", "code": 500}))
        provider = HttpAccountRequestProvider("https://notify.example/apply", session=session)

        with self.assertRaisesRegex(AccountRequestError, "请联系管理员"):
            provider.send({"username": "alice", "password": "secret", "applicant_name": "张三"})

    def test_http_failure_becomes_safe_account_request_error(self):
        provider = HttpAccountRequestProvider(
            "https://notify.example/apply",
            session=FakeHttpSession(httpx.TimeoutException("secret must not leak")),
        )

        with self.assertRaisesRegex(AccountRequestError, "请联系管理员") as raised:
            provider.send({"password": "secret"})

        self.assertNotIn("secret", str(raised.exception))

    def test_anonymous_endpoint_validates_fields_and_never_returns_password(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.extensions["account_request_service"] = AccountRequestService(MockAccountRequestProvider())
        app.register_blueprint(auth_bp, url_prefix="/auth")
        client = app.test_client()

        missing = client.post("/auth/account-requests", json={"username": "alice"})
        accepted = client.post("/auth/account-requests", json={
            "username": "alice",
            "password": "secret",
            "applicant_name": "张三",
        })

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(accepted.status_code, 202)
        self.assertNotIn("secret", accepted.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
