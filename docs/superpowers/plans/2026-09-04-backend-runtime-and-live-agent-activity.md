# Backend Runtime and Live Agent Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use \`superpowers:subagent-driven-development\` (recommended) or \`superpowers:executing-plans\` to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Move the full Python application to \`backend/\`, bound provider stages, and show safe live agent/tool activity in the frontend.

**Architecture:** \`backend/\` becomes an independently runnable Python project with the \`research_assistant\` package, package-mirrored backend tests, and a thin FastAPI adapter. The Vite application remains in \`frontend/\`; it reduces replayable, safe SSE activity events to animated agent-card state.

**Tech Stack:** Python 3.14, FastAPI, LangChain/LangGraph, Tavily, pytest, React 19, TypeScript, Vite, Tailwind, Vitest/RTL, Playwright, Storybook.

**Spec:** \`docs/superpowers/specs/2026-09-04-backend-runtime-and-live-agent-activity-design.md\`

## Global Constraints

- The branch is \`feature/streaming-research-command-center\`; never create a \`codex/\` branch.
- Do not use a git worktree; work directly on the feature branch.
- All Python runtime code and Python config live under \`backend/\`; \`frontend/\` contains UI code only.
- Backend default tests are offline and credential-free; mock Gemini, Tavily, HTTP, and LangChain callback boundaries.
- Preserve \`web_search(query: str) -> str\` and \`scrape_url(url: str) -> str\`.
- Never send prompts, chain-of-thought, tool arguments/results, credentials, provider metadata, or raw exceptions through SSE.
- Search has a 45-second stage deadline and a 30-second Tavily request timeout.
- Backend coverage remains at least 80% across \`backend/src\`.
- Use Conventional Commit messages and target \`devel\` with the existing PR.

---

### Task 1: Create the standalone backend project layout

**Files:**

- Move: \`src/\` → \`backend/src/research_assistant/\`
- Move: \`tests/test_agents.py\` → \`backend/tests/agents/test_agents.py\`
- Move: \`tests/test_tools.py\` → \`backend/tests/tools/test_tools.py\`
- Move: \`tests/test_pipeline.py\` → \`backend/tests/pipelines/test_pipeline.py\`
- Move: \`tests/test_api.py\` → \`backend/tests/api/test_api.py\`
- Move: \`tests/e2e_server.py\` → \`backend/tests/api/e2e_server.py\`
- Move: \`requirements*.txt\`, \`.python-version\`, \`pyproject.toml\`, \`.flake8\`, \`.env.example\`, and \`main.py\` → \`backend/\`
- Modify: \`.gitignore\`, \`AGENTS.md\`, \`frontend/playwright.config.ts\`
- Test: \`backend/tests/agents/test_imports.py\`

**Interfaces:**

- Produces: \`research_assistant.agents\`, \`research_assistant.api\`, \`research_assistant.pipelines\`, and \`research_assistant.tools\` imports with \`backend/src\` on \`PYTHONPATH\`.

- [ ] **Step 1: Write the failing import-boundary test**

\`\`\`python
def test_backend_packages_import_without_root_src_package() -> None:
    from research_assistant.api.app import create_app
    from research_assistant.pipelines.pipeline import stream_research_pipeline

    assert callable(create_app)
    assert callable(stream_research_pipeline)
\`\`\`

- [ ] **Step 2: Verify the test fails before relocation**

Run: \`cd backend && .venv/bin/pytest tests/agents/test_imports.py -q\`

Expected: FAIL because \`backend/\` and \`research_assistant\` do not yet exist.

- [ ] **Step 3: Move the Python project and update imports**

Use \`git mv\` for source, tests, Python configuration, requirements, and the entry point. Rename imports from \`src.*\` to \`research_assistant.*\`. Set backend pytest configuration to:

\`\`\`toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-ra --strict-markers --cov=research_assistant --cov-report=term-missing --cov-fail-under=80"
\`\`\`

Keep test categories explicit (\`agents\`, \`api\`, \`pipelines\`, \`tools\`). Update the Playwright fake-server command to invoke \`backend/.venv/bin/python -m tests.api.e2e_server\`.
Create the ignored backend environment before running the relocated suite:

\`python -m venv backend/.venv && backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt\`.

- [ ] **Step 4: Verify the relocated backend suite passes**

Run: \`cd backend && .venv/bin/black --check . && .venv/bin/flake8 . && .venv/bin/pytest -q\`

Expected: all relocated backend tests pass with at least 80% coverage.

- [ ] **Step 5: Commit the structural migration**

\`\`\`zsh
git add backend .gitignore AGENTS.md frontend/playwright.config.ts
git commit -m "refactor: isolate backend runtime"
\`\`\`

### Task 2: Bound search and publish safe activity events

**Files:**

- Modify: \`backend/src/research_assistant/pipelines/events.py\`
- Modify: \`backend/src/research_assistant/pipelines/pipeline.py\`
- Modify: \`backend/src/research_assistant/agents/agents.py\`
- Modify: \`backend/src/research_assistant/tools/tools.py\`
- Test: \`backend/tests/pipelines/test_timeouts.py\`
- Test: \`backend/tests/pipelines/test_activity.py\`
- Test: \`backend/tests/tools/test_tools.py\`

**Interfaces:**

- Produces: \`StageTimeouts\`, \`agent.activity\` events, and bounded default stage execution.

- [ ] **Step 1: Write failing timeout and safe-activity tests**

\`\`\`python
def test_search_timeout_emits_safe_terminal_failure() -> None:
    events = collect(
        stream_research_pipeline(
            "topic",
            blocked_dependencies,
            stage_timeouts=StageTimeouts(search_seconds=0.01),
        )
    )

    assert events[-1].payload == {"message": "Search timed out. Please try again."}


def test_tool_callback_emits_fixed_safe_activity_label() -> None:
    assert activity_from_tool_start("web_search").payload == {
        "kind": "using_tool",
        "label": "Using web search",
    }
\`\`\`

Add a tool test asserting Tavily receives \`timeout=30\`.

- [ ] **Step 2: Verify the tests fail**

Run: \`cd backend && .venv/bin/pytest tests/pipelines/test_timeouts.py tests/pipelines/test_activity.py tests/tools/test_tools.py -q\`

Expected: FAIL because stage deadlines, callback activity, and the Tavily timeout argument do not exist.

- [ ] **Step 3: Implement deadlines and callback-backed activity**

Add \`agent.activity\` to the safe event union. Add a frozen \`StageTimeouts\` dataclass with defaults of 45, 45, 90, and 45 seconds. Wrap each stage awaitable in \`asyncio.wait_for\`; on timeout emit the active stage's failed status, later skipped statuses, and a fixed safe message.

Implement a run-scoped LangChain callback handler. Its only tool mappings are:

\`\`\`python
TOOL_ACTIVITY = {
    "web_search": ("using_tool", "Using web search"),
    "scrape_url": ("using_tool", "Reading selected source"),
}
\`\`\`

Capture the event loop and use thread-safe scheduling to relay callback events from \`asyncio.to_thread\`. Emit fixed \`thinking\` and \`streaming\` labels around Writer and Critic. Pass \`timeout=30\` to Tavily \`search()\`.

- [ ] **Step 4: Verify stage behavior**

Run: \`cd backend && .venv/bin/pytest tests/pipelines tests/tools -q\`

Expected: the timeout test finishes quickly, sends no provider data, and all pipeline/tool tests pass.

- [ ] **Step 5: Commit the bounded stream**

\`\`\`zsh
git add backend/src backend/tests/pipelines backend/tests/tools
git commit -m "feat: stream safe agent activity"
\`\`\`

### Task 3: Replay activity over the API

**Files:**

- Modify: \`backend/src/research_assistant/api/registry.py\`
- Modify: \`backend/src/research_assistant/api/app.py\`
- Test: \`backend/tests/api/test_api.py\`

**Interfaces:**

- Consumes: safe \`agent.activity\` events.
- Produces: replayable activity frames and snapshots that include latest activity per agent.

- [ ] **Step 1: Write failing API tests**

\`\`\`python
def test_sse_replays_safe_agent_activity() -> None:
    response = client.get(f"/api/runs/{run_id}/events")

    assert "event: agent.activity" in response.text
    assert "Using web search" in response.text
    assert "tool arguments" not in response.text


def test_timed_out_run_releases_next_queued_run() -> None:
    assert wait_for_terminal(client, blocked_run)["status"] == "failed"
    assert wait_for_terminal(client, next_run)["status"] == "completed"
\`\`\`

- [ ] **Step 2: Verify the API tests fail**

Run: \`cd backend && .venv/bin/pytest tests/api/test_api.py -q\`

Expected: FAIL because the registry drops activity and has no timeout-driven queue coverage.

- [ ] **Step 3: Add activity persistence and replay**

Add \`activities: dict[AgentName, AgentActivity | None]\` to \`RunRecord\`. Validate only allowed kind/fixed-label pairs in \`_apply_pipeline_event\`, persist and publish those safe values, and include activities in \`snapshot()\`. Preserve event IDs, Last-Event-ID replay, and termination before \`_start_next()\`.

- [ ] **Step 4: Verify API contracts**

Run: \`cd backend && .venv/bin/pytest tests/api -q\`

Expected: activity replay, timeout failure, cancellation, downloads, and FIFO queue tests pass offline.

- [ ] **Step 5: Commit API support**

\`\`\`zsh
git add backend/src/research_assistant/api backend/tests/api
git commit -m "feat: replay agent activity over sse"
\`\`\`

### Task 4: Reorganize frontend tests and render live activity

**Files:**

- Move: \`frontend/src/useResearchRun.test.ts\` → \`frontend/tests/unit/useResearchRun.test.ts\`
- Move: \`frontend/src/components/RunTimeline.test.tsx\` → \`frontend/tests/unit/components/RunTimeline.test.tsx\`
- Move: \`frontend/e2e/research.spec.ts\` → \`frontend/tests/e2e/research.spec.ts\`
- Modify: \`frontend/src/useResearchRun.ts\`
- Modify: \`frontend/src/components/RunTimeline.tsx\`
- Modify: \`frontend/src/styles.css\`
- Modify: \`frontend/vite.config.ts\`, \`frontend/playwright.config.ts\`
- Test: \`frontend/tests/unit/useResearchRun.test.ts\`
- Test: \`frontend/tests/unit/components/RunTimeline.test.tsx\`
- Test: \`frontend/tests/e2e/research.spec.ts\`

**Interfaces:**

- Consumes: snapshots and SSE events with \`activities[agent]\` and \`agent.activity\`.
- Produces: accessible agent cards that show safe activity and animate only while running.

- [ ] **Step 1: Write failing reducer and component tests in the new layout**

\`\`\`tsx
it("stores the newest safe activity for the running agent", () => {
  const state = runReducer(runningState, {
    type: "event",
    event: {
      id: 3,
      type: "agent.activity",
      agent: "search",
      payload: { kind: "using_tool", label: "Using web search" }
    }
  });

  expect(state.snapshot?.activities.search?.label).toBe("Using web search");
});
\`\`\`

\`\`\`tsx
it("shows animated activity only while a stage is running", () => {
  render(<RunTimeline agents={runningAgents} summaries={emptySummaries} activities={activities} />);

  expect(screen.getByText("Using web search")).toBeVisible();
  expect(screen.getByLabelText("Search activity")).toHaveClass("activity-shimmer");
});
\`\`\`

- [ ] **Step 2: Verify the unit tests fail**

Run: \`cd frontend && npm test -- --run tests/unit/useResearchRun.test.ts tests/unit/components/RunTimeline.test.tsx\`

Expected: FAIL because activity state, component props, and new test discovery paths are absent.

- [ ] **Step 3: Update UI contract and presentation**

Extend \`RunSnapshot\` with \`activities\`. Validate activity payloads in the reducer and ignore malformed/stale data. Add an \`activities\` prop to \`RunTimeline\`; render an activity label with \`aria-label="<Stage> activity"\` only for running stages. Add a reduced-motion-safe shimmer/pulse animation and stop it for terminal statuses. Update Vitest include/exclude and Playwright \`testDir\` to the new test directories.

- [ ] **Step 4: Extend the deterministic browser test**

Make \`backend/tests/api/e2e_server.py\` emit Search's \`agent.activity\` before completion. Assert Playwright sees \`Using web search\` before the completed report and download links.

- [ ] **Step 5: Verify all frontend quality gates**

Run: \`cd frontend && npm run format && npm run lint && npm test && npm run build && npm run build-storybook && npm run test:e2e\`

Expected: formatter, linter, unit suite, build, Storybook, and browser test pass.

- [ ] **Step 6: Commit UI behavior**

\`\`\`zsh
git add frontend
git commit -m "feat: show live agent activity"
\`\`\`

### Task 5: Align CI and documentation

**Files:**

- Modify: \`.github/workflows/ci.yaml\`
- Modify: \`README.md\`, \`CONTRIBUTING.md\`, \`AGENTS.md\`, \`.gitignore\`
- Test: \`backend/tests/agents/test_imports.py\`

**Interfaces:**

- Produces: accurate Beta documentation and CI commands that execute subproject tooling.

- [ ] **Step 1: Write a failing backend entrypoint test**

\`\`\`python
def test_backend_entrypoint_is_import_safe() -> None:
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
\`\`\`

- [ ] **Step 2: Verify the test fails**

Run: \`cd backend && .venv/bin/pytest tests/agents/test_imports.py -q\`

Expected: FAIL until the backend entrypoint matches the documented command and avoids provider work at import time.

- [ ] **Step 3: Update tooling and docs**

Set CI Python-job working directory to \`backend\`, cache \`backend/requirements*.txt\`, and run backend Black, Flake8, and pytest there. Keep frontend jobs in \`frontend\`; browser E2E starts the backend fake server. Update README and contributor guidance to Beta status, the two-root layout, safe activity boundary, deadlines, and explicit \`cd backend\` / \`cd frontend\` commands. Add ignores for \`backend/.venv\`, backend coverage artifacts, and frontend generated output.

- [ ] **Step 4: Verify all documented gates**

Run:

\`\`\`zsh
cd backend && .venv/bin/black --check . && .venv/bin/flake8 . && .venv/bin/pytest -q
cd frontend && npm run format && npm run lint && npm test && npm run build && npm run build-storybook && npm run test:e2e
git diff --check
\`\`\`

Expected: every command exits zero; backend coverage remains at least 80%; no default test uses provider credentials or live network calls.

- [ ] **Step 5: Commit delivery changes and update the PR**

\`\`\`zsh
git add .github README.md CONTRIBUTING.md AGENTS.md .gitignore backend frontend
git commit -m "docs: align beta backend workflow"
git push
\`\`\`

Confirm the existing PR targets \`devel\` and its head is \`feature/streaming-research-command-center\`.
