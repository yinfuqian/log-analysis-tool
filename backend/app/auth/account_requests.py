import secrets
from datetime import datetime, timedelta, timezone

import httpx

from .users import normalize_username


CHINA_TIMEZONE = timezone(timedelta(hours=8))


class AccountRequestError(RuntimeError):
    pass


class MockAccountRequestProvider:
    def send(self, payload):
        return {"message_id": f"mock-{payload['request_id']}"}


class HttpAccountRequestProvider:
    def __init__(self, url, token="", timeout=10, session=None):
        self.url = str(url or "").strip()
        self.token = str(token or "").strip()
        self.timeout = float(timeout)
        self.session = session or httpx.Client()

    def send(self, payload):
        if not self.url:
            raise AccountRequestError("账号申请失败，请联系管理员")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self.session.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise AccountRequestError("账号申请失败，请联系管理员") from exc
        return result if isinstance(result, dict) else {}


class AccountRequestService:
    def __init__(self, provider):
        self.provider = provider

    def submit(self, username, password, applicant_name):
        username = normalize_username(username)
        password = str(password or "")
        applicant_name = str(applicant_name or "").strip()
        missing = [
            name
            for name, value in (
                ("username", username),
                ("password", password),
                ("applicant_name", applicant_name),
            )
            if not value
        ]
        if missing:
            raise ValueError("缺少必要字段: " + ",".join(missing))

        requested_at = datetime.now(CHINA_TIMEZONE)
        request_id = f"AR-{requested_at:%Y%m%d%H%M%S}-{secrets.token_hex(3).upper()}"
        payload = {
            "request_id": request_id,
            "requested_at": requested_at.isoformat(timespec="seconds"),
            "applicant_name": applicant_name,
            "username": username,
            "password": password,
        }
        provider_result = self.provider.send(payload)
        return {
            "request_id": request_id,
            "requested_at": payload["requested_at"],
            "delivery_status": "accepted",
            "message_id": provider_result.get("message_id"),
        }


def build_account_request_service(config):
    provider_name = str(config.get("ACCOUNT_REQUEST_PROVIDER", "mock")).strip().lower()
    if provider_name == "mock":
        provider = MockAccountRequestProvider()
    elif provider_name == "http":
        provider = HttpAccountRequestProvider(
            config.get("ACCOUNT_REQUEST_API_URL"),
            token=config.get("ACCOUNT_REQUEST_API_TOKEN"),
            timeout=config.get("ACCOUNT_REQUEST_API_TIMEOUT", 10),
        )
    else:
        raise ValueError("ACCOUNT_REQUEST_PROVIDER 仅支持 mock 或 http")
    return AccountRequestService(provider)
