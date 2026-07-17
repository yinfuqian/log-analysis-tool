import sys
import unittest
import importlib.util
import inspect
from pathlib import Path

import requests


CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from api_client import ApiClient


def load_main_module():
    client_path = CLIENT_DIR / "log_analyzer_client.py"
    spec = importlib.util.spec_from_file_location("authenticated_client_under_test", client_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


class ApiClientAuthTests(unittest.TestCase):
    def test_login_keeps_token_only_in_memory_and_authorizes_later_requests(self):
        session = FakeSession([
            FakeResponse({"token": "session-token", "username": "alice"}),
            FakeResponse({"products": []}),
        ])
        client = ApiClient("http://backend", session=session)

        username = client.login("alice", "secret")
        client._request("GET", "/product/get")

        self.assertEqual(username, "alice")
        self.assertEqual(client.token, "session-token")
        self.assertNotIn("Authorization", session.requests[0][2].get("headers", {}))
        self.assertEqual(
            session.requests[1][2]["headers"]["Authorization"],
            "Bearer session-token",
        )

    def test_unauthorized_response_clears_token_and_notifies_application(self):
        notifications = []
        session = FakeSession([FakeResponse({"message": "expired"}, status_code=401)])
        client = ApiClient(
            "http://backend",
            session=session,
            on_unauthorized=lambda: notifications.append("unauthorized"),
        )
        client.set_token("session-token")

        with self.assertRaises(requests.HTTPError):
            client._request("GET", "/product/get")

        self.assertIsNone(client.token)
        self.assertEqual(notifications, ["unauthorized"])

    def test_logout_revokes_server_session_then_forgets_local_token(self):
        session = FakeSession([FakeResponse({"message": "ok"})])
        client = ApiClient("http://backend", session=session)
        client.set_token("session-token")

        client.logout()

        self.assertIsNone(client.token)
        self.assertEqual(session.requests[0][1], "http://backend/auth/logout")
        self.assertEqual(
            session.requests[0][2]["headers"]["Authorization"],
            "Bearer session-token",
        )

    def test_account_request_is_anonymous_and_returns_request_metadata(self):
        session = FakeSession([FakeResponse({"request_id": "AR-1", "delivery_status": "accepted"}, status_code=202)])
        client = ApiClient("http://backend", session=session)

        result = client.request_account("new-user", "request-secret", "张三")

        self.assertEqual(result["request_id"], "AR-1")
        method, url, kwargs = session.requests[0]
        self.assertEqual((method, url), ("POST", "http://backend/auth/account-requests"))
        self.assertEqual(kwargs["json"], {
            "username": "new-user",
            "password": "request-secret",
            "applicant_name": "张三",
        })
        self.assertNotIn("Authorization", kwargs.get("headers", {}))

    def test_log_analyzer_api_uses_authenticated_session_for_business_calls(self):
        module = load_main_module()
        session = FakeSession([FakeResponse({"products": []})])
        client = module.LogAnalyzerApiClient("http://backend", session=session)
        client.set_token("session-token")

        products = client.get_products()

        self.assertEqual(products, [])
        self.assertEqual(
            session.requests[0][2]["headers"]["Authorization"],
            "Bearer session-token",
        )

    def test_main_window_accepts_the_authenticated_client_created_at_login(self):
        module = load_main_module()

        parameters = inspect.signature(module.LogAnalyzerWindow.__init__).parameters

        self.assertIn("api_client", parameters)

    def test_application_opens_login_before_creating_main_window(self):
        module = load_main_module()
        events = []

        class FakeRoot:
            def withdraw(self):
                events.append("withdraw")

            def deiconify(self):
                events.append("deiconify")

            def after(self, delay, callback):
                events.append(("after", delay))
                callback()

            def destroy(self):
                events.append("destroy")

        class FakeClient:
            def __init__(self, base_url, on_unauthorized=None):
                self.base_url = base_url
                self.on_unauthorized = on_unauthorized

        class FakeLoginWindow:
            def __init__(self, root, client, on_success, on_cancel):
                events.append("login")
                self.on_success = on_success

            def exists(self):
                return True

        class FakeMainWindow:
            def __init__(self, root, api_client=None):
                events.append(("main", api_client))

        module.LogAnalyzerApiClient = FakeClient
        module.LoginWindow = FakeLoginWindow
        module.LogAnalyzerWindow = FakeMainWindow

        application = module.ClientApplication(FakeRoot())

        self.assertEqual(events[:2], ["withdraw", "login"])
        self.assertNotIn("main", events)

        application.login_window.on_success("alice")

        self.assertEqual(events[2][0], "main")

    def test_closing_main_window_revokes_the_authenticated_session(self):
        module = load_main_module()
        events = []

        class FakeClient:
            def logout(self):
                events.append("logout")

        class FakeRoot:
            def destroy(self):
                events.append("destroy")

        window = object.__new__(module.LogAnalyzerWindow)
        window.api_client = FakeClient()
        window.root = FakeRoot()
        window._stop_progress_animation = lambda: events.append("stop")

        window._on_close()

        self.assertEqual(events, ["stop", "logout", "destroy"])


if __name__ == "__main__":
    unittest.main()
