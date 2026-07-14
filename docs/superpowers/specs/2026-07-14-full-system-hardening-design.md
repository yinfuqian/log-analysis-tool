# Full-System Hardening And Maintainability Design

## Goal

Harden the log analyzer for authenticated use, remove unsafe trust in client-supplied paths and repository URLs, improve database integrity and transaction safety, reduce backend and frontend coupling, and make builds and verification reproducible without discarding the current OCR, multilingual analysis, knowledge-base, or Windows-client behavior.

The work will be delivered in independently verifiable phases. Existing public business URLs remain compatible during the migration unless a security boundary requires stricter validation.

## Scope And Delivery Order

1. Establish a reproducible test and migration baseline.
2. Add file-backed user authentication and mandatory authorization.
3. Harden uploads, analysis file references, Git access, CORS, and Markdown rendering.
4. Add database constraints, transaction boundaries, and efficient queries.
5. Extract backend services while retaining current API URLs.
6. Add web and Windows-client login flows and split oversized client modules.
7. Make Docker builds reproducible, add CI, and update operational documentation.

## Authentication And User Configuration

### User File

Users are managed through a JSON file whose path is configured by environment variable. There is no self-registration flow, administrator role, or user-management UI. Every configured user has the same application permissions.

Each entry contains:

- a normalized unique username;
- a strong password hash rather than a plaintext password;
- an enabled flag;
- a credential version that changes whenever the password or account state changes.

The repository includes a password-hash generation command. It reads the password interactively so the password does not need to be committed or passed as a command-line argument.

### Hot Reload

The backend caches the last valid user configuration and checks the file modification identity during authentication. A changed file is parsed and validated into a new immutable snapshot, then atomically replaces the previous snapshot.

If the changed file is missing, malformed, duplicated, or contains invalid password hashes, the backend keeps the last valid snapshot and logs a structured configuration error. A service that has never loaded a valid user file fails closed and exposes only the health endpoint.

### Session Model

`POST /auth/login` validates credentials and creates a cryptographically random opaque session token. Session state is stored in Redis and contains the username, credential version, creation time, and last-seen metadata. The raw token is returned only once; Redis stores a hash of it.

`POST /auth/logout` removes the current session. `GET /auth/me` returns the authenticated username and current session state.

Every protected request verifies:

1. the token exists in Redis;
2. the user still exists and is enabled in the current file snapshot;
3. the session credential version matches the current user entry.

Deleting or disabling a user, or changing that user's password or credential version, therefore invalidates all existing sessions immediately. All business endpoints are protected by default; only login and health checks are anonymous.

The web client stores the token in `sessionStorage`, so closing the browser tab or window removes local login state. The Windows client stores it only in process memory. Neither client implements remember-password behavior. A 401 response clears local session state and returns the user to the login screen.

### Login Abuse Controls

Login failures are rate-limited by normalized username and source address using Redis. Responses do not reveal whether a username exists. Successful authentication resets the relevant failure counter. Authentication events are logged without passwords or tokens.

## File And Upload Security

### Limits

- One log upload is limited to 100 MB.
- One image is limited to 10 MB.
- One request accepts at most 10 images.
- Total request size is enforced before application processing where possible.

Logs are processed as bounded streams or temporary files instead of being copied into memory without a limit. Images are checked by extension, MIME signature, actual decoder format, dimensions, and decompression-bomb safeguards. A failed multi-file upload removes all files created by that request.

### Server-Side File References

Analysis APIs stop treating client-supplied absolute `file_path` and `repo_path` values as trusted references. New requests use `log_id` or an opaque upload token. The backend resolves the stored path and verifies its real path is beneath the configured upload root.

During a compatibility period, old path fields are accepted only when their resolved path is beneath an approved root and corresponds to the expected stored record. Accepted legacy requests emit a deprecation log. Arbitrary existing server files are never readable through the API.

Temporary upload and repository cleanup uses real-path containment checks and task-scoped directories. Cleanup failures are logged and can be retried without deleting paths outside the configured roots.

## Git Security And Workspace Management

The configured Git service is the only allowed repository authority. Repository URLs must:

- use HTTPS;
- match the configured Git base host and allowed path prefix;
- reject embedded credentials, alternate schemes, localhost, raw IP targets, and unconfigured hosts;
- remain within the configured authority after normalization and redirects.

Git credentials are not embedded in command-line URLs. The Git adapter supplies credentials through a temporary, process-scoped credential mechanism that is removed after use and never included in logs or API errors.

Clone, branch lookup, and permission checks have explicit timeouts, bounded output capture, shallow-clone behavior where compatible, task-scoped workspace names, and disk-usage limits. Failed or cancelled operations clean up their workspace. Repository error responses are normalized and sanitized.

## Web Security

Markdown rendering disables raw HTML and passes generated output through DOMPurify with a narrow element, attribute, and URL-protocol allowlist. External links receive safe `rel` attributes.

CORS uses a configured origin allowlist and does not allow wildcard credentialed access. The backend adds appropriate content-type, frame, referrer, and content-security response headers. Mutating requests require the bearer session and use JSON or multipart content types expected by the endpoint.

## Database Integrity And Transactions

### Schema

New Alembic migrations add:

- foreign keys for `product_modules` and `module_branches`;
- unique constraints for `(product_id, module_id)` and `(module_id, branch_id)`;
- a unique or explicitly versioned constraint for repository address and tag combinations;
- indexes supporting product-module lookup, module-branch lookup, task history, and knowledge-case lookup;
- corrected foreign keys for query records on every supported upgrade path.

Before adding constraints, the migration deterministically removes duplicate relationship rows and reports or removes orphan rows according to the documented policy. Migration tests cover both an empty database and a representative legacy schema.

### Deletion Policy

Deleting a product or module removes configuration relationships but preserves analysis history. Historical records retain stable identifying fields even if the live configuration is later removed. Repository and branch records are deleted only when no configuration references remain.

### Transactions And Queries

Product, module, branch, and relationship mutations execute in one transaction. Validation occurs before writes; failures roll back the complete operation. Integrity errors produce a consistent conflict response rather than partial data.

List and search endpoints use joins or eager loading rather than querying modules and branches inside loops. Pagination and bounded result sizes are added where lists can grow.

## Backend Architecture

The current URLs remain stable while route modules become thin adapters over focused services:

- `auth`: user-file loading, password verification, sessions, and rate limiting;
- `uploads`: upload validation, storage, and opaque file references;
- `repositories`: URL policy, credentials, Git commands, and workspaces;
- `analysis`: task orchestration and domain-level analysis flow;
- `ai`: provider configuration, prompts, requests, and normalized failures;
- `knowledge`: fingerprints, cache lookup, and knowledge-case persistence;
- `products` and `modules`: configuration queries and transactional mutations.

Services expose explicit inputs and results and do not depend on Flask request globals. Celery tasks call the same services as synchronous routes. Route errors use a shared JSON shape containing a stable error code, a safe message, optional field details, and a request identifier.

The existing large analysis route and Windows-client module are reduced incrementally. Refactoring is performed alongside characterization tests so OCR, multilingual extraction, related-module discovery, knowledge hits, progress reporting, and cleanup semantics remain intact.

## Web Client

The web application gains a login page and global route guard. Business routes are not mounted as usable views until the current session has been validated.

All API modules share one Axios client that owns:

- the configured base URL;
- bearer-token injection;
- request timeout defaults;
- normalized error handling;
- 401 session cleanup and login redirection.

Duplicate API wrappers are consolidated. Element Plus remains the UI system. Unused `marked` and `vuetify` dependencies are removed. Frontend tests cover login, protected navigation, 401 handling, Markdown sanitization, upload limits, and the primary analysis flow.

## Windows Client

The Windows application opens a login window before creating the main business window. A successful login creates an in-memory authenticated API session. Logout, application exit, a 401 response, or a credential-version mismatch destroys that session and returns to login.

The current client module is split incrementally into:

- authenticated API client;
- login window;
- main window and shared state;
- upload and chain-evidence workflow;
- task progress handling;
- analysis-result window and rendering helpers.

The visible workflow and current analysis features remain compatible. Tests cover successful and failed login, token propagation, forced logout, application restart, and existing upload and analysis behavior.

## Deployment And Operations

The frontend uses a fixed supported Node LTS image, `npm ci`, and a multi-stage production build. Runtime containers do not install dependencies on startup.

The backend uses a fixed supported Python version and pinned dependency sets. Runtime containers use a non-root user and writable directories only for uploads, logs, model caches, and Git workspaces. API, worker, migration, Redis, and database readiness are represented with explicit health checks or documented external-service requirements.

Logging uses structured or consistently formatted output with request and task identifiers. File logging, when enabled, rotates by size or time. Sensitive values, session tokens, password hashes, repository credentials, and raw authorization headers are filtered.

The README and deployment documentation describe user-file creation, password-hash generation, hot reload, session invalidation, upload limits, Git authority configuration, database migration, rollback boundaries, and troubleshooting.

## Continuous Integration

CI runs on every change and includes:

- backend unit and integration tests;
- Windows-client tests on a compatible Python version;
- frontend lint, unit tests, and production build;
- Python compilation and configured style checks;
- Alembic upgrade from an empty database and a legacy-schema fixture;
- Docker Compose configuration validation;
- secret scanning and high-severity dependency scanning.

The project defines supported Python and Node versions so local and CI environments do not silently use incompatible runtimes. OCR-heavy tests inject adapters where model downloads are not required; a separate optional integration job can exercise the real OCR runtime.

## Error Handling And Compatibility

- Invalid user-file reload: keep the last valid snapshot and report an operational error.
- Redis unavailable: fail protected authentication closed and return a service-unavailable response.
- Invalid or oversized upload: reject before analysis and remove request-created artifacts.
- Invalid file reference: return a non-disclosing validation error.
- Disallowed or timed-out Git operation: return a sanitized repository error and clean the workspace.
- AI provider failure: preserve the current normalized service-error behavior and task progress state.
- Database integrity conflict: roll back and return a stable conflict code.
- Expired or invalidated session: return 401; both clients clear state and show login.

Compatibility adapters are temporary, observable, and covered by tests. Their removal criteria and target release are documented rather than left indefinitely.

## Testing Strategy

Each delivery phase begins with characterization or failing security tests and ends with the relevant complete suites. Required coverage includes:

- user-file parsing, atomic hot reload, invalid-file fallback, password verification, and immediate session invalidation;
- login rate limiting and non-enumerating errors;
- authorization on every blueprint and Celery task status/cancellation endpoint;
- arbitrary path rejection and approved-root containment on Windows and Linux path forms;
- upload count, byte, MIME, decoder, and decompression limits;
- Git authority normalization, credential redaction, timeout, cancellation, and cleanup;
- Markdown XSS payloads and safe-link behavior;
- relationship deduplication, foreign keys, transactions, deletion policy, and N+1 query regression;
- web and Windows login flows and 401 behavior;
- clean Docker builds and database upgrades.

## Out Of Scope

- Self-registration, password recovery email, administrator roles, or a user-management UI.
- Multiple Git service authorities unless explicitly added to the configuration format later.
- Replacing Redis, Celery, Flask, Vue, or the Windows UI toolkit.
- Redesigning the existing user-facing analysis workflow or visual style.
- Persisting login state after the browser tab or Windows application closes.
