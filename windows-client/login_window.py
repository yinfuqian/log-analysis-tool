import threading
import tkinter as tk
from tkinter import messagebox, ttk


class LoginWindow:
    def __init__(self, root, client, on_success, on_cancel):
        self.root = root
        self.client = client
        self.on_success = on_success
        self.on_cancel = on_cancel
        self.window = tk.Toplevel(root)
        self.window.title("日志分析客户端登录")
        self.window.geometry("420x270")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.grab_set()

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.status = tk.StringVar(value="请输入管理员分配的用户名和密码")
        self._build_layout()

    def _build_layout(self):
        frame = ttk.Frame(self.window, padding=28)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="用户登录", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor=tk.W, pady=(0, 18))

        ttk.Label(frame, text="用户名").pack(anchor=tk.W)
        username_entry = ttk.Entry(frame, textvariable=self.username)
        username_entry.pack(fill=tk.X, pady=(4, 12))

        ttk.Label(frame, text="密码").pack(anchor=tk.W)
        password_entry = ttk.Entry(frame, textvariable=self.password, show="●")
        password_entry.pack(fill=tk.X, pady=(4, 12))
        password_entry.bind("<Return>", lambda _event: self._submit())

        ttk.Label(frame, textvariable=self.status, foreground="#64748b").pack(anchor=tk.W, pady=(0, 12))
        self.login_button = ttk.Button(frame, text="登录", command=self._submit)
        self.login_button.pack(fill=tk.X)
        ttk.Button(frame, text="申请账号", command=self._open_account_request).pack(fill=tk.X, pady=(8, 0))
        username_entry.focus_set()

    def _open_account_request(self):
        AccountRequestDialog(self.window, self.client)

    def exists(self):
        return bool(self.window.winfo_exists())

    def _submit(self):
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            self.status.set("用户名和密码不能为空")
            return
        self.login_button.configure(state=tk.DISABLED)
        self.status.set("正在登录…")

        def authenticate():
            try:
                authenticated_username = self.client.login(username, password)
            except Exception as exc:
                self.root.after(0, lambda: self._show_error(exc))
                return
            self.password.set("")
            self.root.after(0, lambda: self._complete(authenticated_username))

        threading.Thread(target=authenticate, daemon=True).start()

    def _show_error(self, exc):
        self.password.set("")
        self.login_button.configure(state=tk.NORMAL)
        response = getattr(exc, "response", None)
        message = "登录失败，请检查用户名、密码和后端服务"
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("error") or message
        self.status.set(message)
        messagebox.showerror("登录失败", message, parent=self.window)

    def _complete(self, username):
        if self.exists():
            self.window.grab_release()
            self.window.destroy()
        self.on_success(username)

    def _cancel(self):
        self.password.set("")
        if self.exists():
            self.window.grab_release()
            self.window.destroy()
        self.on_cancel()


class AccountRequestDialog:
    def __init__(self, parent, client):
        self.parent = parent
        self.client = client
        self.window = tk.Toplevel(parent)
        self.window.title("申请账号")
        self.window.geometry("420x360")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        self.applicant_name = tk.StringVar()
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.status = tk.StringVar(value="请填写申请信息")
        self._build_layout()

    def _build_layout(self):
        frame = ttk.Frame(self.window, padding=24)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="申请账号", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor=tk.W, pady=(0, 16))
        for label, variable, show in (
            ("申请人姓名", self.applicant_name, None),
            ("申请用户名", self.username, None),
            ("申请密码", self.password, "●"),
        ):
            ttk.Label(frame, text=label).pack(anchor=tk.W)
            ttk.Entry(frame, textvariable=variable, show=show or "").pack(fill=tk.X, pady=(4, 10))
        ttk.Label(frame, textvariable=self.status, foreground="#64748b").pack(anchor=tk.W, pady=(0, 10))
        self.submit_button = ttk.Button(frame, text="提交申请", command=self._submit)
        self.submit_button.pack(fill=tk.X)
        ttk.Button(frame, text="关闭", command=self._close).pack(fill=tk.X, pady=(8, 0))

    def _submit(self):
        applicant_name = self.applicant_name.get().strip()
        username = self.username.get().strip()
        password = self.password.get()
        if not applicant_name or not username or not password:
            self.status.set("申请人姓名、用户名和密码不能为空")
            return
        self.submit_button.configure(state=tk.DISABLED)
        self.status.set("正在提交申请…")

        def submit_request():
            try:
                result = self.client.request_account(username, password, applicant_name)
            except Exception as exc:
                self.parent.after(0, lambda: self._show_error(exc))
                return
            self.parent.after(0, lambda: self._show_success(result))

        threading.Thread(target=submit_request, daemon=True).start()

    def _show_success(self, result):
        self.password.set("")
        self.submit_button.configure(state=tk.NORMAL)
        request_id = result.get("request_id") or ""
        self.status.set(f"申请已提交 {request_id}".strip())
        messagebox.showinfo("申请已提交", "账号申请已提交，请等待管理员处理", parent=self.window)

    def _show_error(self, exc):
        self.password.set("")
        self.submit_button.configure(state=tk.NORMAL)
        response = getattr(exc, "response", None)
        message = "账号申请失败，请联系管理员"
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                message = payload.get("error") or message
        self.status.set(message)
        messagebox.showerror("申请失败", message, parent=self.window)

    def _close(self):
        self.password.set("")
        self.window.grab_release()
        self.window.destroy()
