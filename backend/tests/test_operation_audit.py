import unittest

from flask import Flask, g, jsonify

from app.audit.service import install_operation_audit


class OperationAuditTests(unittest.TestCase):
    def make_app(self, writer):
        app = Flask(__name__)
        app.config["TESTING"] = True
        install_operation_audit(app, writer)

        @app.get("/business")
        def business():
            g.current_user = type("User", (), {"username": "alice"})()
            return jsonify({"password": "response-secret"})

        @app.post("/auth/login")
        def login():
            return jsonify({"token": "secret-token"})

        @app.post("/auth/account-requests")
        def account_request():
            return jsonify({"ok": True}), 202

        @app.get("/unauthorized")
        def unauthorized():
            return jsonify({"error": "login"}), 401

        @app.get("/health/live")
        def health():
            return jsonify({"ok": True})

        return app

    def test_records_authenticated_operation_without_sensitive_content(self):
        rows = []
        client = self.make_app(rows.append).test_client()

        response = client.get("/business", headers={"Authorization": "Bearer secret-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(rows[0]["operator_username"], "alice")
        self.assertEqual(rows[0]["actor_type"], "authenticated")
        self.assertEqual(rows[0]["request_method"], "GET")
        self.assertEqual(rows[0]["request_path"], "/business")
        self.assertGreaterEqual(rows[0]["duration_ms"], 0)
        self.assertNotIn("password", rows[0])
        self.assertNotIn("token", str(rows[0]).lower())
        self.assertEqual(response.headers["X-Request-ID"], rows[0]["request_id"])

    def test_records_login_and_account_request_target_usernames(self):
        rows = []
        client = self.make_app(rows.append).test_client()

        client.post("/auth/login", json={"username": "Alice", "password": "secret"})
        client.post("/auth/account-requests", json={
            "username": "new-user",
            "password": "request-secret",
            "applicant_name": "张三",
        })

        self.assertEqual(rows[0]["target_username"], "alice")
        self.assertEqual(rows[1]["target_username"], "new-user")
        self.assertTrue(all(row["actor_type"] == "anonymous" for row in rows))
        self.assertNotIn("secret", str(rows))

    def test_records_unauthorized_and_skips_health_and_options(self):
        rows = []
        client = self.make_app(rows.append).test_client()

        client.get("/unauthorized")
        client.get("/health/live")
        client.open("/business", method="OPTIONS")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status_code"], 401)
        self.assertEqual(rows[0]["operation_result"], "failed")

    def test_writer_failure_does_not_change_business_response(self):
        def broken_writer(_row):
            raise RuntimeError("database unavailable")

        app = self.make_app(broken_writer)
        response = app.test_client().get("/business")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
