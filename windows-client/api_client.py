import requests


class _AuthenticatedSession:
    def __init__(self, client):
        self._client = client

    def request(self, method, url, **kwargs):
        return self._client._request_url(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class ApiClient:
    def __init__(self, base_url, session=None, on_unauthorized=None):
        self.base_url = base_url.rstrip("/")
        self._raw_session = session or requests.Session()
        self.session = _AuthenticatedSession(self)
        self.on_unauthorized = on_unauthorized
        self.token = None

    def set_base_url(self, base_url):
        self.base_url = base_url.rstrip("/")

    def set_token(self, token):
        self.token = str(token).strip() if token else None

    def login(self, username, password):
        response = self._request(
            "POST",
            "/auth/login",
            authenticated=False,
            json={"username": username, "password": password},
        )
        payload = response.json()
        token = payload.get("token")
        if not token:
            raise RuntimeError("登录响应缺少会话令牌")
        self.set_token(token)
        return payload.get("username") or str(username).strip()

    def request_account(self, username, password, applicant_name):
        response = self._request(
            "POST",
            "/auth/account-requests",
            authenticated=False,
            json={
                "username": str(username or "").strip(),
                "password": str(password or ""),
                "applicant_name": str(applicant_name or "").strip(),
            },
        )
        return response.json()

    def logout(self):
        try:
            if self.token:
                self._request("POST", "/auth/logout", timeout=5)
        finally:
            self.set_token(None)

    def _request(self, method, path, authenticated=True, **kwargs):
        url = path if str(path).startswith(("http://", "https://")) else f"{self.base_url}/{str(path).lstrip('/')}"
        return self._request_url(method, url, authenticated=authenticated, **kwargs)

    def _request_url(self, method, url, authenticated=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            kwargs["headers"] = headers

        request_method = getattr(self._raw_session, "request", None)
        if request_method:
            response = request_method(method, url, **kwargs)
        else:
            response = getattr(self._raw_session, method.lower())(url, **kwargs)

        if response.status_code == 401 and authenticated:
            self.set_token(None)
            if self.on_unauthorized:
                self.on_unauthorized()
        response.raise_for_status()
        return response
