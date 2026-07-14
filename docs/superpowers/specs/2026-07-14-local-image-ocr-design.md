# Local Image OCR Analysis Design

## Goal

Make image inputs enter the same deterministic fault-analysis pipeline as text logs. Local OCR extracts screenshot text before chain discovery, while the original images remain attached to the single final multimodal AI request for visual verification.

## Decisions

- Use PaddleOCR for local Chinese/English text recognition and OpenCV for screenshot preprocessing.
- OCR is local inference and does not count as an AI API request.
- The web discovery request performs OCR before deciding whether upstream/downstream modules are involved.
- The client returns the server-produced OCR payload with the asynchronous analysis request so the Celery worker does not repeat OCR.
- If OCR is unavailable, fails, or returns no text, the system keeps the existing metadata and final-image fallback instead of failing the task.
- The final OpenAI-compatible multimodal analysis remains one request on a cache miss.

## Components

### OCR Adapter

Create `backend/app/analysis/image_ocr.py` as an isolated adapter. It lazily initializes one PaddleOCR engine per process, preprocesses screenshots with OpenCV, normalizes PaddleOCR 3.x and legacy result shapes, preserves image and line order, and returns:

- `available`: whether the local OCR runtime loaded.
- `engine`: the engine name.
- `extracted_text`: all accepted lines joined in reading order.
- `lines`: text, confidence, image index, and line index.
- `average_confidence`: average accepted confidence.
- `warnings`: non-fatal initialization or recognition messages.

The adapter accepts an injected engine in tests so unit tests do not require PaddleOCR models.

### Chain Discovery

For image input, `discover_related_modules` invokes the OCR adapter before `assess_chain_relevance`. Its source text consists of OCR text plus the image tag, description, and filenames. Therefore URLs, exception names, callback paths, and service names visible in screenshots participate in issue grouping and repository matching.

The discovery response includes `imageOcr`. The Windows client stores this payload and submits it as `image_ocr` with the analysis task.

### Analysis Task

For image input, the worker trusts only the structured fields produced by the server OCR adapter and builds `log_content` from `extracted_text` plus image metadata. It then runs the same functions used by text logs:

1. error information extraction;
2. full-file error-event extraction and grouping;
3. language detection;
4. upstream/downstream signal detection;
5. primary and related repository code lookup;
6. final combined report generation.

The original images are still passed to the final multimodal request to correct OCR ambiguity and provide UI context.

## Configuration And Deployment

- `LOCAL_OCR_ENABLED` controls local OCR and defaults to enabled.
- `OCR_MIN_CONFIDENCE` defaults to `0.45`.
- `PADDLE_PDX_CACHE_HOME` points at a persistent model-cache directory.
- Docker API and worker services mount the same model-cache directory.
- OCR dependencies are kept in `requirements-ocr.txt` and installed by the backend image, keeping the dependency boundary explicit.

## Failure Handling

- Missing PaddleOCR/OpenCV: return an unavailable OCR result and continue with image metadata and the final multimodal request.
- One unreadable image: record a warning and continue with the remaining images.
- Low-confidence line: omit it from deterministic parsing but retain the original image for final analysis.
- Empty OCR text: no fabricated error groups are created.
- A client-provided arbitrary string is not accepted as OCR evidence; only the structured payload returned by discovery is reused.

## Testing

- Normalize PaddleOCR 3.x output and preserve line order.
- Filter low-confidence text and combine multiple images.
- Verify OCR failure degrades without raising.
- Verify image chain discovery uses OCR text.
- Verify the client forwards `imageOcr` into `image_ocr`.
- Verify the task source calls the local OCR reuse path and still makes one final multimodal AI request.
- Run backend analysis, task-progress, upload, and Windows client suites.

## Out Of Scope

- Handwriting-specific model training.
- Persisting OCR results in a new database table.
- Removing original-image multimodal verification.
- Running OCR on ordinary text-log uploads.
