# Local Image OCR Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract screenshot text locally before chain discovery and route that text through the same deterministic analysis pipeline as uploaded log files.

**Architecture:** A focused OCR adapter owns PaddleOCR/OpenCV integration and returns a stable dictionary contract. The discovery endpoint computes OCR once, the client forwards that result, and the Celery task reuses it while retaining original images for one final multimodal AI request.

**Tech Stack:** Python 3.10, PaddleOCR 3.x, PaddlePaddle CPU, OpenCV headless, Flask, Celery, Tkinter, `unittest`.

---

### Task 1: Local OCR Adapter

**Files:**
- Create: `backend/app/analysis/image_ocr.py`
- Test: `backend/tests/test_image_ocr.py`

- [ ] Write tests for PaddleOCR 3.x output normalization, confidence filtering, multiple-image ordering, and unavailable-runtime degradation.
- [ ] Run `python -m unittest backend.tests.test_image_ocr -v` and verify failures because the adapter does not exist.
- [ ] Implement lazy engine initialization, OpenCV preprocessing, result normalization, and the stable OCR result contract.
- [ ] Run `python -m unittest backend.tests.test_image_ocr -v` and verify all adapter tests pass.

### Task 2: OCR-Aware Chain Discovery

**Files:**
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/tests/test_async_analysis_routes.py`

- [ ] Add a failing route test where OCR text contains a downstream URL and `discover_related_modules_route` returns `requiresRelatedEvidence=true` with `imageOcr`.
- [ ] Run the targeted test and verify the current metadata-only implementation fails.
- [ ] Add an image-source helper that calls the OCR adapter and merges OCR text with safe metadata before chain assessment.
- [ ] Return the structured `imageOcr` payload from discovery and rerun the targeted route tests.

### Task 3: Client OCR Reuse

**Files:**
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/tests/test_api_client.py`

- [ ] Add a failing client test proving `imageOcr` from discovery is forwarded as `image_ocr` in task submission.
- [ ] Run the targeted client test and verify the submission currently omits OCR data.
- [ ] Store the discovery OCR payload in `upload_result` and extend `submit_analysis_task` with the structured `image_ocr` field.
- [ ] Rerun the targeted client tests.

### Task 4: Unified Worker Pipeline

**Files:**
- Modify: `backend/app/analysis/routes/tasks.py`
- Modify: `backend/tests/test_analysis_task_progress.py`
- Modify: `backend/tests/test_async_analysis_routes.py`

- [ ] Add a failing task-source test requiring image OCR text to become `log_content` before `extract_log_error_events` and `build_backend_log_analysis`.
- [ ] Add a test proving the original images still use exactly one final multimodal request.
- [ ] Implement OCR payload validation/reuse and a local fallback when discovery did not provide OCR.
- [ ] Normalize `image_analysis` from OCR output and route it through existing log grouping, code lookup, and reporting.
- [ ] Run task and analysis tests.

### Task 5: Runtime Packaging And Verification

**Files:**
- Create: `backend/requirements-ocr.txt`
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] Add PaddlePaddle CPU, PaddleOCR, OpenCV headless, and NumPy runtime dependencies with explicit versions compatible with Python 3.10.
- [ ] Configure a persistent Paddle model-cache directory for API and worker services.
- [ ] Run `python -m py_compile` for modified Python modules.
- [ ] Run all affected backend and Windows client tests.
- [ ] Run `git diff --check` and inspect the final diff for unrelated changes.
