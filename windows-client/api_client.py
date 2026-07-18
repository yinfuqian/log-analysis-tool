"""api client 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import requests


class _AuthenticatedSession:
    """_AuthenticatedSession 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, client):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self._client = client

    def request(self, method, url, **kwargs):
        """提交 request 对应的业务数据，保持现有调用约定。"""
        return self._client._request_url(method, url, **kwargs)

    def get(self, url, **kwargs):
        """读取并返回 get 对应的业务数据，保持现有调用约定。"""
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        """处理 post 对应的业务步骤，并向调用方返回所需结果。"""
        return self.request("POST", url, **kwargs)


class ApiClient:
    """ApiClient 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, base_url, session=None, on_unauthorized=None):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.base_url = base_url.rstrip("/")
        self._raw_session = session or requests.Session()
        self.session = _AuthenticatedSession(self)
        self.on_unauthorized = on_unauthorized
        self.token = None

    def set_base_url(self, base_url):
        """设置或应用 set_base_url 对应的业务数据，保持现有调用约定。"""
        self.base_url = base_url.rstrip("/")

    def set_token(self, token):
        """设置或应用 set_token 对应的业务数据，保持现有调用约定。"""
        self.token = str(token).strip() if token else None

    def login(self, username, password):
        """处理 login 对应的业务步骤，并向调用方返回所需结果。"""
        response = self._request(
            "POST",
            "/auth/login",
            authenticated=False,
            timeout=10,
            json={"username": username, "password": password},
        )
        payload = response.json()
        token = payload.get("token")
        if not token:
            raise RuntimeError("登录响应缺少会话令牌")
        self.set_token(token)
        return payload.get("username") or str(username).strip()

    def request_account(self, username, password, applicant_name):
        """提交 request_account 对应的业务数据，保持现有调用约定。"""
        response = self._request(
            "POST",
            "/auth/account-requests",
            authenticated=False,
            timeout=10,
            json={
                "username": str(username or "").strip(),
                "password": str(password or ""),
                "applicant_name": str(applicant_name or "").strip(),
            },
        )
        return response.json()

    def logout(self):
        """处理 logout 对应的业务步骤，并向调用方返回所需结果。"""
        try:
            if self.token:
                self._request("POST", "/auth/logout", timeout=5)
        finally:
            self.set_token(None)

    def _request(self, method, path, authenticated=True, **kwargs):
        """提交 _request 对应的业务数据，保持现有调用约定。"""
        url = path if str(path).startswith(("http://", "https://")) else f"{self.base_url}/{str(path).lstrip('/')}"
        return self._request_url(method, url, authenticated=authenticated, **kwargs)

    def _request_url(self, method, url, authenticated=True, **kwargs):
        """提交 _request_url 对应的业务数据，保持现有调用约定。"""
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
