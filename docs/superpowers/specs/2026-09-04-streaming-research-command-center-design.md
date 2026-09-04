# Streaming Research Command Center Design

## Purpose and scope

Transform the existing synchronous, print-driven research pipeline into a
local web application. The application will retain Gemini as its runtime model
and the existing Tavily and extraction tool contracts, while adding safe,
observable streaming to a React command center.

This design covers an asynchronous four-stage pipeline, a FastAPI SSE API, a
React/Vite/TypeScript/Tailwind user interface, offline tests, CI, and accurate
documentation. It does not add durable storage, multi-process coordination,
live-provider tests, remote deployment, or a Streamlit interface.

## Decisions

- Run at most one research job at a time. Later submissions are queued in
  creation order.
- An explicit cancellation transitions the run to `cancelled` and immediately
  starts the next queued run. Any late provider output from the cancelled run
  is ignored.
- A client disconnect never cancels research; only `DELETE /api/runs/{run_id}`
  does.
- Keep the existing `run_research_pipeline(topic)` synchronous compatibility
  interface and its legacy `feedback` result key. The asynchronous and HTTP
  interfaces use the clearer `critique` name.
- The application accepts only safe, filtered domain events. It never sends
  credentials, model reasoning, raw exceptions, raw provider events, raw tool
  diagnostics, or unfiltered provider metadata to a browser.
- The registry is process-local. A restart loses run data and production runs
  with exactly one Uvicorn worker.

## Architecture

```text
React command center
        |
        | POST / snapshot / SSE / DELETE / downloads
        v
FastAPI app and run registry
        |
        | typed, safe pipeline events
        v
stream_research_pipeline(topic)
        |
        +--> Search LangGraph agent --> existing Tavily tool
        +--> Reader LangGraph agent --> existing extraction tool
        +--> Writer LangChain chain
        +--> Critic LangChain chain
```

`src/pipelines/` owns sequencing and typed domain events. Agent and model
construction remains in `src/agents/`; external retrieval and extraction
remain in `src/tools/`. `src/api/` owns HTTP formatting, event replay, task
ownership, queueing, and snapshots. The frontend owns view state and never
contains Gemini or Tavily configuration.

### Pipeline

Add an async generator with the public shape:

```python
async def stream_research_pipeline(topic: str, ...) -> AsyncIterator[PipelineEvent]:
    ...
```

Pipeline events are typed, domain-level values for agent status changes, safe
agent summaries, text deltas, a completed result, failure, and cancellation.
The pipeline explicitly sequences Search, Reader, Writer, and Critic. Search
and Reader consume LangChain/LangGraph event streams through a narrow adapter;
Writer and Critic stream their generated text. The adapter accepts only text
deltas and concise, scrubbed summaries. It normalizes structured message
content before passing it to the next stage.

Provider construction is lazy and dependencies are injectable. Default tests
use scripted async stage runners rather than credentials, Gemini, Tavily, or
HTTP. A cooperative cancellation signal is checked between stages and while
iterating events. `CancelledError` is handled as an intentional terminal
condition. Blocking retrieval already in progress may finish in a worker, but
the cancelled pipeline can publish no later events.

`run_research_pipeline(topic)` synchronously collects the async stream,
returning `search_results`, `scraped_content`, `report`, and `feedback`.
Calling it from an active event loop raises a concise instruction to use the
async interface instead.

### API and run lifecycle

`create_app(...)` provides dependency injection for a pipeline factory, clock,
run ID source, and keepalive interval. The in-memory registry holds a run
snapshot, append-only event history, a task handle, cancellation state, and
per-run subscriber notifications. It retains the newest 20 terminal runs and
never evicts an active run.

Run status follows:

```text
queued -> running -> completed | failed | cancelled
```

An agent is `pending`, `running`, `completed`, `failed`, `cancelled`, or
`skipped`. A central, lock-protected terminal transition makes terminal events
exactly once and prevents a completion/cancellation race. A per-run event ID
starts at one and increases monotonically. Each event envelope includes `id`,
`run_id`, RFC3339 UTC `timestamp`, `type`, optional `agent`, and a
type-specific safe payload.

Routes:

- `POST /api/runs` accepts `{"topic": string}`. It trims input, rejects blank
  input and topics longer than 1000 characters, queues the run, and returns
  `202` with the run ID, status, snapshot URL, event URL, and download URLs.
- `GET /api/runs/{run_id}` returns the topic, run status, four agent statuses,
  accumulated summaries, report, critique, and a safe terminal error if any.
- `GET /api/runs/{run_id}/events` returns `text/event-stream`. It frames each
  persisted event as `id`, `event`, and JSON `data` lines; replays IDs strictly
  newer than `Last-Event-ID`; emits comment keepalives; and closes after the
  terminal event is delivered.
- `DELETE /api/runs/{run_id}` cancels queued or active work, updates active
  agents to cancelled and unstarted agents to skipped, and is idempotent.
- `GET /api/runs/{run_id}/downloads/report.md` and
  `GET /api/runs/{run_id}/downloads/result.json` return artifacts only for a
  completed run. They return `409` before completion and `404` for unknown or
  evicted runs.

Use `asyncio.create_task` so the registry can own and cancel the task. Every
subscriber reads a cursor from shared history; no single queue divides events
between clients. Backpressure from an SSE client never blocks the producer.
FastAPI serves `frontend/dist` only when present, mounts API routes first, and
provides SPA fallback without shadowing `/api`.

### Frontend

The npm project lives exclusively under `frontend/` to avoid changing the
existing release workflow's root package behavior. It uses React, Vite,
TypeScript, Tailwind's Vite plugin, and a committed `package-lock.json`.
`package.json` declares Node `>=22.13.0` and npm `>=10`; CI uses Node 22.13.0.

The research feature models API events as a discriminated TypeScript union and
reduces them with a pure state reducer. It records the greatest event ID and
ignores duplicate or stale events. An injected EventSource factory supports
unit testing. The client treats transient EventSource errors as reconnecting,
not as research failure, and reconciles with the snapshot endpoint after
terminal transitions or repeated reconnect errors.

The Command Center contains a labelled, 1000-character topic input; a
persistent semantic Search/Reader/Writer/Critic rail; expandable agent
summaries; accumulated report and critique panels; connection and error state;
cancellation; copy; and completed-only Markdown and JSON download links.
Markdown uses `react-markdown` with GFM and no raw HTML or unsafe protocol
rendering. It must not use `dangerouslySetInnerHTML`.

Desktop uses a sticky rail with a flexible content column. Mobile uses a compact
ordered timeline above the content; controls wrap, long text can wrap, and code
blocks scroll horizontally. Status is never color-only. Real controls expose
their state with native buttons and `aria-expanded`, the stage update is a
concise polite live region, streamed prose is not token-announced, touch
targets are at least 44px, focus indicators remain visible, and reduced motion
is respected.

### Test design

All default tests are offline and credential-free. Backend tests inject a
scripted async pipeline with deterministic IDs, timestamps, stage events,
delays, failures, and cancellation points. They cover full-stage success,
ordered deltas, data propagation, each stage failure, safe error redaction,
cancellation, the synchronous wrapper, registry transitions, snapshots,
missing runs, replay, SSE framing, keepalives, concurrent subscribers,
downloads, retention, shutdown, and static file routing.

Frontend unit tests use Vitest and React Testing Library for reducer ordering,
stream accumulation, EventSource lifecycle, reconnecting, topic validation,
component states, cancellation, downloads, accessibility, and long content.
Storybook React-Vite stories cover idle, queued, running, completed, failed,
cancelled, long content, dark theme, and mobile widths using fixtures rather
than a live backend. Playwright launches real Vite and a real FastAPI app
composed with the test-only scripted pipeline; it covers success, synchronized
statuses, cancellation, failure recovery, mobile layout, and artifact downloads.

### Tooling, CI, and documentation

Python dependencies add FastAPI and Uvicorn runtime support, with async and
HTTP test dependencies in development. LangGraph's event-streaming dependency
is isolated behind the adapter to contain schema drift. No Python lockfile is
introduced.

The frontend adds Prettier, ESLint, typechecking, Vitest coverage thresholds of
at least 80% for lines, branches, functions, and statements, Storybook, and
Playwright Chromium. `.gitignore` excludes frontend dependencies and generated
test/build artifacts. CI runs Black, Flake8, pytest, npm ci, Prettier, ESLint,
TypeScript, Vitest coverage, Vite build, Storybook build, and Chromium
Playwright tests. Python checks avoid traversing frontend dependencies.

After all implementation gates pass, README, CONTRIBUTING, and AGENTS describe
the working local web workflow, requirements, safe offline tests, static
serving, in-memory limits, and downloads. They remove Streamlit references and
avoid claims that planned behavior is implemented.

## Delivery

Work is developed on `codex/streaming-research-dashboard` from refreshed
`devel`, with repository-local author `Axel Sanchez <axelshz@gmail.com>` and
the corrected origin. Documentation, backend API, frontend, tests/CI, and final
documentation use focused Conventional Commits. After all quality gates and an
independent audit pass, authenticate GitHub CLI as `Axeloooo` if necessary,
verify the authenticated account, push the branch, and create the requested PR
against `devel`. Do not merge, release, publish, or add Codex/OpenAI/ChatGPT
authorship metadata.
