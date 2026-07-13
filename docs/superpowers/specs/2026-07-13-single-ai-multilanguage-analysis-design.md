# Single-AI Multilanguage Analysis Design

## Goal

Reduce AI usage without weakening full-file log coverage. The backend performs deterministic parsing, grouping, repository selection, and code evidence extraction. One final AI request receives all prepared evidence and produces the combined report.

Supported source and stack languages are Java, Python, Go, and Shell.

## Current Problem

The asynchronous task currently calls AI once for preliminary log analysis and a second time for combined log and code analysis. Image input can add another multimodal recognition call. This repeats the same log context, increases token use, and allows the preliminary result to bias or omit later errors.

The backend already scans the full log, extracts error events, resolves stack files, searches related repositories, and builds code snippets. These deterministic results should replace the preliminary AI call.

## Processing Flow

1. Read the complete input file once.
2. Detect the source language and extract every error event across the file.
3. Normalize and group duplicate events using exception type, message signature, stack origin, process/thread, and request trace where available.
4. Preserve each occurrence count, first/last location, representative context, and source log line range.
5. Resolve stack locations and component usages against the primary and selected upstream/downstream repositories.
6. Build a bounded structured evidence package containing every grouped issue and the strongest code/log evidence.
7. Submit one final AI request that returns the complete `issues` array and overall conclusion.
8. Persist the result in the knowledge cache. A matching future fingerprint uses zero AI calls.

Polling task status never calls AI and never creates another analysis task.

## Language Adapters

Language handling uses independent deterministic adapters with a common output shape: `language`, `file`, `line`, `symbol`, `error_type`, and `message`.

- Java: parse `Exception`/`Error`, `Caused by`, and `at package.Class.method(File.java:line)` frames. Search `.java`, `.kt`, `.groovy`, and JVM configuration files.
- Python: parse `Traceback`, `File "...", line N, in ...`, the terminal exception line, and chained exceptions. Search `.py` and Python configuration files.
- Go: parse `panic`, goroutine stacks, `file.go:line`, wrapped errors, and common runtime fatal lines. Search `.go`, `go.mod`, and `go.sum`.
- Shell: parse shell-prefixed failures, `script.sh: line N`, `script.sh:N`, command-not-found, non-zero exit, `set -e` exits, and common Bash diagnostics. Search `.sh`, `.bash`, `.zsh`, Dockerfiles, and shell-oriented deployment files.

Unknown formats remain eligible for generic ERROR/FATAL/Exception grouping so an unsupported line never disappears from the report.

## AI Request Policy

For text logs, the final combined report is exactly one AI request on a cache miss.

For images, OCR/business-context extraction and final reasoning are combined into one multimodal request. The request also includes backend-selected repository code evidence. There is no separate image-recognition request followed by a text request.

The prompt contains grouped evidence rather than the complete raw file when the file is large. Every group remains represented. Per-group context and code snippets are bounded independently so early errors cannot consume the budget intended for later errors.

## Report Contract

The final response remains JSON and contains:

- Overall category, conclusion, confidence, possible causes, and commands.
- An `issues` item for every backend error group, ordered by first occurrence.
- Each issue includes title, summary, root cause, solution, evidence, query commands, fix commands, and code locations.
- A backend-generated issue is retained as a fallback if AI omits it.
- Report metadata includes detected event count, grouped issue count, languages, repositories analyzed, code snippet count, cache status, and AI call count.

## Failure Handling

- If repository cloning or a related repository fails, continue with available evidence and record the missing repository.
- If no code location is found, keep the issue and state that it is supported by log evidence only.
- If the AI request fails, return a backend-generated structured diagnostic summary instead of discarding extracted issues.
- If task progress stalls, the existing client polling limit stops polling and reports the task ID for diagnosis.

## Testing

- Assert a text-log cache miss makes exactly one AI call.
- Assert a cache hit makes zero AI calls.
- Assert a multimodal analysis makes exactly one AI call.
- Cover Java, Python, Go, and Shell stack extraction and source-file resolution.
- Cover mixed-language logs and ensure every grouped issue appears in final output.
- Cover duplicate grouping without losing occurrence counts or later independent exceptions.
- Run backend route/task tests and Windows client report tests.

## Out of Scope

- Executing repair commands automatically.
- Replacing Git repository permissions or branch selection behavior.
- Sending the raw full log without size limits to the AI service.
