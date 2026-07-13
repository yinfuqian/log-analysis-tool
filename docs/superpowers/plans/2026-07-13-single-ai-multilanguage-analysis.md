# Single-AI Multilanguage Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cache-miss analysis use one AI request while preserving every grouped error and extracting code evidence for Java, Python, Go, and Shell.

**Architecture:** Pure backend adapters turn mixed logs into normalized source locations and languages. Existing full-file event extraction is extended with deterministic grouping and a bounded backend summary. Both synchronous and Celery task flows feed that summary plus all repository code snippets into one final text or multimodal AI request.

**Tech Stack:** Python 3, Flask, Celery, OpenAI-compatible SDK, `unittest`, Tkinter client report normalization.

---

## File Structure

- Create `backend/app/analysis/language_adapters.py`: pure Java/Python/Go/Shell stack and source-location parsing.
- Modify `backend/app/analysis/routes/routes.py`: event grouping, bounded evidence rendering, one-call final analyzer, synchronous endpoint migration, shell-search suffixes.
- Modify `backend/app/analysis/routes/tasks.py`: asynchronous text/image flow migration and analysis metadata.
- Modify `backend/app/config.py`: advertise Shell as a supported language.
- Modify `backend/tests/test_async_analysis_routes.py`: language, grouping, prompt, and multimodal call tests.
- Modify `backend/tests/test_analysis_task_progress.py`: task evidence metadata tests.
- Modify `windows-client/tests/test_api_client.py`: report fallback coverage for grouped issues if required by payload changes.

### Task 1: Four-Language Source Location Adapters

**Files:**
- Create: `backend/app/analysis/language_adapters.py`
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_async_analysis_routes.py`

- [ ] **Step 1: Write failing Shell and mixed-language tests**

```python
def test_extracts_shell_script_file_and_line(self):
    routes, _, _, _, _ = load_routes_module()
    result = routes.extract_error_info_from_log(
        "deploy.sh: line 27: kubectl: command not found\n"
        "worker.sh:43: exit status 1\n"
    )
    self.assertEqual([(x["file"], x["line"]) for x in result], [
        ("deploy.sh", 27), ("worker.sh", 43),
    ])
    self.assertTrue(all(x["language"] == "shell" for x in result))

def test_supported_source_suffixes_include_shell(self):
    routes, _, _, _, _ = load_routes_module()
    self.assertTrue({".sh", ".bash", ".zsh"}.issubset(routes.SOURCE_CODE_SUFFIXES))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_extracts_shell_script_file_and_line backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_supported_source_suffixes_include_shell -v`

Expected: FAIL because Shell frames and suffixes are not supported.

- [ ] **Step 3: Implement normalized adapters**

```python
LANGUAGE_FRAME_PATTERNS = {
    "python": re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([^\n]+))?'),
    "go": re.compile(r'(?m)^\s+([^\s]+\.go):(\d+)(?:\s+\+0x[0-9a-fA-F]+)?'),
    "shell": re.compile(r'(?m)([^\s:]+\.(?:sh|bash|zsh))(?::\s*line\s+|:)(\d+)'),
}

def extract_source_locations(log_content):
    text = str(log_content or "")
    error_match = re.search(r"(?m)^\s*([\w.$]+(?:Exception|Error)|panic):?\s*(.*)$", text)
    error_type = error_match.group(1) if error_match else "unknown"
    message = error_match.group(2).strip() if error_match else "unknown error"
    locations = []
    seen = set()

    def add(language, file_name, line_number, symbol=""):
        key = (language, os.path.basename(file_name), int(line_number), symbol)
        if key in seen:
            return
        seen.add(key)
        locations.append({
            "language": language,
            "file": os.path.basename(file_name),
            "line": int(line_number),
            "symbol": symbol,
            "error_type": error_type,
            "message": message,
        })

    for file_name, line_number, symbol in LANGUAGE_FRAME_PATTERNS["python"].findall(text):
        add("python", file_name, line_number, symbol or "")
    for file_name, line_number in LANGUAGE_FRAME_PATTERNS["go"].findall(text):
        add("go", file_name, line_number)
    for file_name, line_number in LANGUAGE_FRAME_PATTERNS["shell"].findall(text):
        add("shell", file_name, line_number)
    for symbol, file_name, line_number in re.findall(
        r"(?m)^\s*at\s+([\w.$<>]+)\(([^():]+\.(?:java|kt|groovy)):(\d+)\)", text
    ):
        add("java", file_name, line_number, symbol)
    return locations
```

Import `extract_source_locations` in `routes.py`, make `extract_error_info_from_log` delegate location parsing while preserving its existing `error` field, and add `.sh`, `.bash`, `.zsh`, `Dockerfile`, `go.mod`, and `go.sum` search handling. Set `SUPPORTED_LANGUAGES = ['.java', '.py', '.go', '.sh', '.bash', '.zsh']`.

- [ ] **Step 4: Run focused language tests**

Run: `python -m unittest backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_extracts_python_traceback_file_and_line backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_extracts_go_panic_file_and_line backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_extracts_shell_script_file_and_line backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_supported_source_suffixes_include_shell -v`

Expected: PASS.

- [ ] **Step 5: Commit adapter changes**

```bash
git add backend/app/analysis/language_adapters.py backend/app/analysis/routes/routes.py backend/app/config.py backend/tests/test_async_analysis_routes.py
git commit -m "feat: add four-language log adapters"
```

### Task 2: Deterministic Full-File Grouping and Evidence Budgeting

**Files:**
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/app/analysis/routes/tasks.py`
- Test: `backend/tests/test_async_analysis_routes.py`
- Test: `backend/tests/test_analysis_task_progress.py`

- [ ] **Step 1: Write failing grouping tests**

```python
def test_groups_duplicate_errors_but_keeps_late_independent_exception(self):
    routes, _, _, _, _ = load_routes_module()
    log_content = """2026-06-24 10:00:00 ERROR asr transform error
SeeTaskException: Can not download file
    at demo.Asr.run(Asr.java:10)
2026-06-24 10:00:01 ERROR asr transform error
SeeTaskException: Can not download file
    at demo.Asr.run(Asr.java:10)
2026-06-24 10:00:02 ERROR asr transform error
SeeTaskException: Can not download file
    at demo.Asr.run(Asr.java:10)
2026-06-24 10:05:00 ERROR complaint analysis error
java.lang.NullPointerException: null
    at demo.Complaint.run(Complaint.java:42)
"""
    events = routes.extract_log_error_events(log_content)
    grouped = routes.group_log_error_events(events)
    self.assertEqual(len(grouped), 2)
    self.assertEqual(grouped[0]["occurrence_count"], 3)
    self.assertIn("NullPointerException", grouped[1]["representative_text"])
    self.assertLess(grouped[0]["first_line"], grouped[1]["first_line"])

def test_backend_summary_represents_every_group_with_independent_budget(self):
    routes, _, _, _, _ = load_routes_module()
    log_content = """2026-06-24 10:00:00 ERROR ASR transform error
SeeTaskException: Can not download file
    at demo.Asr.run(Asr.java:10)
2026-06-24 10:05:00 ERROR complaint analysis error
java.lang.NullPointerException: null
    at demo.Complaint.run(Complaint.java:42)
"""
    summary = routes.build_backend_log_analysis(log_content, max_chars=4000)
    self.assertIn("ASR", summary)
    self.assertIn("NullPointerException", summary)
    self.assertIn("occurrence_count", summary)
```

- [ ] **Step 2: Run grouping tests and verify RED**

Run: `python -m unittest backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_groups_duplicate_errors_but_keeps_late_independent_exception backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_backend_summary_represents_every_group_with_independent_budget -v`

Expected: FAIL because `group_log_error_events` and `build_backend_log_analysis` do not exist.

- [ ] **Step 3: Implement grouping and deterministic summary**

```python
def group_log_error_events(events):
    groups = []
    by_signature = {}
    for event in events:
        signature = build_log_event_signature(event["text"])
        if signature not in by_signature:
            group = {
                "signature": signature,
                "first_line": event["line"],
                "last_line": event["line"],
                "occurrence_count": 0,
                "representative_text": event["text"],
            }
            by_signature[signature] = group
            groups.append(group)
        group = by_signature[signature]
        group["occurrence_count"] += 1
        group["last_line"] = event["line"]
    return groups

def build_backend_log_analysis(log_content, max_chars=None):
    events = extract_log_error_events(log_content)
    groups = group_log_error_events(events)
    return render_grouped_error_evidence(groups, max_chars=max_chars)
```

The signature must normalize timestamps, request IDs, object addresses, and changing numbers while retaining exception/error type, stable message tokens, and the first application stack frame. Allocate a minimum per-group character budget before distributing remaining capacity.

- [ ] **Step 4: Add evidence metadata**

Extend `build_analysis_evidence` with `grouped_issue_count`, `detected_languages`, and `ai_call_count`, while retaining raw `log_error_event_count` and `log_error_events` for client fallback.

- [ ] **Step 5: Run grouping and task evidence tests**

Run: `python -m unittest backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress -v`

Expected: PASS.

- [ ] **Step 6: Commit grouping changes**

```bash
git add backend/app/analysis/routes/routes.py backend/app/analysis/routes/tasks.py backend/tests/test_async_analysis_routes.py backend/tests/test_analysis_task_progress.py
git commit -m "feat: group full-file log errors"
```

### Task 3: One AI Call for Text Logs

**Files:**
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/app/analysis/routes/tasks.py`
- Test: `backend/tests/test_async_analysis_routes.py`
- Test: `backend/tests/test_analysis_task_progress.py`

- [ ] **Step 1: Write failing call-count tests**

```python
def test_combined_text_analysis_calls_ai_once(self):
    routes, flask_stub, _, _, fake_openai = load_routes_module()
    flask_stub.current_app.config = {
        "OPENAI_KEY": "token",
        "OPENAI_URL": "https://example.invalid/v1",
        "OPENAI_MODEL": "gpt-test",
        "OPENAI_API_STYLE": "chat",
    }
    log_content = "ERROR failed\njava.lang.NullPointerException: null\n    at demo.Demo.run(Demo.java:42)"
    result = routes.analyze_code_with_deepseek(
        log_content,
        routes.build_backend_log_analysis(log_content),
        [{"file": "Demo.java", "line": 42, "snippet": "throw ex;"}],
    )
    self.assertEqual(result, "chat-result")
    self.assertEqual(len(fake_openai.last_instance.chat.completions.calls), 1)
```

Add this asynchronous task source assertion proving `analyze_log_task` no longer imports or invokes the preliminary AI helper:

```python
def test_async_task_uses_backend_summary_instead_of_preliminary_ai(self):
    source = TASKS_PATH.read_text(encoding="utf-8")
    self.assertNotIn("analyze_log_with_deepseek", source)
    self.assertIn("build_backend_log_analysis", source)
```

- [ ] **Step 2: Run call-count tests and verify RED**

Run: `python -m unittest backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress -v`

Expected: FAIL while the task still contains the preliminary AI stage.

- [ ] **Step 3: Replace preliminary AI analysis in both flows**

In `analyze_log_task`, replace:

```python
log_analysis = analyze_log_with_deepseek(analysis_log_content)
```

with:

```python
log_analysis = build_backend_log_analysis(analysis_log_content)
```

Do the same in `/analysis/log_analysis`. Keep `analyze_code_with_deepseek` as the only AI call. Rename progress text from “AI log analysis” to “backend log preprocessing” and set `analysis_evidence["ai_call_count"] = 1` on cache misses and `0` on knowledge-cache hits.

- [ ] **Step 4: Add backend fallback result**

If the final AI call fails, serialize the grouped backend evidence into the existing report contract with one fallback issue per group. Preserve code locations already resolved by the backend and record `ai_service_error` in metadata.

- [ ] **Step 5: Run backend task and route tests**

Run: `python -m unittest backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress -v`

Expected: PASS and no test observes more than one text AI request.

- [ ] **Step 6: Commit one-call text flow**

```bash
git add backend/app/analysis/routes/routes.py backend/app/analysis/routes/tasks.py backend/tests/test_async_analysis_routes.py backend/tests/test_analysis_task_progress.py
git commit -m "feat: use one AI call for text analysis"
```

### Task 4: One Multimodal AI Call for Images

**Files:**
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/app/analysis/routes/tasks.py`
- Test: `backend/tests/test_async_analysis_routes.py`

- [ ] **Step 1: Write failing multimodal call-count test**

```python
def test_final_image_analysis_uses_one_multimodal_request(self):
    routes, flask_stub, _, _, fake_openai = load_routes_module()
    flask_stub.current_app.config = {
        "OPENAI_KEY": "token",
        "OPENAI_URL": "https://example.invalid/v1",
        "OPENAI_MODEL": "gpt-test",
        "OPENAI_API_STYLE": "chat",
    }
    with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
        image_file.write(b"fake-png")
        image_file.flush()
        result = routes.analyze_code_with_deepseek(
            "image_tag=log_image",
            "backend image metadata",
            [],
            image_paths=[image_file.name],
        )
    self.assertEqual(result, "chat-result")
    self.assertEqual(len(fake_openai.last_instance.chat.completions.calls), 1)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest backend.tests.test_async_analysis_routes.AsyncAnalysisRouteTests.test_final_image_analysis_uses_one_multimodal_request -v`

Expected: FAIL because the final analyzer does not accept image paths.

- [ ] **Step 3: Route final analysis through one multimodal request**

Extend `analyze_code_with_deepseek(log_content, log_analysis, code_snippets, image_analysis=None, image_paths=None)`. When paths are present, convert all paths with `build_image_data_url` and call `call_ai_multimodal_model` once with the same final prompt. In `analyze_log_task`, stop calling `analyze_uploaded_image`; build deterministic context from `image_tag`, `image_description`, filenames, selected modules, and code evidence, then pass `image_paths=input_paths` to the final analyzer.

- [ ] **Step 4: Run image and text regression tests**

Run: `python -m unittest backend.tests.test_async_analysis_routes -v`

Expected: PASS; text uses one text request and image uses one multimodal request.

- [ ] **Step 5: Commit multimodal flow**

```bash
git add backend/app/analysis/routes/routes.py backend/app/analysis/routes/tasks.py backend/tests/test_async_analysis_routes.py
git commit -m "feat: combine image analysis into one request"
```

### Task 5: Full Regression and Report Contract Verification

**Files:**
- Modify if needed: `windows-client/log_analyzer_client.py`
- Test: `windows-client/tests/test_api_client.py`

- [ ] **Step 1: Add a report test for mixed grouped issues**

```python
def test_report_keeps_java_python_go_and_shell_backend_issues(self):
    payload = {"issue_conclusion": {"issues": [
        {"title": "Java NPE", "language": "java"},
        {"title": "Python zero division", "language": "python"},
        {"title": "Go nil pointer", "language": "go"},
        {"title": "Shell command missing", "language": "shell"},
    ]}}
    issues = client_module._normalize_issue_items(payload)
    self.assertEqual({x["language"] for x in issues}, {"java", "python", "go", "shell"})
```

- [ ] **Step 2: Run the test and verify RED or existing compatibility**

Run: `python -m unittest windows-client.tests.test_api_client -v`

Expected: PASS if current normalization is generic; otherwise FAIL on the missing language field.

- [ ] **Step 3: Make the minimal client compatibility change if RED**

Preserve `language`, `occurrence_count`, and backend fallback code locations while keeping the current HTML issue hierarchy unchanged.

- [ ] **Step 4: Run complete verification**

```bash
python -m unittest backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress backend.tests.test_async_config windows-client.tests.test_api_client -v
python -m py_compile backend/app/analysis/language_adapters.py backend/app/analysis/routes/routes.py backend/app/analysis/routes/tasks.py windows-client/log_analyzer_client.py
```

Expected: all tests PASS and compilation exits with status 0.

- [ ] **Step 5: Inspect AI call sites and diff hygiene**

Run: `rg -n "analyze_log_with_deepseek\(|call_ai_model\(|call_ai_multimodal_model\(" backend/app/analysis/routes backend/tests`

Expected: asynchronous and synchronous cache-miss flows each reach exactly one final AI call; helper definitions and direct unit tests may remain.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 6: Commit final compatibility changes**

```bash
git add windows-client/log_analyzer_client.py windows-client/tests/test_api_client.py
git commit -m "test: verify multilingual single-call reports"
```
