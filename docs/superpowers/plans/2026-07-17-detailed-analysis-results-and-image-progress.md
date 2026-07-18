# Detailed Analysis Results and Image Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore complete per-issue analysis with three-level navigation and keep image-analysis progress visible while safely degrading failed local OCR.

**Architecture:** Keep the existing normalized issue model as the single source for popup and HTML rendering. Add explicit issue rendering/navigation in the Windows popup and nested anchors in HTML. Treat all-image OCR prediction failure as unavailable while preserving original-image multimodal analysis.

**Tech Stack:** Python, Tkinter, HTML generation, PaddleOCR, unittest.

---

### Task 1: Restore detailed issue sections

**Files:**
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/tests/test_api_client.py`

- [ ] Add a failing test asserting `build_analysis_sections()` keeps separate `结论` and `问题明细` sections.
- [ ] Add a failing Tkinter test asserting the popup renders issue title, summary, root cause, evidence, solution, commands, and code.
- [ ] Remove the wrapper logic that renames the issue list to `问题结论` and deletes the overall conclusion.
- [ ] Add `_insert_issue_items()` and dispatch `issue_list` sections to it.
- [ ] Run `python -m unittest tests.test_api_client -v` and confirm the result tests pass.

### Task 2: Add three-level navigation

**Files:**
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/tests/test_api_client.py`

- [ ] Add failing tests for popup entries `问题明细 -> 问题1 -> 根因判断` and equivalent HTML links.
- [ ] Add issue and issue-detail marks to the popup listbox with two- and four-space indentation.
- [ ] Extend HTML issue cards with stable detail anchors and render nested issue-detail links in the table of contents.
- [ ] Run the result navigation and HTML tests.

### Task 3: Keep image progress visible

**Files:**
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/tests/test_api_client.py`

- [ ] Add a failing source/layout test proving the progress frame is packed before the image form.
- [ ] Move the progress frame above the form without changing progress update behavior.
- [ ] Run Windows client tests.

### Task 4: Mark complete OCR prediction failure unavailable

**Files:**
- Modify: `backend/app/analysis/image_ocr.py`
- Modify: `backend/tests/test_image_ocr.py`

- [ ] Add a failing test with an existing image and a predictor that raises, expecting `available=false` and a warning.
- [ ] Track attempted and failed predictions; return unavailable when every attempted image fails and no text is produced.
- [ ] Preserve partial success when at least one image predicts successfully.
- [ ] Run OCR and image-route tests.

### Task 5: Final verification

**Files:**
- Verify: `windows-client/`
- Verify: `backend/`

- [ ] Run all Windows client tests.
- [ ] Run backend OCR, async image-route, and task-progress tests.
- [ ] Run `git diff --check` on touched files.
- [ ] Build a new Windows executable after all tests pass.
