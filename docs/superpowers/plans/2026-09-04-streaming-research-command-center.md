# Streaming Research Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a local React command center that safely streams the existing four-stage research workflow over FastAPI SSE.

**Architecture:** `src/pipelines` emits safe typed events while preserving the synchronous pipeline entry point. `src/api` owns an in-memory single-worker run queue and SSE replay; `frontend/` reduces those events into the responsive command center and is served statically by FastAPI in production.

**Tech Stack:** Python 3.14.7, LangChain/LangGraph, FastAPI, Uvicorn, pytest, React, Vite, TypeScript, Tailwind CSS v4, Vitest, React Testing Library, Storybook, Playwright, ESLint, Prettier.

**Spec:** `docs/superpowers/specs/2026-09-04-streaming-research-command-center-design.md`

## Global Constraints

- Preserve `web_search(query: str) -> str`, `scrape_url(url: str) -> str`, and synchronous `run_research_pipeline(topic)`.
- Default tests are offline and credential-free; browser events contain no credentials, raw exceptions, model reasoning, raw tool diagnostics, or provider metadata.
- The process-local registry runs one job at a time, queues later jobs, and retains the newest 20 terminal runs.
- Use one Uvicorn worker; API routes must precede static serving and SPA fallback.
- Require Node `>=22.13.0`, npm `>=10`, and commit `frontend/package-lock.json`.
- Retain Black/Flake8 for Python; apply ESLint and Prettier only in `frontend/`.
- Maintain 80% minimum Python and frontend coverage.

---

### Task 1: Typed streaming pipeline

**Files:**
- Create: `src/pipelines/events.py`
- Modify: `src/agents/agents.py`, `src/pipelines/pipeline.py`
- Test: `tests/test_pipeline.py`, `tests/test_agents.py`

**Interfaces:**
- Produces `PipelineEvent`, `PipelineResult`, `AgentName`, `AgentStatus`, and `async def stream_research_pipeline(topic: str, dependencies: PipelineDependencies | None = None) -> AsyncIterator[PipelineEvent]`.
- Keeps `def run_research_pipeline(topic: str) -> dict[str, str]` returning `search_results`, `scraped_content`, `report`, and `feedback`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_stream_research_pipeline_emits_ordered_safe_events() -> None:
    events = [event async for event in stream_research_pipeline("topic", fake_dependencies)]
    assert events[-1].type == "run.completed"
    assert events[-1].payload["result"]["feedback"] == "Critique"
```

- [ ] **Step 2: Verify the red state**

Run: `.venv/bin/pytest tests/test_pipeline.py -q`

Expected: FAIL because `stream_research_pipeline` does not exist.

- [ ] **Step 3: Implement the minimum safe event stream**

```python
@dataclass(frozen=True)
class PipelineEvent:
    type: EventType
    agent: AgentName | None
    payload: dict[str, object]

async def stream_research_pipeline(...) -> AsyncIterator[PipelineEvent]:
    yield status_event("search", "running")
```

Use lazy/injected agent dependencies, normalize message text, stream only safe summaries and report/critique deltas, convert provider failures to safe terminal events, and check cancellation between chunks.

- [ ] **Step 4: Cover stage failures, cancellation, synchronous collection, and active-loop guard**

```python
def test_run_research_pipeline_collects_legacy_feedback_key() -> None:
    assert run_research_pipeline("topic", fake_dependencies)["feedback"] == "Critique"
```

- [ ] **Step 5: Verify and commit**

Run: `.venv/bin/pytest tests/test_pipeline.py tests/test_agents.py -q && .venv/bin/black src tests && .venv/bin/flake8 src tests`

Commit:
```bash
git add src/agents src/pipelines tests/test_agents.py tests/test_pipeline.py
git commit -m "feat: add typed research pipeline streaming"
```

### Task 2: FastAPI run registry and SSE API

**Files:**
- Create: `src/api/__init__.py`, `src/api/app.py`, `src/api/models.py`, `src/api/registry.py`
- Modify: `requirements.txt`, `requirements-dev.txt`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces `create_app(pipeline_factory: PipelineFactory = stream_research_pipeline) -> FastAPI`.
- Implements the start, snapshot, SSE, cancellation, Markdown-download, and JSON-download API defined in the spec.

- [ ] **Step 1: Write failing API tests**

```python
def test_events_replay_only_after_last_event_id(client: TestClient) -> None:
    run_id = client.post("/api/runs", json={"topic": "topic"}).json()["run_id"]
    body = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "2"}).text
    assert "id: 1" not in body
    assert "event: run.completed" in body
```

- [ ] **Step 2: Verify the red state**

Run: `.venv/bin/pytest tests/test_api.py -q`

Expected: FAIL because `src.api` does not exist.

- [ ] **Step 3: Implement the queue, snapshots, and cursor-based SSE**

```python
@app.post("/api/runs", status_code=202)
async def create_run(request: StartRunRequest) -> RunAccepted:
    return await registry.enqueue(request.topic)

@app.get("/api/runs/{run_id}/events")
async def events(run_id: UUID, request: Request) -> StreamingResponse:
    return StreamingResponse(
        registry.stream_sse(run_id, request.headers.get("last-event-id")),
        media_type="text/event-stream",
    )
```

Make deletion idempotent, skip unstarted agents after cancellation, protect terminal transitions with a lock, emit comment keepalives, avoid producer backpressure, and serve static files only after API routes.

- [ ] **Step 4: Add validation, queue, cancellation, subscriber, redaction, retention, download, shutdown, and static fallback tests**

```python
def test_cancelled_run_starts_next_queued_run(client: TestClient) -> None:
    first = client.post("/api/runs", json={"topic": "one"}).json()["run_id"]
    second = client.post("/api/runs", json={"topic": "two"}).json()["run_id"]
    client.delete(f"/api/runs/{first}")
    assert client.get(f"/api/runs/{second}").json()["status"] == "running"
```

- [ ] **Step 5: Verify and commit**

Run: `.venv/bin/pytest tests/test_api.py tests/test_pipeline.py -q && .venv/bin/black src tests && .venv/bin/flake8 src tests`

Commit:
```bash
git add src/api src/pipelines requirements.txt requirements-dev.txt tests/test_api.py
git commit -m "feat: add streaming research api"
```

### Task 3: React command center and frontend unit tests

**Files:**
- Create: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/src/`
- Create: `frontend/.storybook/`, `frontend/src/**/*.stories.tsx`, `frontend/src/**/*.test.tsx`
- Modify: `.gitignore`

**Interfaces:**
- Produces `ResearchEvent`, `ResearchState`, `researchReducer`, `useResearchRun`, and `App`.
- Consumes the API event envelopes and artifact URLs from Task 2.

- [ ] **Step 1: Write failing reducer and UI tests**

```tsx
it("ignores duplicate event IDs and appends report deltas once", () => {
  const once = researchReducer(initialResearchState, reportDelta(4, "First "));
  expect(researchReducer(once, reportDelta(4, "First ")).report).toBe("First ");
});
```

- [ ] **Step 2: Verify the red state**

Run: `cd frontend && npm test -- --run`

Expected: FAIL because the frontend project is absent.

- [ ] **Step 3: Implement the smallest accessible command center**

```ts
export function researchReducer(state: ResearchState, event: ResearchEvent): ResearchState {
  if (event.id <= state.lastEventId) return state;
  if (event.type === "report.delta") {
    return { ...state, lastEventId: event.id, report: state.report + event.payload.delta };
  }
  return applyEvent(state, event);
}
```

Use React/Vite/TypeScript/Tailwind v4, ESLint flat config, Prettier, Vitest, React Testing Library, and `react-markdown` with GFM and no raw HTML. Implement status rail, expandable summaries, report/critique panes, cancellation, copy, connection state, and completed-only downloads.

- [ ] **Step 4: Cover EventSource lifecycle, validation, reconnect, errors, cancellation, accessibility, dark mode, mobile, and long content**

```tsx
it("shows reconnecting without marking a running run failed", async () => {
  render(<ResearchApp eventSourceFactory={flakyEventSourceFactory} />);
  expect(await screen.findByText(/reconnecting/i)).toBeVisible();
});
```

- [ ] **Step 5: Add stories, verify, and commit**

Run: `cd frontend && npm run format && npm run lint && npm run typecheck && npm run test:coverage && npm run build && npm run build-storybook`

Commit:
```bash
git add frontend .gitignore
git commit -m "feat: add research command center"
```

### Task 4: E2E, CI, and documentation

**Files:**
- Create: `frontend/e2e/research.spec.ts`, `frontend/playwright.config.ts`
- Modify: `.github/workflows/ci.yaml`, `.github/workflows/release.yaml`, `README.md`, `CONTRIBUTING.md`, `AGENTS.md`
- Test: `tests/test_package_structure.py`

**Interfaces:**
- Consumes Tasks 1-3 and supplies deterministic test-only FastAPI pipeline wiring.
- Produces CI verification for backend, frontend, Storybook, and Chromium E2E.

- [ ] **Step 1: Write the failing browser test**

```ts
test("streams output, synchronizes stages, and downloads artifacts", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel(/research topic/i).fill("AI jobs");
  await page.getByRole("button", { name: /run research/i }).click();
  await expect(page.getByText(/writer.*running/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /download markdown/i })).toBeEnabled();
});
```

- [ ] **Step 2: Verify the red state**

Run: `cd frontend && npx playwright test`

Expected: FAIL because Playwright configuration and the test API harness are absent.

- [ ] **Step 3: Add deterministic two-server Playwright setup**

Start Vite and Uvicorn using `create_app` with a scripted pipeline. Test successful streaming, agent status sync, cancellation, failure recovery, mobile layout, and both downloads without live credentials.

- [ ] **Step 4: Update CI and contributor documentation after behavior exists**

Use Node 22.13.0, `npm ci`, Prettier, ESLint, typecheck, Vitest coverage, Vite, Storybook, and Chromium. Document the actual local web workflow, static serving, queue/retention limits, safe offline tests, downloads, and removal of Streamlit.

- [ ] **Step 5: Run the complete quality gate and commit**

Run: `.venv/bin/black --check . && .venv/bin/flake8 . && .venv/bin/pytest && cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test:coverage && npm run build && npm run build-storybook && npx playwright test`

Commit:
```bash
git add .github README.md CONTRIBUTING.md AGENTS.md frontend tests
git commit -m "ci: verify streaming research application"
```

## Plan self-review

- Tasks 1-2 cover the pipeline, queue, cancellation, API, and static serving.
- Task 3 covers all approved interface and frontend unit-test behavior.
- Task 4 covers integrated E2E, CI, and accurate documentation.
- `PipelineEvent` is emitted by Task 1, translated by Task 2, consumed by Task 3, and verified by Task 4.
