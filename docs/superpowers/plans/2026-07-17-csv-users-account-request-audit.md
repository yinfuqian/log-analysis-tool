# CSV Users, Account Requests, and Audit Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace JSON hashed users with hot-reloaded plaintext CSV, add anonymous account requests to both clients through a configurable notification provider, allow anonymous page browsing while protecting all business APIs, and persist sanitized API audit records.

**Architecture:** `UserStore` parses CSV snapshots and derives a stable non-plaintext credential fingerprint for Redis sessions. A focused account-request service validates and forwards requests through Mock or HTTP providers without persistence. Flask request hooks enforce the small anonymous whitelist and write sanitized audit rows after responses.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy/Alembic, Redis, Vue 3, Axios, Tkinter, unittest/Jest.

---

### Task 1: Hot-reloaded CSV users

**Files:**
- Modify: `backend/app/auth/users.py`
- Modify: `backend/app/auth/sessions.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_auth_users.py`
- Modify: `backend/tests/test_auth_sessions.py`
- Modify: `.env.example`

- [ ] Write failing tests using `username,password,status` CSV for login, duplicate names, invalid status, hot reload, password-change invalidation, deletion, and status `0/2` invalidation.
- [ ] Run `python -m unittest backend.tests.test_auth_users backend.tests.test_auth_sessions -v` and confirm JSON-only behavior fails.
- [ ] Implement CSV parsing with Python `csv.DictReader`, require fields, normalize usernames, accept only statuses `0/1/2`, and derive `credential_version = sha256(username + NUL + password)` without retaining it in Redis as plaintext.
- [ ] Keep the last valid snapshot when reload fails; allow authentication only when status is `1`.
- [ ] Change the default `AUTH_USERS_FILE` to `/data/users.csv` and document the CSV example.
- [ ] Run auth tests and commit `feat: manage users from hot-reloaded csv`.

### Task 2: Configurable anonymous account request API

**Files:**
- Create: `backend/app/auth/account_requests.py`
- Modify: `backend/app/auth/routes.py`
- Modify: `backend/app/config.py`
- Create: `backend/tests/test_account_requests.py`
- Modify: `.env.example`

- [ ] Write failing tests for required fields, Mock success, HTTP payload forwarding, optional Bearer token, timeouts, failure message, and no password logging/persistence.
- [ ] Run `python -m unittest backend.tests.test_account_requests -v` and confirm the endpoint/provider is missing.
- [ ] Implement `MockAccountRequestProvider` and `HttpAccountRequestProvider`, selected by `ACCOUNT_REQUEST_PROVIDER`; generate `AR-<timestamp>-<random>` IDs and ISO timestamps.
- [ ] Add anonymous `POST /auth/account-requests`; validate username/password/applicant name and return only request ID, time, and status.
- [ ] Configure provider URL, token, and timeout from `.env`; never log payloads.
- [ ] Run tests and commit `feat: add configurable account request endpoint`.

### Task 3: Public page browsing and protected business APIs

**Files:**
- Modify: `backend/app/auth/middleware.py`
- Modify: `backend/tests/test_auth_routes.py`
- Modify: `frontend/app/log-analyze/src/router/index.js`
- Modify: `frontend/app/log-analyze/src/api/client.js`
- Modify: `frontend/app/log-analyze/tests/unit/auth.spec.js`

- [ ] Write failing tests proving login, account request, health, and OPTIONS are anonymous while all business APIs return `401` without a token.
- [ ] Write failing router tests proving anonymous users may enter business routes.
- [ ] Implement the backend whitelist and remove the frontend route redirect guard; retain API `401` handling and show the login route when a user attempts a protected action.
- [ ] Run backend and frontend auth tests and commit `feat: allow anonymous browsing with protected actions`.

### Task 4: Database operation audit logs

**Files:**
- Create: `backend/app/audit/models.py`
- Create: `backend/app/audit/service.py`
- Create: `backend/migrations/versions/7c9a4f21d801_user_operation_logs.py`
- Modify: `backend/app/__init__.py`
- Create: `backend/tests/test_operation_audit.py`

- [ ] Write failing tests for authenticated username, anonymous login/apply target username, unauthorized `401`, request ID, duration, status, skipped health/OPTIONS, and sensitive field exclusion.
- [ ] Implement `UserOperationLog` and migration with indexed `operator_username`, `request_path`, and `created_at`.
- [ ] Add request hooks that generate a request ID and start time, then write one sanitized audit row after the response.
- [ ] Catch audit database failures, rollback, log the error, and return the original response unchanged.
- [ ] Run audit/auth tests and commit `feat: persist sanitized user operation audit logs`.

### Task 5: Web and Windows account request forms

**Files:**
- Modify: `frontend/app/log-analyze/src/views/LoginView.vue`
- Modify: `frontend/app/log-analyze/src/assets/styles/login.css`
- Create: `frontend/app/log-analyze/src/api/accountRequests.js`
- Modify: `frontend/app/log-analyze/tests/unit/login.spec.js`
- Modify: `windows-client/login_window.py`
- Modify: `windows-client/api_client.py`
- Modify: `windows-client/tests/test_auth_client.py`

- [ ] Write failing tests for opening the request form, three required inputs, anonymous request calls, success feedback, failure feedback, and password clearing.
- [ ] Implement the Vue request form and API module without storing the password.
- [ ] Add `request_account` to the Windows API client and an account-request dialog to the login window; clear password fields after every attempt.
- [ ] Run Windows tests, frontend tests, lint, and production build.
- [ ] Run the full backend regression in isolated test processes and commit `feat: add account requests to web and desktop clients`.
